# checks the output instead of reproducing it: the components must be right and in topological order
def components(n, edges):
    reach = [[False] * n for _ in range(n)]
    for v in range(n): reach[v][v] = True
    for a, b in edges: reach[a][b] = True
    for k in range(n):
        for i in range(n):
            if reach[i][k]:
                for j in range(n):
                    if reach[k][j]: reach[i][j] = True
    return reach

def check(text, output):
    data = list(map(int, text.split())); n, m = data[0], data[1]
    edges = [(data[2 + 2 * i], data[3 + 2 * i]) for i in range(m)]
    reach = components(n, edges)
    tokens = list(map(int, output.split())); k = tokens[0]; pos = 1; line = {}
    for j in range(k):
        size = tokens[pos]; members = tokens[pos + 1: pos + 1 + size]; pos += 1 + size
        for v in members: line[v] = j
        for a in members:
            for b in members:
                if not (reach[a][b] and reach[b][a]): return f"{a} and {b} are not strongly connected"
    if sorted(line) != list(range(n)): return "not every vertex appears exactly once"
    for a in range(n):
        for b in range(n):
            if a != b and reach[a][b] and reach[b][a] and line[a] != line[b]: return f"{a} and {b} should share a component"
    for a, b in edges:
        if line[b] < line[a]: return f"edge {a} -> {b} goes backwards"
    return None
