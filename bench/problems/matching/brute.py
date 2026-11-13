from itertools import permutations
def solve(text):
    data = list(map(int, text.split())); n = data[0]; a = [data[1 + i * n:1 + (i + 1) * n] for i in range(n)]
    return f"{sum(all(a[i][p[i]] for i in range(n)) for p in permutations(range(n))) % (10**9 + 7)}\n"
