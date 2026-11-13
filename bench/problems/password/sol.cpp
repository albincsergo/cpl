#include "../../fastio.h"
using namespace std;
int main() {
    io::setup();
    string s = io::readWord();
    int n = s.size();
    vector<int> pi(n, 0);
    for (int i = 1; i < n; i++) {
        int k = pi[i - 1];
        while (k > 0 && s[i] != s[k]) k = pi[k - 1];
        if (s[i] == s[k]) k++;
        pi[i] = k;
    }
    int border = pi[n - 1];
    if (border > 0) {
        for (int i = 0; i < n - 1; i++)
            if (pi[i] == border) { io::writeString(s.substr(0, border)); io::writeChar('\n'); return 0; }
        border = pi[border - 1];
    }
    if (border > 0) io::writeString(s.substr(0, border)); else io::writeString("Just a legend");
    io::writeChar('\n');
}
