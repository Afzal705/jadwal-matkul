import hashlib
from flask import Flask, render_template, request, jsonify
from neo4j_driver import Neo4jConnector
from graph_scheduler import schedule_courses
from graph_scheduler import compare_algorithms
from neo4j import GraphDatabase

# from neo4j_driver import get_all_course_students

app = Flask(__name__)
neo4j = Neo4jConnector("bolt://localhost:7687", "neo4j", "412445678")  # ganti dengan kredensial Anda

DEFAULT_SLOTS = [
    "Senin 08.00", "Senin 10.00", "Senin 13.00", "Senin 15.00",
    "Selasa 08.00", "Selasa 10.00", "Selasa 13.00", "Selasa 15.00",
    "Rabu 08.00", "Rabu 10.00", "Rabu 13.00", "Rabu 15.00",
    "Kamis 08.00", "Kamis 10.00", "Kamis 13.00", "Kamis 15.00",
    "Jumat 08.00", "Jumat 10.00", "Jumat 13.00", "Jumat 15.00"
]

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

@app.route("/evaluasi", methods=["GET"])
def halaman_evaluasi():
    return render_template("eval.html")  # tanpa hasil dulu

@app.route("/evaluasi", methods=["POST"])
def jalankan_evaluasi():
    course_students = neo4j.get_all_course_students()
    result = compare_algorithms(course_students, DEFAULT_SLOTS, neo4j.driver)  # ✅ TAMBAHKAN driver
    return render_template("eval.html", result=result)





@app.route("/mahasiswa")
def halaman_mahasiswa():
    return render_template("mahasiswa.html")

# ================================================== dosen =====================================================
@app.route("/api/jadwal_dosen")
def jadwal_dosen():
    if "username" not in session or session.get("peran") != "dosen":
        return jsonify({"error": "Unauthorized"}), 403

    dosen = session["username"]
    try:
        with neo4j.driver.session() as db:
            result = db.run("""
                MATCH (d:Dosen {nama: $nama})-[:MENGAJAR]->(k:Kelas)
                MATCH (k)-[:UNTUK]->(matkul:Matakuliah)
                # MATCH (k)-[:DIJADWALKAN_PADA]->(s:Slot)
                RETURN matkul.nama AS matakuliah, s.waktu AS slot
            """, nama=dosen)
            jadwal = [dict(record) for record in result]
        return jsonify(jadwal)
    except Exception as e:
        return jsonify({"error": str(e)}), 500



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

@app.route("/api/admin/auto_alokasi", methods=["POST"])
def auto_alokasi():
    try:
        data = request.get_json()
        selected_algo = data.get("algoritma", "greedy")  # default ke greedy

        course_students = neo4j.get_all_course_students()
        result = compare_algorithms(course_students, DEFAULT_SLOTS, neo4j.driver)

        if selected_algo == "greedy":
            eval_result = result["greedy"]
        elif selected_algo == "welsh_powell":
            eval_result = result["welsh_powell"]
        else:
            return jsonify({"message": "❌ Algoritma tidak dikenali"}), 400

        return jsonify({
            "message": f"✅ Slot berhasil dialokasikan menggunakan algoritma {selected_algo.capitalize()}.",
            "detail": {
                "num_colors": eval_result["eval"]["num_colors"],
                "conflict_percentage": eval_result["eval"]["conflict_percentage"],
                "time": eval_result["time"]
            }
        })

    except Exception as e:
        return jsonify({"message": "❌ Gagal melakukan alokasi otomatis.", "error": str(e)}), 500


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
    try:
        data = request.get_json()
        dosen = data["dosen"]
        matkul = data["matakuliah"]
    except Exception as e:
        return jsonify({"error": "Data tidak valid atau JSON salah", "detail": str(e)}), 400

    try:
        with neo4j.driver.session() as db:
            # Cari slot yang belum dipakai
            slot = db.run("""
                MATCH (s:Slot)
                WHERE NOT EXISTS {
                    MATCH (c:Kelas)-[:DIJADWALKAN_PADA]->(s)
                }
                RETURN s.waktu AS waktu LIMIT 1
            """).single()

            if not slot:
                return jsonify({"message": "Slot penuh"}), 400

            kelas_id = f"KLS_{dosen}_{matkul}".replace(" ", "_")

            result = db.run("""
                CREATE (c:Kelas {id: $kelas_id})
                WITH c
                MATCH (d:Dosen {nama: $dosen}), (m:Matakuliah {nama: $matkul}), (s:Slot {waktu: $slot})
                MERGE (d)-[:MENGAJAR]->(c)
                MERGE (c)-[:UNTUK]->(m)
                MERGE (c)-[:DIJADWALKAN_PADA]->(s)
            """, dosen=dosen, matkul=matkul, slot=slot["waktu"], kelas_id=kelas_id)

            return jsonify({"message": f"Kelas {kelas_id} dibuat, slot: {slot['waktu']}"})

    except Exception as e:
        return jsonify({"error": "Gagal membuat relasi kelas", "detail": str(e)}), 500


