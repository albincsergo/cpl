#include "../../fastio.h"
using namespace std;
vector<int> tree_, values;
void build(int node, int l, int r) {
    if (l == r) { tree_[node] = values[l]; return; }
    int m = (l + r) / 2; build(2 * node, l, m); build(2 * node + 1, m + 1, r);
    tree_[node] = max(tree_[2 * node], tree_[2 * node + 1]);
}
void update(int node, int l, int r, int p, int v) {
    if (l == r) { tree_[node] = v; return; }
    int m = (l + r) / 2;
    if (p <= m) update(2 * node, l, m, p, v); else update(2 * node + 1, m + 1, r, p, v);
    tree_[node] = max(tree_[2 * node], tree_[2 * node + 1]);
}
int query(int node, int l, int r, int ql, int qr) {
    if (qr < l || r < ql) return -1;
    if (ql <= l && r <= qr) return tree_[node];
    int m = (l + r) / 2;
    return max(query(2 * node, l, m, ql, qr), query(2 * node + 1, m + 1, r, ql, qr));
}
int first(int node, int l, int r, int from, int v) {
    if (r < from || tree_[node] < v) return -1;
    if (l == r) return l;
    int m = (l + r) / 2;
    int left = first(2 * node, l, m, from, v);
    if (left != -1) return left;
    return first(2 * node + 1, m + 1, r, from, v);
}
int main() {
    io::setup();
    int n = io::readInt(), q = io::readInt();
    values.assign(n + 1, 0);
    for (int i = 1; i <= n; i++) values[i] = io::readInt();
    tree_.assign(4 * n + 4, 0);
    build(1, 1, n);
    for (int k = 0; k < q; k++) {
        int t = io::readInt(), a = io::readInt(), b = io::readInt();
        if (t == 1) update(1, 1, n, a, b);
        else if (t == 2) { io::writeLong(query(1, 1, n, a, b)); io::writeChar('\n'); }
        else { int j = first(1, 1, n, a, b); io::writeLong(j == -1 ? n + 1 : j); io::writeChar('\n'); }
    }
}
