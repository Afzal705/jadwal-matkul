import networkx as nx
import time
from collections import defaultdict
from neo4j import GraphDatabase

# ===================== 1. Bangun graf konflik dari relasi mahasiswa - kelas =====================
def build_conflict_graph(course_students):
    G = nx.Graph()
    courses = list(course_students.keys())
    G.add_nodes_from(courses)
    for i in range(len(courses)):
        for j in range(i + 1, len(courses)):
            c1, c2 = courses[i], courses[j]
            if set(course_students[c1]) & set(course_students[c2]):
                G.add_edge(c1, c2)
    return G

# ===================== 2. Penjadwalan dengan greedy coloring =====================
def schedule_courses(course_students, time_slots):
    G = build_conflict_graph(course_students)
    coloring = nx.coloring.greedy_color(G, strategy="saturation_largest_first")
    slot_mapping = {}
    for course, color in coloring.items():
        slot = time_slots[color % len(time_slots)]
        slot_mapping[course] = slot
    return slot_mapping

# ===================== 3. Ambil struktur graf untuk visualisasi =====================
def get_graph_data(course_students):
    G = build_conflict_graph(course_students)
    graph_data = []
    for node in G.nodes():
        graph_data.append({"data": {"id": node}})
    for u, v in G.edges():
        graph_data.append({"data": {"source": u, "target": v}})
    return graph_data

# ===================== 4. Pewarnaan graf: Welsh-Powell =====================
def welsh_powell_coloring(G):
    sorted_nodes = sorted(G.nodes(), key=lambda x: G.degree(x), reverse=True)
    coloring = {}
    current_color = 0

    for node in sorted_nodes:
        if node in coloring:
            continue
        coloring[node] = current_color
        for other in sorted_nodes:
            if other not in coloring and all(coloring.get(neigh) != current_color for neigh in G.neighbors(other)):
                coloring[other] = current_color
        current_color += 1

    return coloring

# ===================== 5. Evaluasi hasil pewarnaan graf =====================
def evaluate_coloring(G, coloring):
    num_colors = len(set(coloring.values()))
    conflict_edges = sum(1 for u, v in G.edges() if coloring.get(u) == coloring.get(v))
    total_edges = G.number_of_edges()
    conflict_percentage = (conflict_edges / total_edges * 100) if total_edges else 0

    color_distribution = defaultdict(int)
    for color in coloring.values():
        color_distribution[color] += 1

    return {
        "num_colors": num_colors,
        "conflict_percentage": conflict_percentage,
        "color_distribution": dict(color_distribution)
    }

# ===================== 6. Hapus semua relasi jadwal slot kelas =====================
def reset_slot_relations(driver):
    with driver.session() as session:
        session.run("""
            MATCH (:Kelas)-[r:DIJADWALKAN_PADA]->()
            DELETE r
        """)

# ===================== 7. Terapkan hasil pewarnaan ke dalam DB =====================
def apply_coloring_to_db(driver, coloring, time_slots):
    with driver.session() as session:
        for course, color in coloring.items():
            slot_waktu = time_slots[color % len(time_slots)]
            session.run("""
                MATCH (m:Matakuliah {nama: $nama})
                MATCH (k:Kelas)-[:UNTUK]->(m)
                MATCH (s:Slot {waktu: $slot})
                MERGE (k)-[:DIJADWALKAN_PADA]->(s)
            """, nama=course, slot=slot_waktu)

# ===================== 8. Jalankan evaluasi lengkap kedua algoritma =====================
def compare_algorithms(course_students, time_slots, driver):
    G = build_conflict_graph(course_students)

    # ---------- Greedy ----------
    reset_slot_relations(driver)
    # start_greedy = time.time()
    start_greedy = time.perf_counter()
    greedy_coloring = nx.coloring.greedy_color(G, strategy="saturation_largest_first")
    # greedy_time = time.time() - start_greedy
    greedy_time = time.perf_counter() - start_greedy
    apply_coloring_to_db(driver, greedy_coloring, time_slots)
    greedy_eval = evaluate_coloring(G, greedy_coloring)

    # ---------- Welsh-Powell ----------
    reset_slot_relations(driver)
    # start_wp = time.time()
    start_wp = time.perf_counter()
    wp_coloring = welsh_powell_coloring(G)
    # wp_time = time.time() - start_wp
    wp_time = time.perf_counter() - start_wp
    apply_coloring_to_db(driver, wp_coloring, time_slots)
    wp_eval = evaluate_coloring(G, wp_coloring)

    return {
        "greedy": {
            "coloring": greedy_coloring,
            "eval": greedy_eval,
            "time": greedy_time
        },
        "welsh_powell": {
            "coloring": wp_coloring,
            "eval": wp_eval,
            "time": wp_time
        }
    }
