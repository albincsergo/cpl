# CPL vs C++ on competitive programming problems

17 real problems from AtCoder and Codeforces, each solved twice with **the same algorithm**: once in CPL (`sol.cpl`) and once in C++ (`sol.cpp`). The rules:

- **Same algorithm, same complexity, same tie-breaking.** Outputs are compared byte for byte. The three problems that accept several answers (SCC, LCS and Codeforces 20C) also have checkers, which are used when the outputs differ.
- **Same class of I/O.** CPL's runtime reads with buffered `read()`, so the main C++ build uses an equivalent buffered reader and writer (`fastio.h`, built with `-DFAST_IO`). The `C++ (cin)` column is the same source with `cin`/`cout` and `sync_with_stdio(false)`, which is what most submissions use.
- **Judge settings.** `g++ -O2` (what Codeforces and AtCoder use) and `cpl build -O2`, with an unlimited stack for both, as judges allow.
- **Verified first.** `run.py verify` runs every sample plus 200 random small tests per problem against a brute force or checker, for all three builds. `run.py bench` only times max-size tests, after checking that CPL's output equals C++'s.

Times are wall clock, best of 7 runs, on one Linux machine (x86-64, 8 cores); memory is peak RSS. Expect a few percent of noise between runs, so results within about 5% are a tie.

## Results

| Problem | Test | C++ (fast I/O) | C++ (cin) | CPL | CPL vs C++ |
|---|---|---|---|---|---|
| coins | random | 11 ms, 3 MB | 10 ms, 3 MB | 6 ms, 1 MB | 2.00x faster |
| convolution | random | 214 ms, 23 MB | 319 ms, 23 MB | 218 ms, 43 MB | 1.02x slower |
| dijkstra_path | random | 45 ms, 10 MB | 67 ms, 10 MB | 42 ms, 13 MB | 1.06x faster |
| dijkstra_path | long_path | 33 ms, 10 MB | 49 ms, 10 MB | 19 ms, 13 MB | 1.76x faster |
| dsu | random | 14 ms, 4 MB | 45 ms, 4 MB | 11 ms, 4 MB | 1.21x faster |
| dsu | chain | 10 ms, 4 MB | 42 ms, 4 MB | 10 ms, 4 MB | 1.02x faster |
| fenwick | random | 69 ms, 7 MB | 193 ms, 6 MB | 63 ms, 6 MB | 1.09x faster |
| good_substrings | all_good | 95 ms, 20 MB | 95 ms, 20 MB | 96 ms, 11 MB | 1.01x slower |
| good_substrings | random | 69 ms, 12 MB | 71 ms, 12 MB | 69 ms, 9 MB | 1.00x faster |
| knapsack | random | 9 ms, 3 MB | 9 ms, 3 MB | 8 ms, 2 MB | 1.00x faster |
| lazy_segtree | random | 832 ms, 53 MB | 1054 ms, 52 MB | 717 ms, 33 MB | 1.16x faster |
| lcs | random | 21 ms, 37 MB | 21 ms, 37 MB | 18 ms, 37 MB | 1.15x faster |
| lcs | two_letters | 34 ms, 37 MB | 35 ms, 37 MB | 34 ms, 37 MB | 1.01x faster |
| matching | all_compatible | 129 ms, 18 MB | 126 ms, 18 MB | 124 ms, 19 MB | 1.04x faster |
| matching | random | 149 ms, 18 MB | 145 ms, 18 MB | 148 ms, 19 MB | 1.01x faster |
| password | periodic | 12 ms, 9 MB | 8 ms, 8 MB | 9 ms, 9 MB | 1.25x faster |
| password | random | 9 ms, 7 MB | 7 ms, 7 MB | 8 ms, 8 MB | 1.08x faster |
| password | all_a | 13 ms, 9 MB | 8 ms, 8 MB | 10 ms, 9 MB | 1.29x faster |
| registration | few_names | 16 ms, 4 MB | 23 ms, 3 MB | 18 ms, 8 MB | 1.13x slower |
| registration | distinct | 86 ms, 15 MB | 72 ms, 15 MB | 50 ms, 21 MB | 1.73x faster |
| same_differences | many_tests | 14 ms, 3 MB | 26 ms, 3 MB | 17 ms, 12 MB | 1.27x slower |
| same_differences | one_big_test | 7 ms, 3 MB | 22 ms, 3 MB | 6 ms, 1 MB | 1.28x faster |
| scc | random | 110 ms, 27 MB | 204 ms, 26 MB | 92 ms, 27 MB | 1.20x faster |
| scc | long_cycle | 186 ms, 61 MB | 267 ms, 60 MB | 116 ms, 48 MB | 1.60x faster |
| scc | dag_path | 83 ms, 67 MB | 170 ms, 66 MB | 41 ms, 54 MB | 2.03x faster |
| segtree | random | 58 ms, 7 MB | 113 ms, 6 MB | 55 ms, 5 MB | 1.05x faster |
| snuke_festival | random | 38 ms, 4 MB | 56 ms, 3 MB | 40 ms, 4 MB | 1.07x slower |
| snuke_festival | small_values | 33 ms, 4 MB | 46 ms, 3 MB | 33 ms, 4 MB | 1.01x slower |
| suffix_array | random | 50 ms, 15 MB | 46 ms, 15 MB | 45 ms, 14 MB | 1.10x faster |
| suffix_array | few_letters | 64 ms, 14 MB | 63 ms, 15 MB | 57 ms, 14 MB | 1.12x faster |
| suffix_array | all_a | 78 ms, 14 MB | 79 ms, 15 MB | 77 ms, 14 MB | 1.01x faster |

