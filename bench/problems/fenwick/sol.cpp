#include "../../fastio.h"
using namespace std;
vector<long long> tree_; int n;
void add(int p, long long x) { for (p++; p <= n; p += p & -p) tree_[p] += x; }
long long prefix(int p) { long long total = 0; for (; p > 0; p -= p & -p) total += tree_[p]; return total; }
int main() {
    io::setup();
    n = io::readInt(); int q = io::readInt();
    tree_.assign(n + 1, 0);
    for (int i = 0; i < n; i++) add(i, io::readLong());
    for (int k = 0; k < q; k++) {
        int t = io::readInt(), a = io::readInt(), b = io::readInt();
        if (t == 0) add(a, b); else { io::writeLong(prefix(b) - prefix(a)); io::writeChar('\n'); }
    }
}
