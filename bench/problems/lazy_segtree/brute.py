MOD = 998244353
def solve(text):
    data = list(map(int, text.split())); n, q = data[0], data[1]
    a = data[2:2 + n]; pos = 2 + n; out = []
    for _ in range(q):
        if data[pos] == 0:
            _, l, r, b, c = data[pos:pos + 5]; pos += 5
            for i in range(l, r): a[i] = (b * a[i] + c) % MOD
        else:
            _, l, r = data[pos:pos + 3]; pos += 3
            out.append(str(sum(a[l:r]) % MOD))
    return "".join(s + "\n" for s in out)
