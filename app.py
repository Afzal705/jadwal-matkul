from flask import Flask, render_template, request, jsonify
from neo4j_driver import Neo4jConnector
from graph_scheduler import schedule_courses

app = Flask(__name__)
neo4j = Neo4jConnector("bolt://localhost:7687", "neo4j", "412445678")  # ganti dengan kredensial Anda

DEFAULT_SLOTS = ["Senin 08.00", "Senin 10.00", "Selasa 08.00", "Selasa 10.00"]

# @app.route("/")
# def index():
#     return render_template("index.html")

from flask import Flask, render_template, request, redirect, session, url_for
app.secret_key = "rahasia"  # ganti untuk keamanan asli
#======================================== LOGIN ============================================
@app.route("/")
def beranda():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        peran = request.form["peran"]

        # Validasi nama di database (kecuali admin)
        if peran in ["dosen", "mahasiswa"]:
            label = "Dosen" if peran == "dosen" else "Mahasiswa"
            with neo4j.driver.session() as db:
                result = db.run(
                    f"MATCH (n:{label} {{nama: $nama}}) RETURN count(n) > 0 AS ada",
                    nama=username
                )
                if not result.single()["ada"]:
                    return f"❌ Nama {label.lower()} '{username}' tidak ditemukan di database.", 403

        # Login berhasil
        session["username"] = username
        session["peran"] = peran

        # Arahkan sesuai peran
        if peran == "admin":
            return redirect("/admin")
        elif peran == "dosen":
            return redirect("/dosen")
        elif peran == "mahasiswa":
            return redirect("/mahasiswa")

        return "Peran tidak dikenali.", 400

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/mahasiswa")
def halaman_mahasiswa():
    return render_template("mahasiswa.html")

# ================================================== dosen =====================================================
@app.route("/api/jadwal_dosen")
def jadwal_dosen():
    if session.get("peran") != "dosen":
        return jsonify([])

    nama = session["username"]
    query = """
    MATCH (d:Dosen {nama: $nama})-[:MENGAJAR]->(k:Perkuliahan)
    MATCH (k)-[:UNTUK]->(mat:Matakuliah)
    MATCH (k)-[:DIJADWALKAN_PADA]->(slot:Slot)
    RETURN mat.nama AS matkul, slot.waktu AS slot
    ORDER BY slot.waktu
    """
    with neo4j.driver.session() as db:
        result = db.run(query, nama=nama)
        return jsonify([{
            "matakuliah": r["matkul"],
            "slot": r["slot"]
        } for r in result])




@app.route("/dosen")
def halaman_dosen():
    if session.get("peran") != "dosen":
        return redirect("/login")
    return render_template("dosen.html")

#========================================= Admin ===========================================

# @app.route("/admin")
# def halaman_admin():
#     return render_template("admin.html")

@app.route("/admin")
def halaman_admin():
    if session.get("peran") != "admin":
        return redirect("/login")
    return render_template("admin.html")
#======================================= Drobdown ++
@app.route("/api/admin/dropdowns")
def dropdowns():
    with neo4j.driver.session() as db:
        return jsonify({
            "dosen": db.run("MATCH (d:Dosen) RETURN d.nama AS nama").value(),
            "mahasiswa": db.run("MATCH (m:Mahasiswa) RETURN m.nama AS nama").value(),
            "matakuliah": db.run("MATCH (m:Matakuliah) RETURN m.nama AS nama").value()
        })

    
#======================================== relsi dosen ++
@app.route("/api/admin/relasi_dosen", methods=["POST"])
def relasi_dosen():
    dosen = data["dosen"]; matkul = data["matakuliah"]
    with neo4j.driver.session() as db:
        slot = db.run("""
            MATCH (s:Slot)
            WHERE NOT EXISTS {
                MATCH (c:Kelas)-[:DIJADWALKAN_PADA]->(s)
            }
            RETURN s.waktu AS waktu LIMIT 1
        """).single()
        if not slot: return jsonify({"message": "Slot penuh"}), 400

        kelas_id = f"KLS_{dosen}_{matkul}".replace(" ", "_")
        db.run("""
            CREATE (c:Kelas {id: $kelas_id})
            MATCH (d:Dosen {nama: $dosen}), (m:Matakuliah {nama: $matkul}), (s:Slot {waktu: $slot})
            MERGE (d)-[:MENGAJAR]->(c)
            MERGE (c)-[:UNTUK]->(m)
            MERGE (c)-[:DIJADWALKAN_PADA]->(s)
        """, dosen=dosen, matkul=matkul, slot=slot["waktu"], kelas_id=kelas_id)

        return jsonify({"message": f"Kelas {kelas_id} dibuat, slot: {slot['waktu']}"})

