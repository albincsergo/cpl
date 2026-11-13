def solve(text):
    data = list(map(int, text.split())); n, q = data[0], data[1]
    a = [0] + data[2:2 + n]; pos = 2 + n; out = []
    for _ in range(q):
        t, x, y = data[pos:pos + 3]; pos += 3
        if t == 1: a[x] = y
        elif t == 2: out.append(str(max(a[x:y + 1])))
        else: out.append(str(next((j for j in range(x, n + 1) if a[j] >= y), n + 1)))
    return "".join(s + "\n" for s in out)
