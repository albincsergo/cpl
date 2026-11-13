def solve(text):
    data = list(map(int, text.split())); n, q = data[0], data[1]
    a = data[2:2 + n]; pos = 2 + n; out = []
    for _ in range(q):
        t, x, y = data[pos:pos + 3]; pos += 3
        if t == 0: a[x] += y
        else: out.append(str(sum(a[x:y])))
    return "".join(x + "\n" for x in out)
