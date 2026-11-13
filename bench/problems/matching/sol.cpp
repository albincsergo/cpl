#include "../../fastio.h"
using namespace std;
const long long MOD = 1000000007;
int main() {
    io::setup();
    int n = io::readInt();
    vector<int> compatible(n * n);
    for (auto &x : compatible) x = io::readInt();
    vector<long long> ways(1 << n, 0);
    ways[0] = 1;
    for (int mask = 1; mask < (1 << n); mask++) {
        int man = __builtin_popcount(mask) - 1;
        long long total = 0;
        for (int woman = 0; woman < n; woman++)
            if ((mask >> woman & 1) != 0 && compatible[man * n + woman] == 1) total += ways[mask ^ (1 << woman)];
        ways[mask] = total % MOD;
    }
    io::writeLong(ways[(1 << n) - 1]); io::writeChar('\n');
}