| Problem | Source | What it exercises |
|---|---|---|
| dsu | [ALPC A](https://atcoder.jp/contests/practice2/tasks/practice2_a) | union-find, 2·10⁵ queries |
| fenwick | [ALPC B](https://atcoder.jp/contests/practice2/tasks/practice2_b) | Fenwick tree, 10⁶ numbers of input |
| segtree | [ALPC J](https://atcoder.jp/contests/practice2/tasks/practice2_j) | recursive segment tree with descent |
| lazy_segtree | [ALPC K](https://atcoder.jp/contests/practice2/tasks/practice2_k) | lazy propagation, modular arithmetic, 5·10⁵ queries |
| scc | [ALPC G](https://atcoder.jp/contests/practice2/tasks/practice2_g) | recursive Tarjan, recursion 5·10⁵ deep |
| suffix_array | [ALPC I](https://atcoder.jp/contests/practice2/tasks/practice2_i) | suffix array by prefix doubling, LCP, 5·10⁵ characters |
| convolution | [ALPC F](https://atcoder.jp/contests/practice2/tasks/practice2_f) | NTT over 2²⁰ elements |
| lcs | [EDPC F](https://atcoder.jp/contests/dp/tasks/dp_f) | 3000 × 3000 string DP with reconstruction |
| knapsack | [EDPC D](https://atcoder.jp/contests/dp/tasks/dp_d) | 1D DP, 10⁷ transitions |
| matching | [EDPC O](https://atcoder.jp/contests/dp/tasks/dp_o) | bitmask DP over 2²¹ masks with popcount |
| coins | [EDPC I](https://atcoder.jp/contests/dp/tasks/dp_i) | floating point DP, fixed precision output |
| password | [CF 126B](https://codeforces.com/problemset/problem/126/B) | prefix function on 10⁶ characters |
| registration | [CF 4C](https://codeforces.com/problemset/problem/4/C) | hash map with string keys |
| dijkstra_path | [CF 20C](https://codeforces.com/problemset/problem/20/C) | Dijkstra with a priority queue of pairs, path output |
| good_substrings | [CF 271D](https://codeforces.com/problemset/problem/271/D) | rolling hashes of 10⁶ substrings, sorting |
| snuke_festival | [ABC 077 C](https://atcoder.jp/contests/abc077/tasks/arc084_a) | sorting and binary search |
| same_differences | [CF 1520D](https://codeforces.com/problemset/problem/1520/D) | 10⁴ test cases, a hash map per test |

## Where the differences come from

CPL wins because of trade-offs that only short-lived programs can afford, plus a few compiler tricks:

- **No `free`, ever.** Allocating is a pointer bump, so vectors of vectors, priority queues and graphs build faster than with `malloc`. This is most of the SCC and Dijkstra wins.
- **The runtime is compiled into the program.** It's linked in as LLVM bitcode, so reading a number, printing one and indexing a string are inlined into the loops that use them.
- **Loop versioning.** In `for (i in rng(a, b))` loops, the compiler proves every `v[i + E]` is in bounds once, before the loop, and runs an unchecked copy. That takes the bounds checks out of DP loops.
- **Branch-free `if`.** `if c { x = A. } else { x = B. }` becomes a select when both sides are cheap and safe, which is why LCS on a two-letter alphabet doesn't pay for mispredicted branches.
- **Constants.** A global like `_ mod: ll = 998244353.` that's never assigned is a compile-time constant, so `% mod` becomes a multiplication.

Where CPL is slower or uses more memory, the reasons are just as plain:

- **Memory is never freed.** That shows up as higher memory in convolution (a temporary vector per NTT level) and same_differences (a new map for each of 10⁴ tests), and as time in same_differences' many tiny tests.
- **No references.** `seen[name]` followed by `seen[name] = ...` is two map lookups in CPL, while C++ binds `int &times = seen[name]` once. A one-entry cache in the map makes the second lookup cheap, but not free (registration, few names).
- **Vectorization.** In coins, LLVM vectorizes the DP loop once versioning has removed its bounds checks, and g++ -O2 doesn't vectorize it. clang++ -O2 would, so that 2x is LLVM versus GCC rather than CPL versus C++.

## Running it

```bash
python3 bench/run.py verify            # samples and random tests against a brute force
python3 bench/run.py bench             # max tests, prints the table above
python3 bench/run.py bench lcs scc     # only some problems
BENCH_RUNS=7 python3 bench/run.py bench
```

Each problem folder has `info.txt` (the link), `sol.cpl`, `sol.cpp`, `gen.py` (test generator) and `brute.py` (brute force or checker), plus the samples from the statement. Builds and generated tests go to `bench/.build/`.
