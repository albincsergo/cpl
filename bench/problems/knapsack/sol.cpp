#include "../../fastio.h"
using namespace std;
int main() {
    io::setup();
    int n = io::readInt(), capacity = io::readInt();
    vector<long long> best(capacity + 1, 0);
    for (int k = 0; k < n; k++) {
        int w = io::readInt(); long long v = io::readLong();
        for (int c = capacity; c > w - 1; c--) best[c] = max(best[c], best[c - w] + v);
    }
    io::writeLong(best[capacity]); io::writeChar('\n');
}
