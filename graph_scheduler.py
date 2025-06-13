import networkx as nx

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

def schedule_courses(course_students, time_slots):
    G = build_conflict_graph(course_students)
    coloring = nx.coloring.greedy_color(G, strategy="saturation_largest_first")
    slot_mapping = {}
    for course, color in coloring.items():
        slot = time_slots[color % len(time_slots)]
        slot_mapping[course] = slot
    return slot_mapping
