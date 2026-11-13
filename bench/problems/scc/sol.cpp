#include "../../fastio.h"
using namespace std;
vector<int> start_, adj, order_, low, stk, comp;
vector<char> onStack;
int counter = 0, components = 0;
void dfs(int v) {
    order_[v] = low[v] = ++counter;
    stk.push_back(v); onStack[v] = 1;
    for (int k = start_[v]; k < start_[v + 1]; k++) {
        int u = adj[k];
        if (order_[u] == 0) { dfs(u); low[v] = min(low[v], low[u]); }
        else if (onStack[u]) low[v] = min(low[v], order_[u]);
    }
    if (low[v] == order_[v]) {
        while (true) {
            int u = stk.back(); stk.pop_back(); onStack[u] = 0; comp[u] = components;
            if (u == v) break;
        }
        components++;
    }
}
int main() {
    io::setup();
    int n = io::readInt(), m = io::readInt();
    vector<int> from(m), to(m);
    start_.assign(n + 1, 0);
    for (int i = 0; i < m; i++) { from[i] = io::readInt(); to[i] = io::readInt(); start_[from[i] + 1]++; }
    for (int v = 0; v < n; v++) start_[v + 1] += start_[v];
    vector<int> fill(start_.begin(), start_.begin() + n);
    adj.assign(m, 0);
    for (int i = 0; i < m; i++) adj[fill[from[i]]++] = to[i];
    order_.assign(n, 0); low.assign(n, 0); comp.assign(n, 0); onStack.assign(n, 0);
    for (int v = 0; v < n; v++) if (order_[v] == 0) dfs(v);
    vector<int> count(components, 0);
    for (int v = 0; v < n; v++) count[components - 1 - comp[v]]++;
    vector<int> lineStart(components + 1, 0);
    for (int j = 0; j < components; j++) lineStart[j + 1] = lineStart[j] + count[j];
    vector<int> next_(lineStart.begin(), lineStart.begin() + components), grouped(n);
    for (int v = 0; v < n; v++) { int j = components - 1 - comp[v]; grouped[next_[j]++] = v; }
    io::writeLong(components); io::writeChar('\n');
    for (int j = 0; j < components; j++) {
        io::writeLong(count[j]);
        for (int k = lineStart[j]; k < lineStart[j + 1]; k++) { io::writeChar(' '); io::writeLong(grouped[k]); }
        io::writeChar('\n');
    }
}
