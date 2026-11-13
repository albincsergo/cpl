#include "../../fastio.h"
using namespace std;
int main() {
    io::setup();
    int n = io::readInt();
    unordered_map<string, int> seen;
    for (int k = 0; k < n; k++) {
        string name = io::readWord();
        int &times = seen[name];
        if (times == 0) io::writeString("OK"); else { io::writeString(name); io::writeLong(times); }
        io::writeChar('\n');
        times++;
    }
}
