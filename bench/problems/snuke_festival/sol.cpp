#include "../../fastio.h"
using namespace std;
int main() {
    io::setup();
    int n = io::readInt();
    vector<int> a(n), b(n), c(n);
    for (auto &x : a) x = io::readInt();
    for (auto &x : b) x = io::readInt();
    for (auto &x : c) x = io::readInt();
    sort(a.begin(), a.end()); sort(c.begin(), c.end());
    long long total = 0;
    for (int x : b) total += (long long)(lower_bound(a.begin(), a.end(), x) - a.begin()) * (n - (upper_bound(c.begin(), c.end(), x) - c.begin()));
    io::writeLong(total); io::writeChar('\n');
}
