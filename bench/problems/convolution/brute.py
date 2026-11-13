MOD = 998244353
def solve(text):
    data = list(map(int, text.split())); n, m = data[0], data[1]
    a = data[2:2 + n]; b = data[2 + n:2 + n + m]; c = [0] * (n + m - 1)
    for i in range(n):
        for j in range(m): c[i + j] = (c[i + j] + a[i] * b[j]) % MOD
    return " ".join(map(str, c)) + "\n"
