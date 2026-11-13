#include "../../fastio.h"
using namespace std;
int main() {
    io::setup();
    string s = io::readWord(), t = io::readWord();
    int n = s.size(), m = t.size(), width = m + 1;
    vector<int> dp((n + 1) * width, 0);
    for (int i = 1; i <= n; i++) {
        char a = s[i - 1];
        for (int j = 1; j <= m; j++) {
            if (a == t[j - 1]) dp[i * width + j] = dp[(i - 1) * width + j - 1] + 1;
            else dp[i * width + j] = max(dp[(i - 1) * width + j], dp[i * width + j - 1]);
        }
    }
    vector<char> answer;
    int i = n, j = m;
    while (i > 0 && j > 0) {
        if (s[i - 1] == t[j - 1]) { answer.push_back(s[i - 1]); i--; j--; }
        else if (dp[(i - 1) * width + j] >= dp[i * width + j - 1]) i--;
        else j--;
    }
    reverse(answer.begin(), answer.end());
    for (char c : answer) io::writeChar(c);
    io::writeChar('\n');
}
