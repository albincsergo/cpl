#include "../../fastio.h"
using namespace std;
int main() {
    io::setup();
    int t = io::readInt();
    while (t--) {
        int n = io::readInt();
        unordered_map<int, int> count;
        long long pairs = 0;
        for (int i = 0; i < n; i++) {
            int a = io::readInt();
            int &c = count[a - i];
            pairs += c;
            c++;
        }
        io::writeLong(pairs); io::writeChar('\n');
    }
}
