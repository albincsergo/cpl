#include "../../fastio.h"
using namespace std;
int main() {
    io::setup();
    int n = io::readInt(), m = io::readInt();
    vector<vector<pair<int, int>>> graph(n + 1);
    for (int k = 0; k < m; k++) {
        int a = io::readInt(), b = io::readInt(), w = io::readInt();
        graph[a].push_back({b, w}); graph[b].push_back({a, w});
    }
    const long long INF = (long long)1e18;
    vector<long long> distance(n + 1, INF);
    vector<int> parent(n + 1, 0);
    priority_queue<pair<long long, int>, vector<pair<long long, int>>, greater<>> queue;
    distance[1] = 0; queue.push({0, 1});
    while (!queue.empty()) {
        auto [d, u] = queue.top(); queue.pop();
        if (d > distance[u]) continue;
        for (auto [to, w] : graph[u]) {
            long long next = d + w;
            if (next < distance[to]) { distance[to] = next; parent[to] = u; queue.push({next, to}); }
        }
    }
    if (distance[n] == INF) { io::writeLong(-1); io::writeChar('\n'); return 0; }
    vector<int> path;
    for (int v = n; v != 1; v = parent[v]) path.push_back(v);
    path.push_back(1);
    reverse(path.begin(), path.end());
    for (size_t i = 0; i < path.size(); i++) { if (i) io::writeChar(' '); io::writeLong(path[i]); }
    io::writeChar('\n');
}
