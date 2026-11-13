#include "../../fastio.h"
using namespace std;
const long long MOD = 998244353;
long long power(long long base, long long exponent) {
    long long result = 1; base %= MOD;
    while (exponent > 0) { if (exponent & 1) result = result * base % MOD; base = base * base % MOD; exponent >>= 1; }
    return result;
}
void ntt(vector<long long> &a, bool invert) {
    int n = (int)a.size();
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) swap(a[i], a[j]);
    }
    for (int length = 2; length <= n; length <<= 1) {
        long long w = power(3, (MOD - 1) / length);
        if (invert) w = power(w, MOD - 2);
        int half = length / 2;
        vector<long long> roots(half);
        roots[0] = 1;
        for (int k = 1; k < half; k++) roots[k] = roots[k - 1] * w % MOD;
        for (int i = 0; i < n; i += length)
            for (int k = 0; k < half; k++) {
                long long u = a[i + k], v = a[i + k + half] * roots[k] % MOD;
                a[i + k] = u + v < MOD ? u + v : u + v - MOD;
                a[i + k + half] = u - v >= 0 ? u - v : u - v + MOD;
            }
    }
    if (invert) { long long inverse = power(n, MOD - 2); for (auto &x : a) x = x * inverse % MOD; }
}
int main() {
    io::setup();
    int n = io::readInt(), m = io::readInt();
    int size = 1;
    while (size < n + m - 1) size <<= 1;
    vector<long long> a(size, 0), b(size, 0);
    for (int i = 0; i < n; i++) a[i] = io::readLong();
    for (int i = 0; i < m; i++) b[i] = io::readLong();
    ntt(a, false); ntt(b, false);
    for (int i = 0; i < size; i++) a[i] = a[i] * b[i] % MOD;
    ntt(a, true);
    for (int i = 0; i < n + m - 1; i++) { if (i) io::writeChar(' '); io::writeLong(a[i]); }
    io::writeChar('\n');
}
