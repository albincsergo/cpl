# any shortest path is accepted, so check the output's validity and length
import heapq
def check(text, output):
    data = list(map(int, text.split())); n, m = data[0], data[1]
    best = {}; adjacency = [[] for _ in range(n + 1)]
    for i in range(m):
        a, b, w = data[2 + 3 * i: 5 + 3 * i]
        for x, y in ((a, b), (b, a)):
            best[(x, y)] = min(best.get((x, y), w), w); adjacency[x].append((y, w))
    dist = [None] * (n + 1); dist[1] = 0; heap = [(0, 1)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]: continue
        for v, w in adjacency[u]:
            if dist[v] is None or d + w < dist[v]: dist[v] = d + w; heapq.heappush(heap, (d + w, v))
    path = list(map(int, output.split()))
    if dist[n] is None: return None if path == [-1] else "there is no path, expected -1"
    if not path or path[0] != 1 or path[-1] != n: return "the path must go from 1 to n"
    length = 0
    for x, y in zip(path, path[1:]):
        if (x, y) not in best: return f"there is no edge {x}-{y}"
        length += best[(x, y)]
    return None if length == dist[n] else f"path length {length}, shortest is {dist[n]}"
