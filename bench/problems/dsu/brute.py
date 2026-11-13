def solve(text):
    data = list(map(int, text.split())); n, q = data[0], data[1]
    comp = list(range(n)); out = []
    for i in range(q):
        t, u, v = data[2 + 3 * i: 5 + 3 * i]
        if t == 0:
            old, new = comp[v], comp[u]
            comp = [new if c == old else c for c in comp]
        else:
            out.append("1" if comp[u] == comp[v] else "0")
    return "".join(x + "\n" for x in out)
