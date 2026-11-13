#include "../../fastio.h"
using namespace std;
int main() {
    io::setup();
    string s = io::readWord();
    int n = (int)s.size() + 1;
    vector<int> text(n, 0);
    for (int i = 0; i + 1 < n; i++) text[i] = s[i] - 'a' + 1;
    int alphabet = max(27, n);
    vector<int> sa(n), cls(n), count(alphabet, 0);
    for (int i = 0; i < n; i++) count[text[i]]++;
    for (int i = 1; i < 27; i++) count[i] += count[i - 1];
    for (int i = n - 1; i >= 0; i--) sa[--count[text[i]]] = i;
    int classes = 1;
    cls[sa[0]] = 0;
    for (int i = 1; i < n; i++) { if (text[sa[i]] != text[sa[i - 1]]) classes++; cls[sa[i]] = classes - 1; }
    vector<int> shifted(n), newCls(n);
    for (int k = 1; k < n && classes < n; k *= 2) {
        for (int i = 0; i < n; i++) { shifted[i] = sa[i] - k; if (shifted[i] < 0) shifted[i] += n; }
        fill(count.begin(), count.begin() + classes, 0);
        for (int i = 0; i < n; i++) count[cls[shifted[i]]]++;
        for (int i = 1; i < classes; i++) count[i] += count[i - 1];
        for (int i = n - 1; i >= 0; i--) sa[--count[cls[shifted[i]]]] = shifted[i];
        newCls[sa[0]] = 0; classes = 1;
        for (int i = 1; i < n; i++) {
            int a = sa[i] + k, b = sa[i - 1] + k;
            if (a >= n) a -= n;
            if (b >= n) b -= n;
            if (cls[sa[i]] != cls[sa[i - 1]] || cls[a] != cls[b]) classes++;
            newCls[sa[i]] = classes - 1;
        }
        swap(cls, newCls);
    }
    long long lcpTotal = 0; int h = 0;
    for (int i = 0; i < n - 1; i++) {
        int j = sa[cls[i] - 1];
        while (text[i + h] == text[j + h]) h++;
        lcpTotal += h;
        if (h > 0) h--;
    }
    long long length = n - 1;
    io::writeLong(length * (length + 1) / 2 - lcpTotal); io::writeChar('\n');
}
