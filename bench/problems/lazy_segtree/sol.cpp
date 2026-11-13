#include "../../fastio.h"
using namespace std;
const long long MOD = 998244353;
vector<long long> sum_, mul_, add_, values;
void apply_(int node, int length, long long b, long long c) {
    sum_[node] = (sum_[node] * b + c * length) % MOD;
    mul_[node] = mul_[node] * b % MOD;
    add_[node] = (add_[node] * b + c) % MOD;
}
void push(int node, int l, int r) {
    if (mul_[node] == 1 && add_[node] == 0) return;
    int m = (l + r) / 2;
    apply_(2 * node, m - l + 1, mul_[node], add_[node]);
    apply_(2 * node + 1, r - m, mul_[node], add_[node]);
    mul_[node] = 1; add_[node] = 0;
}
void build(int node, int l, int r) {
    mul_[node] = 1;
    if (l == r) { sum_[node] = values[l]; return; }
    int m = (l + r) / 2; build(2 * node, l, m); build(2 * node + 1, m + 1, r);
    sum_[node] = (sum_[2 * node] + sum_[2 * node + 1]) % MOD;
}
void update(int node, int l, int r, int ql, int qr, long long b, long long c) {
    if (qr < l || r < ql) return;
    if (ql <= l && r <= qr) { apply_(node, r - l + 1, b, c); return; }
    push(node, l, r);
    int m = (l + r) / 2;
    update(2 * node, l, m, ql, qr, b, c); update(2 * node + 1, m + 1, r, ql, qr, b, c);
    sum_[node] = (sum_[2 * node] + sum_[2 * node + 1]) % MOD;
}
long long query(int node, int l, int r, int ql, int qr) {
    if (qr < l || r < ql) return 0;
    if (ql <= l && r <= qr) return sum_[node];
    push(node, l, r);
    int m = (l + r) / 2;
    return (query(2 * node, l, m, ql, qr) + query(2 * node + 1, m + 1, r, ql, qr)) % MOD;
}
int main() {
    io::setup();
    int n = io::readInt(), q = io::readInt();
    values.assign(n, 0);
    for (int i = 0; i < n; i++) values[i] = io::readLong();
    sum_.assign(4 * n, 0); mul_.assign(4 * n, 0); add_.assign(4 * n, 0);
    build(1, 0, n - 1);
    for (int k = 0; k < q; k++) {
        int t = io::readInt(), l = io::readInt(), r = io::readInt();
        if (t == 0) { long long b = io::readLong(), c = io::readLong(); update(1, 0, n - 1, l, r - 1, b, c); }
        else { io::writeLong(query(1, 0, n - 1, l, r - 1)); io::writeChar('\n'); }
    }
}
