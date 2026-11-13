#include "../../fastio.h"
using namespace std;
int main() {
    io::setup();
    int n = io::readInt();
    vector<double> chance(n + 1, 0.0);
    chance[0] = 1;
    for (int i = 0; i < n; i++) {
        double p = stod(io::readWord());
        for (int k = i + 1; k > 0; k--) chance[k] = chance[k] * (1 - p) + chance[k - 1] * p;
        chance[0] *= 1 - p;
    }
    double answer = 0;
    for (int k = n / 2 + 1; k <= n; k++) answer += chance[k];
    char buffer[64];
    snprintf(buffer, sizeof(buffer), "%.10f", answer);
    io::writeString(buffer); io::writeChar('\n');
}
