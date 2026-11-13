# cpl
CPL is an LLVM-based programming language designed specifically for competitive programming. Okay, actually it is a parody of the way competitive programmers write code.

It's also a complete language. It has 64-bit and unsigned integers, doubles, strings, vectors, hash maps, structs, recursion, loops and fast input/output. Programs compile to native code through LLVM. They often run faster than the C++ they're making fun of, because CPL makes trade-offs that only short-lived programs can afford: memory is never freed, and the stack is gigabytes deep.

```go
// read n numbers and print how often each one appears, in order
f mn() {
    _ n: it.
    in @ n.
    _ count: map<ll, it>.
    for (i in rng(n)) {
        _ x: ll.
        in @ x.
        count[x]++.
    }
    for (x, times in count) {
        ou @@ x @@ ": " @@ times @@ el.
    }
}
```

See [SYNTAX.md](SYNTAX.md) for the whole language and [examples/](examples) for some classic problems: BFS, Dijkstra, knapsack, a prime sieve, binary search and a solution to [Codeforces 2272F](https://codeforces.com/contest/2272/problem/F).

## Speed

[bench/](bench) has 17 real AtCoder and Codeforces problems, each solved with the same algorithm in CPL and in C++ (g++ -O2, with the same fast I/O). All three builds are verified against brute force solutions before anything is timed. CPL is faster than or level with C++ on 27 of the 31 max-size tests:

| Problem | C++ | CPL |
|---|---|---|
| SCC, 5·10⁵ vertices, recursion 5·10⁵ deep | 83 ms | 41 ms |
| Dijkstra with path, 10⁵ edges (long path) | 33 ms | 19 ms |
| lazy segment tree, 5·10⁵ queries mod 998244353 | 832 ms | 717 ms |
| suffix array + LCP, 5·10⁵ characters | 64 ms | 57 ms |
| LCS DP, 3000 × 3000 | 21 ms | 18 ms |
| NTT convolution, 2²⁰ | 214 ms | 218 ms |
| 10⁴ test cases with a hash map each | 14 ms | 17 ms |

The full table, the rules and the reasons behind each difference are in [bench/README.md](bench/README.md). In short, CPL wins by never freeing memory, compiling its runtime into the program, and proving bounds checks away in loops. It loses where C++'s references save a lookup or where freeing memory matters.

## Setup

You need Python 3.10 or newer, [llvmlite](https://pypi.org/project/llvmlite/) and a C compiler (`cc`, `gcc` or `clang`) for the runtime library.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The `cpl` script uses `.venv` automatically when it exists. Set `CPL_PYTHON` to use a different interpreter.

## Usage

```bash
./cpl examples/gcd.cpl < examples/gcd.in
```

| Command | What it does |
|---------|--------------|
| `./cpl run file.cpl` (or just `./cpl file.cpl`) | compile and run straight away |
| `./cpl build file.cpl -o program` | build a native executable |
| `./cpl check file.cpl` | only report errors |
| `./cpl ir file.cpl` | print the LLVM IR (`-O0` for the unoptimized version) |
| `./cpl ast file.cpl` | print the syntax tree as JSON |
| `./cpl tokens file.cpl` | print the tokens |

Add `-O0` to `-O3` to pick the optimization level (the default is `-O2`), and `--time` to print the run time. Programs read stdin and write stdout, and the value returned from `mn` is the exit code.

## Tests

```bash
.venv/bin/python tests/run_tests.py            # everything, using the JIT
.venv/bin/python tests/run_tests.py --native   # also as native executables
.venv/bin/python tests/run_tests.py maps       # only tests with "maps" in the name
```

The tests are split by what they check:
- `tests/programs/` holds programs with expected output.
- `tests/errors/` checks the compile error messages.
- `tests/runtime_errors/` checks the runtime errors.

The examples run as tests too.

## How it works

| File | Role |
|------|------|
| `python/Lexer.py`, `python/Token.py` | turn source text into tokens |
| `python/Parser.py`, `python/AST.py` | a Pratt parser that builds the syntax tree |
| `python/Compiler.py`, `python/Types.py` | type checking and LLVM IR generation with llvmlite |
| `python/Driver.py`, `python/main.py` | optimization, JIT, linking, and the command line |
| `runtime/cpl_runtime.c` | strings, vectors, hash maps, buffered I/O and runtime errors |