#==================================== Relasi Mahasiswa ++
@app.route("/api/admin/relasi_mahasiswa", methods=["POST"])
def relasi_mahasiswa():
    try:
        data = request.get_json()
        mahasiswa = data["mahasiswa"]
        kelas_id = data["kelas"]

        with neo4j.driver.session() as db:
            kelas = db.run("""
                MATCH (c:Kelas {id: $id}) RETURN c.id AS id
            """, id=kelas_id).single()

            if not kelas:
                return jsonify({"message": "Kelas tidak ditemukan"}), 400

            db.run("""
                MATCH (mhs:Mahasiswa {nama: $mhs}), (c:Kelas {id: $id})
                MERGE (mhs)-[:MENGAMBIL]->(c)
            """, mhs=mahasiswa, id=kelas_id)

            return jsonify({"message": f"Mahasiswa berhasil mengambil kelas {kelas_id}"})

    except KeyError as e:
        return jsonify({"message": f"Field hilang: {e}"}), 400
    except Exception as e:
        return jsonify({"message": f"Terjadi error: {str(e)}"}), 500


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
    if "username" not in session or session.get("peran") != "mahasiswa":
        return jsonify({"error": "Unauthorized"}), 403

    mahasiswa = session["username"]
    try:
        with neo4j.driver.session() as db:
            result = db.run("""
                MATCH (mhs:Mahasiswa {nama: $nama})-[:MENGAMBIL]->(k:Kelas)
                MATCH (k)-[:UNTUK]->(matkul:Matakuliah)
                MATCH (k)-[:DIJADWALKAN_PADA]->(s:Slot)
                OPTIONAL MATCH (d:Dosen)-[:MENGAJAR]->(k)
                RETURN matkul.nama AS matakuliah, d.nama AS dosen, s.waktu AS slot
            """, nama=mahasiswa)
            jadwal = [dict(record) for record in result]
        return jsonify(jadwal)
    except Exception as e:
        return jsonify({"error": str(e)}), 500



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

#========================================== graf ============================================
SLOT_COLOR_MAP = {
    "Senin 08.00": "#e74c3c",
    "Senin 10.00": "#3498db",
    "Selasa 08.00": "#2ecc71",
    "Selasa 10.00": "#9b59b6",
    "Rabu 08.00": "#f1c40f",
    "Rabu 10.00": "#e67e22",
    "Kamis 08.00": "#1abc9c",
    "Kamis 10.00": "#34495e",
    "Jumat 08.00": "#7f8c8d",
    "Jumat 10.00": "#ff6f61",
}
DEFAULT_SLOTS = list(SLOT_COLOR_MAP.keys())



def hash_color(text):
    h = hashlib.md5(text.encode()).hexdigest()
    return f"#{h[:6]}"

# @app.route("/api/graph")
# def get_graph():
#     # Ambil data dari Neo4j
#     course_data = neo4j.get_course_student_map()

#     # Gunakan algoritma scheduler (DSATUR)
#     slot_mapping = schedule_courses(course_data, DEFAULT_SLOTS)

#     nodes = []
#     edges = []
#     added_nodes = set()

#     for course, mahasiswa_list in course_data.items():
#         # Ambil slot dan warna matakuliah
#         slot = slot_mapping.get(course, "Senin 08.00")
#         color = SLOT_COLOR_MAP.get(slot, "#95a5a6")

#         # Tambah node untuk matakuliah
#         if course not in added_nodes:
#             nodes.append({
#                 "id": course,
#                 "label": course,
#                 "color": color
#             })
#             added_nodes.add(course)

#         # Tambah node dan edge untuk mahasiswa
#         for mhs in mahasiswa_list:
#             if mhs not in added_nodes:
#                 nodes.append({
#                     "id": mhs,
#                     "label": mhs,
#                     "color": "#cccccc"  # Mahasiswa pakai warna abu
#                 })
#                 added_nodes.add(mhs)

#             edges.append({
#                 "from": mhs,
#                 "to": course
#             })

#     return jsonify({"nodes": nodes, "edges": edges})


