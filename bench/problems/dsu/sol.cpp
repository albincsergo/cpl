#include "../../fastio.h"
using namespace std;
vector<int> parent, sz;
int find(int x) {
    while (parent[x] != x) { parent[x] = parent[parent[x]]; x = parent[x]; }
    return x;
}
int main() {
    io::setup();
    int n = io::readInt(), q = io::readInt();
    parent.assign(n, 0); sz.assign(n, 1);
    for (int i = 0; i < n; i++) parent[i] = i;
    for (int k = 0; k < q; k++) {
        int t = io::readInt(), u = io::readInt(), v = io::readInt();
        int a = find(u), b = find(v);
        if (t == 0) {
            if (a != b) { if (sz[a] < sz[b]) swap(a, b); parent[b] = a; sz[a] += sz[b]; }
        } else { io::writeLong(a == b ? 1 : 0); io::writeChar('\n'); }
    }
}
