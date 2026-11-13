# cpl
CPL is an LLVM-based programming language designed specifically for competitive programming. Okay, actually it is a parody of the way competitive programmers write code.

It's also a complete language. It has 64-bit and unsigned integers, doubles, strings, vectors, hash maps, structs, recursion, loops and fast input/output. Programs compile to native code through LLVM, and they run about as fast as the C++ they're making fun of.

```go
// read n numbers and print how often each one appears, in order
f mn() -> it {
    _ n: it.
    in @ n.
    _ count: map<ll, it>.
    for (_ i: it = 0. i < n. ++i) {
        _ x: ll.
        in @ x.
        count[x]++.
    }
    _ keys: vec<ll> = count.keys().
    for (_ i: it = 0. i < keys.sz(). ++i) {
        ou @@ keys[i] @@ ": " @@ count[keys[i]] @@ el.
    }
    r 0.
}
```

See [SYNTAX.md](SYNTAX.md) for the whole language and [examples/](examples) for some classic problems: BFS, Dijkstra, knapsack, a prime sieve, binary search and a solution to [Codeforces 2272F](https://codeforces.com/contest/2272/problem/F). On that problem, CPL runs at the same speed as the equivalent C++.

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
