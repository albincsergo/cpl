def solve(text):
    data = list(map(int, text.split())); t = data[0]; pos = 1; out = []
    for _ in range(t):
        n = data[pos]; a = data[pos + 1:pos + 1 + n]; pos += 1 + n
        out.append(str(sum(1 for i in range(n) for j in range(i + 1, n) if a[j] - a[i] == j - i)))
    return "".join(s + "\n" for s in out)
