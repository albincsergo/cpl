from itertools import combinations
def solve(text):
    data = list(map(int, text.split())); n, W = data[0], data[1]
    items = [(data[2 + 2 * i], data[3 + 2 * i]) for i in range(n)]; best = 0
    for r in range(n + 1):
        for pick in combinations(items, r):
            if sum(w for w, v in pick) <= W: best = max(best, sum(v for w, v in pick))
    return f"{best}\n"