#==================================== Relasi Mahasiswa ++
@app.route("/api/admin/relasi_mahasiswa", methods=["POST"])
def relasi_mahasiswa():
    mahasiswa = data["mahasiswa"]; matkul = data["matakuliah"]
    with neo4j.driver.session() as db:
        chosen = db.run("""
            MATCH (c:Kelas)-[:UNTUK]->(m:Matakuliah {nama: $matkul})
            RETURN c.id AS id
            LIMIT 1
        """, matkul=matkul).single()
        if not chosen:
            return jsonify({"message": "Belum ada kelas untuk matakuliah ini"}), 400

        db.run("""
            MATCH (mhs:Mahasiswa {nama: $mhs}), (c:Kelas {id: $id})
            MERGE (mhs)-[:MENGAMBIL]->(c)
        """, mhs=mahasiswa, id=chosen["id"])

        return jsonify({"message": f"Mahasiswa berhasil terdaftar di kelas {chosen['id']}"})

@app.route("/api/admin/kelas/<matkul>")
def admin_kelas(matkul):
    with neo4j.driver.session() as db:
        return jsonify(db.run("""
            MATCH (c:Kelas)-[:UNTUK]->(m:Matakuliah {nama: $matkul})
            RETURN c.id AS id
        """, matkul=matkul).value())



# ========================================== Relasi_Dosen =========================================

@app.route("/relasi/dosen")
def relasi_dosen_page():
    return render_template("relasi_dosen.html")

@app.route("/api/daftar_node")
def daftar_node():
    with neo4j.driver.session() as session:
        dosen = session.run("MATCH (d:Dosen) RETURN d.nama AS nama")
        matkul = session.run("MATCH (m:Matakuliah) RETURN m.nama AS nama")
        return jsonify({
            "dosen": [r["nama"] for r in dosen],
            "matakuliah": [r["nama"] for r in matkul]
        })

@app.route("/api/relasi_dosen", methods=["POST"])
def buat_relasi_dosen():
    data = request.get_json()
    dosen = data["dosen"]
    matkul = data["matakuliah"]

    with neo4j.driver.session() as session:
        # Cari slot yang belum dipakai
        result = session.run("""
            MATCH (s:Slot)
            WHERE NOT EXISTS {
                MATCH (:Matakuliah)-[:DIJADWALKAN_PADA]->(s)
            }
            RETURN s.waktu AS slot
            LIMIT 1
        """)
        slot = result.single()
        if not slot:
            return jsonify({"message": "❌ Tidak ada slot kosong tersedia."}), 400

        # Buat relasi dan tetapkan slot
        session.run("""
            MATCH (d:Dosen {nama: $dosen})
            MATCH (m:Matakuliah {nama: $matkul})
            MATCH (s:Slot {waktu: $slot})
            MERGE (d)-[:MENGAJAR]->(m)
            MERGE (m)-[:DIJADWALKAN_PADA]->(s)
        """, dosen=dosen, matkul=matkul, slot=slot["slot"])

        return jsonify({"message": f"✅ Relasi dibuat. Slot yang ditetapkan: {slot['slot']}."})


@app.route("/api/jadwal_mahasiswa")
def jadwal_mahasiswa():
    if session.get("peran") != "mahasiswa":
        return jsonify([])

    nama = session["username"]
    query = """
    MATCH (mhs:Mahasiswa {nama: $nama})-[:MENGAMBIL]->(k:Perkuliahan)
    MATCH (k)-[:UNTUK]->(mat:Matakuliah)
    MATCH (k)-[:DIJADWALKAN_PADA]->(slot:Slot)
    MATCH (d:Dosen)-[:MENGAJAR]->(k)
    RETURN mat.nama AS matkul, d.nama AS dosen, slot.waktu AS slot
    ORDER BY slot.waktu
    """
    with neo4j.driver.session() as db:
        result = db.run(query, nama=nama)
        return jsonify([{
            "matakuliah": r["matkul"],
            "dosen": r["dosen"],
            "slot": r["slot"]
        } for r in result])


@app.route("/api/schedule")
def get_schedule():
    course_data = neo4j.get_course_student_map()
    jadwal = schedule_courses(course_data, DEFAULT_SLOTS)
    return jsonify(jadwal)

@app.route("/api/graph")
def get_graph():
    nodes, edges = neo4j.get_graph_data()
    return jsonify({"nodes": nodes, "edges": edges})

@app.route("/api/add", methods=["POST"])
def add_data():
    data = request.get_json()
    neo4j.add_data(
        data["mahasiswa"],
        data["matakuliah"],
        data["dosen"],
        data["ruangan"],
        data["slot"]  # tambahkan ini
    )
    return jsonify({"status": "success"})

@app.route("/api/jadwal_semua")
def semua_jadwal():
    query = """
    MATCH (m:Matakuliah)-[:DIJADWALKAN_PADA]->(s:Slot)
    RETURN m.nama AS matakuliah, s.waktu AS slot
    ORDER BY s.waktu, m.nama
    """
    with neo4j.driver.session() as session:
        result = session.run(query)
        data = [{"matakuliah": r["matakuliah"], "slot": r["slot"]} for r in result]
        return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True, port=5001)

