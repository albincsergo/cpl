#include "../../fastio.h"
using namespace std;
int main() {
    io::setup();
    string s = io::readWord(), goodness = io::readWord();
    int k = io::readInt(), n = s.size();
    const long long MOD1 = 1000000007, MOD2 = 998244353;
    vector<long long> hashes;
    for (int i = 0; i < n; i++) {
        long long h1 = 0, h2 = 0; int bad = 0;
        for (int j = i; j < n; j++) {
            int c = s[j] - 'a';
            if (goodness[c] == '0') bad++;
            if (bad > k) break;
            h1 = (h1 * 131 + c + 1) % MOD1;
            h2 = (h2 * 137 + c + 1) % MOD2;
            hashes.push_back(h1 * MOD2 + h2);
        }
    }
    sort(hashes.begin(), hashes.end());
    int distinct = 0;
    for (size_t i = 0; i < hashes.size(); i++) if (i == 0 || hashes[i] != hashes[i - 1]) distinct++;
    io::writeLong(distinct); io::writeChar('\n');
}
