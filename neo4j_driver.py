from neo4j import GraphDatabase

class Neo4jConnector:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def get_course_student_map(self):
        query = """
        MATCH (m:Mahasiswa)-[:MENGAMBIL]->(c:Matakuliah)
        RETURN c.nama AS course, collect(m.nama) AS students
        """
        with self.driver.session() as session:
            result = session.run(query)
            return {record["course"]: record["students"] for record in result}

    def get_graph_data(self):
        query = """
        MATCH (a)-[r]->(b)
        RETURN id(a) AS ida, a.nama AS aname, labels(a)[0] AS alabel,
               type(r) AS rel, id(b) AS idb, b.nama AS bname, labels(b)[0] AS blabel
        """
        with self.driver.session() as session:
            result = session.run(query)
            nodes = {}
            edges = []
            for record in result:
                for idn, name, label in [(record["ida"], record["aname"], record["alabel"]),
                                         (record["idb"], record["bname"], record["blabel"])]:
                    if idn not in nodes:
                        nodes[idn] = {"data": {"id": str(idn), "label": f"{label}: {name}"}}
                edges.append({
                    "data": {
                        "source": str(record["ida"]),
                        "target": str(record["idb"]),
                        "label": record["rel"]
                    }
                })
            return list(nodes.values()), edges

    def add_data(self, mahasiswa, matakuliah, dosen, ruangan, slot):
        with self.driver.session() as session:
            session.run("""
            MERGE (m:Mahasiswa {nama: $mahasiswa})
            MERGE (c:Matakuliah {nama: $matakuliah})
            MERGE (d:Dosen {nama: $dosen})
            MERGE (r:Ruang {nama: $ruangan})
            MERGE (s:Slot {waktu: $slot})
            MERGE (m)-[:MENGAMBIL]->(c)
            MERGE (d)-[:MENGAJAR]->(c)
            MERGE (c)-[:BUTUH_RUANGAN]->(r)
            MERGE (c)-[:DIJADWALKAN_PADA]->(s)
        """, mahasiswa=mahasiswa, matakuliah=matakuliah,
             dosen=dosen, ruangan=ruangan, slot=slot)


    def get_all_course_students(self):
        query = """
        MATCH (m:Mahasiswa)-[:MENGAMBIL]->(k:Kelas)-[:UNTUK]->(mk:Matakuliah)
        RETURN mk.nama AS matkul, collect(DISTINCT m.nama) AS mahasiswa
        """
        with self.driver.session() as session:
            result = session.run(query)
            course_students = {}
            for record in result:
                course_students[record["matkul"]] = record["mahasiswa"]
            return course_students

