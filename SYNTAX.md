# CPL language reference

CPL code looks like a competitive programmer wrote it at 3 a.m.: one or two letter keywords, `in @` and `ou @@` instead of `cin >>` and `cout <<`, statements that end in a full stop, and decimal commas. Underneath, it's a complete statically typed language that compiles to native code through LLVM.

```go
f gcd(a: ll, b: ll) -> ll {
    if b == 0 { r a. }
    r gcd(b, a % b).
}

f mn() -> it {
    _ n: it.
    in @ n.
    _ g: ll.
    for (_ i: it = 0. i < n. ++i) {
        _ x: ll.
        in @ x.
        g = gcd(g, x).
    }
    ou @@ g @@ el.
    r 0.
}
```

## Contents

1. [Program structure](#program-structure)
2. [Keywords](#keywords)
3. [Types](#types)
4. [Literals](#literals)
5. [Variables](#variables)
6. [Operators](#operators)
7. [Conversions](#conversions)
8. [Control flow](#control-flow)
9. [Functions](#functions)
10. [Input and output](#input-and-output)
11. [Strings](#strings)
12. [Vectors and arrays](#vectors-and-arrays)
13. [Pairs](#pairs)
14. [Maps](#maps)
15. [Priority queues](#priority-queues)
16. [Structs](#structs)
17. [Built-in functions](#built-in-functions)
18. [Memory and the stack](#memory-and-the-stack)
19. [Runtime errors](#runtime-errors)
20. [Gotchas](#gotchas)

## Program structure

A program is a list of functions, structs and global variables, in any order. Execution starts at `mn`, which must take no parameters. Its return value becomes the exit code. If `mn` reaches its end without returning, the exit code is 0, as with `main` in C++.

Every simple statement ends with a `.`. Blocks use `{ }`, and the braces are always required, even around a single statement.

```go
// a line comment
/* a block
   comment */
f mn() {
    ou @@ "Hello, World!" @@ el.
}
```

## Keywords

Every keyword has a long form and a short form. Use whichever you like.

| Long form   | Short form | Meaning |
|-------------|------------|---------|
| `shall`     | `_`        | declare a variable |
| `func`      | `f`        | define a function |
| `ret`       | `r`        | return |
| `if`, `else`| `if`, `els`| conditionals |
| `while`     | `wh`       | while loop |
| `for`       |            | for loop |
| `break`     | `brk`      | leave the innermost loop |
| `continue`  | `cont`     | skip to the next iteration |
| `struct`    | `stc`      | define a struct |
| `in`        |            | read input: `in @ x.` |
| `ou`        |            | write output: `ou @@ x.` |
| `true`, `false` |        | booleans |
| `nil`       |            | the empty struct reference |
| `el`        |            | a newline character, like `endl` |
| `eq`        |            | another way to write `=` |

`f` and `r` are special: they're also the most common names in competitive programming (`l` and `r`!), so they only act as keywords at the start of a statement. `r` returns unless it's clearly a variable (`r = 1.`, `r += x.`, `r[i] = 0.`, `r.x = 5.`, `r++.`), and `f` defines a function only when a name follows. Everywhere else they're ordinary names, so `query(l, r)` and `_ f: vec<ll>.` work. The other short forms, like `_`, `in` and `wh`, are real keywords, and so are type names like `it` and `ch`.

## Types

| Type | Long name | What it is |
|------|-----------|------------|
| `it`  | `int`    | 32-bit signed integer |
| `ll`  | `long`   | 64-bit signed integer |
| `ui`  | `uint`   | 32-bit unsigned integer |
| `ull` | `ulong`  | 64-bit unsigned integer |
| `ch`  | `char`   | a single byte character |
| `du`  | `double` | 64-bit floating point number |
| `bo`  | `bool`   | `true` or `false` |
| `st`  | `string` | an immutable string |
| `vo`  | `void`   | "nothing", only used as a return type |
| `vec<T>`    | | a growable vector of `T` |
| `arr<T, N>` | | a `vec<T>` that starts with `N` elements |
| `map<K, V>` | | a hash map from `K` to `V` |
| `pr<A, B>`  | | a pair of an `A` and a `B` |
| `pq<T>`     | | a priority queue, largest first |
| `minpq<T>`  | | a priority queue, smallest first |
| any struct name | | an instance of that struct |

Numbers, characters, booleans, strings and pairs are **values**: assigning or passing them makes a copy, and strings can't be changed in place. Vectors, maps, priority queues and structs are **references**, as in Java or Python: assigning one or passing it to a function shares the same object.

## Literals

```go
42            // it; bigger numbers become ll, then ull
1'000'000     // digit separators, like C++14
2,5           // du: decimals use a comma
1e9  2,5e-3   // du in scientific notation
'a'  '\n'     // ch
"text\t\"quoted\"\n"   // st; escapes: \n \t \r \0 \\ \' \"
true  false   // bo
nil           // an empty struct reference
el            // the newline character '\n'
```

The decimal comma only counts **directly between digits**. `f(1, 2)` passes two arguments, but `f(1,2)` passes the single double `1.2`.

## Variables

```go
_ n: it.                  // starts at its default value
_ total: ll = 0.
_ a, b, c: it.            // several at once
_ x, y: du = 1,5.         // all of them start at 1.5
shall name: st = "cpl".   // the long form
```

Default values: 0 for numbers and characters, `false` for booleans, `""` for strings, an empty vector or map, a new struct with default fields, and `nil` for struct fields.

Variables declared outside functions are globals. They're initialized in order before `mn` runs, and their initializers can call functions. Blocks, `if` branches, loops and functions each have their own scope, and an inner variable can shadow an outer one. A variable declared inside a loop starts fresh on every iteration.

## Operators

From the tightest binding to the loosest:

| Operators | Meaning |
|-----------|---------|
| `f(x)` `v[i]` `p.x` | call, index, member |
| `^` | power, right-associative: `2 ^ 3 ^ 2` is `2 ^ 9` |
| `-x` `!x` `~x` | negation, logical not, bitwise not |
| `*` `/` `%` | multiply, divide, remainder |
| `+` `-` | add, subtract (`+` also joins strings) |
| `<<` `>>` | shifts |
| `<` `>` `<=` `>=` | comparisons |
| `==` `!=` | equality |
| `&` | bitwise and |
| `^^` | bitwise xor (`^` is already taken by power) |
| `\|` | bitwise or |
| `&&` | logical and, short-circuit |
| `\|\|` | logical or, short-circuit |
| `c ? a : b` | choose a value |

Because `^` binds tighter than unary minus, `-2 ^ 2` is `-4`.

`c ? a : b` picks `a` when `c` holds and `b` otherwise, and only evaluates the side it picks. It binds looser than `||` and chains to the right like in C: `x < 0 ? "minus" : x == 0 ? "zero" : "plus"`. The two sides need the same type, or two number types, which meet in their common type.

Assignment is a statement, not an expression: `=`, `+=`, `-=`, `*=`, `/=`, `%=`, `^=`, `&=`, `|=`, `^^=`, `<<=`, `>>=`, and `++x`, `x++`, `--x`, `x--`.

Integer arithmetic works like C++ on a 64-bit machine:
- Overflow wraps around.
- `/` rounds toward zero, and `%` takes the sign of the left side: `-7 / 2` is `-3` and `-7 % 3` is `-1`.
- Dividing by zero is a runtime error instead of undefined behaviour.
- The shift amount wraps at the type's width, as on x86. `1 << 40` on an `it` is `1 << 8`, so write `ll(1) << 40`.
- Integer `^` is exact (it doesn't go through doubles) and wraps on overflow.

When an operator mixes types, the result has the wider type:
- `ch` counts as `it`.
- Mixing an integer with a `du` gives a `du`.
- Integers of equal width give an unsigned result if either side is unsigned.

`&`, `|` and `^^` also work on two `bo` values, without short-circuiting.

## Conversions

These conversions happen automatically:
- between any two integer types, including `ch`, which can truncate
- from integers to `du`
- from `nil` to any struct
- from a whole-number `du` literal to an integer type, if it fits. This makes `_ inf: ll = 1e18.` and `_ mod: it = 1e9 + 7.` work, because arithmetic on literals is worked out at compile time.

Everything else needs an explicit conversion, which is written like a function call on the type:

```go
it(3,99)      // 3: cuts off the decimals
du(7) / 2     // 3.5
ch('a' + 1)   // 'b'
it(true)      // 1
bo(5)         // true
st(42)        // "42"; works on every number, ch and bo
it("123")     // 123; a runtime error if the string isn't a number
du("2.5")     // 2.5; parsing uses a decimal point, like the input does
```

## Control flow

```go
if x < 0 {
    ou @@ "negative".
} else if x == 0 {
    ou @@ "zero".
} els {
    ou @@ "positive".
}

wh i < n { i++. }

for (_ i: it = 0. i < n. ++i) { ... }
for (. i < n. ) { ... }       // every part is optional
for (. . ) { brk. }           // loops forever until brk

for (x in v) { ... }          // every element of a vector
for (i, x in v) { ... }       // with its index (ll)
for (c in s) { ... }          // every character of a string
for (k in m) { ... }          // every key of a map, in sorted order
for (k, val in m) { ... }     // with its value
for (i in rng(n)) { ... }     // 0, 1, ..., n - 1
for (i in rng(a, b)) { ... }  // a, a + 1, ..., b - 1
for (i in rng(b, a, -1)) { ... }   // b, b - 1, ..., a + 1
```

Conditions can be `bo` values or numbers, where 0 is false. Parentheses around conditions are optional. `brk` and `cont` work on the innermost loop, and in a `for` loop `cont` still runs the step.

In a for-each loop, the variables are copies: assigning to `x` doesn't change `v`, but changing a struct through `x` does, since structs are references. The length is checked again on every iteration, so pushing to `v` inside the loop is safe, and a loop over a map goes through the keys it had when the loop started. `rng()` counts like Python's `range` without building a vector.

The compiler reports code after a `r`, `brk` or `cont` as unreachable. It also reports functions that can reach their end without returning a value.

## Functions

```go
f add(a: ll, b: ll) -> ll {
    r a + b.
}

f greet(name: st) {        // no arrow: returns nothing
    ou @@ "hi " @@ name @@ el.
    r.                     // optional early return
}
```

Functions can be defined in any order and can call each other recursively. Arguments are converted to the parameter types using the automatic conversions above. Numbers and strings are passed by value, and vectors, maps and structs by reference. Function names and variable names live in separate namespaces.

## Input and output

```go
in @ n @ m.                // like cin >> n >> m
in @ v[i] @ p.x.           // read straight into elements and fields
ou @@ a @@ ' ' @@ b @@ el. // like cout << a << ' ' << b << endl
```

`in @` skips whitespace, then reads a value of the target's type:

| Type | What `in @` reads |
|------|-------------------|
| integers | a whole number |
| `du` | a number written with a decimal **point**, as input files are |
| `ch` | the next character that isn't whitespace |
| `st` | the next word |
| `bo` | `true`, `false`, `1` or `0` |

At the end of the input, `in @` leaves 0 or an empty string. Input that isn't a valid number is a runtime error.

| Function | Result |
|----------|--------|
| `eof()` | `true` once only whitespace is left |
| `gl()` (or `getline()`) | the rest of the current line, without the line break |

`ou @@` writes values without separators. Numbers print as you'd expect, booleans print as `true` and `false`, and doubles print like `cout`'s default (`%g`, 6 significant digits). For a fixed number of decimals, use `prec(x, digits)`: `ou @@ prec(3,14159, 2).` prints `3.14`.

Output is buffered, which makes it fast. It's flushed when the program ends, before a runtime error message, and whenever the program waits for input, so interactive problems work.

## Strings

```go
_ s: st = "comp".
s = s + "etitive" + '!'.   // + joins strings and characters
s += "!".
s.sz()                     // length (ll)
s.emp()                    // is it empty?
s[0]                       // a ch; bounds-checked
s.sub(start, length)       // substring, without copying; length is cut off at the end
s == "x"   s < t           // comparisons look at the contents
```

Strings are immutable, so `s[0] = 'x'` isn't allowed: build a new string instead. Joining a string with a number needs `st(x)`.

Building a string piece by piece with `s += x` or `s = s + x` is linear, like `+=` on a C++ `std::string`. Appending to the newest version of a string writes in place, and every older version keeps its own length, so it never sees the new characters.

## Vectors and arrays

```go
_ v: vec<it>.                 // empty
_ w: vec<ll> = vec<ll>(n).    // n zeros
_ s: vec<it> = vec<it>(n, 7). // n sevens
_ a: arr<du, 100>.            // a vec<du> with 100 zeros
_ g: vec<vec<it>> = vec<vec<it>>(n).   // n separate empty vectors
```

| Method | Long alias | Does |
|--------|------------|------|
| `v.pb(x)` | `push_back` | add to the end |
| `v.pp()`  | `pop_back`  | remove the last element |
| `v.bk()`  | `back`      | the last element |
| `v.sz()`  | `size`      | number of elements (ll) |
| `v.emp()` | `empty`     | is it empty? |
| `v.clr()` | `clear`     | remove everything |
| `v.srt()` | `sort`      | sort ascending: numbers, characters, booleans, strings or pairs |
| `v.srt(before)` | `sort`  | sort by a function, see below |
| `v.rev()` | `reverse`   | reverse in place |
| `v.lb(x)` | `lower_bound` | in a sorted vector, the index of the first element `>= x` (ll) |
| `v.ub(x)` | `upper_bound` | in a sorted vector, the index of the first element `> x` (ll) |

To sort in another order, or to sort structs, write a function that says whether `a` goes before `b`, and pass its name:

```go
f byTime(a: Job, b: Job) -> bo { r a.time < b.time. }
f descending(a: it, b: it) -> bo { r a > b. }

jobs.srt(byTime).
v.srt(descending).
```

Sorting is stable: elements that are equal under the order keep their relative order.

`ou @@ v` prints the elements separated by spaces. Every `v[i]` is bounds-checked, and a bad index stops the program with a runtime error. `vec<T>(n, x)` isn't allowed when `T` is a vector, map or struct, because all elements would share one object. `vec<T>(n)` gives each element its own.

## Pairs

```go
_ p: pr<it, st> = pr(3, "abc").   // pr(a, b) takes its types from a and b
_ q: pr<ll, ll> = pr(1, 2).       // the halves convert like any other value
p.f += 10.                        // .f and .s, or .first and .second
ou @@ p.s @@ q @@ el.             // a pair prints as "1 2"
in @ q.                           // and reads two values
if pr(1, 2) < pr(1, 3) { ... }    // compared by the first half, then the second
```

Pairs can hold numbers, characters, booleans, strings, structs and other pairs. They're values, so `_ r: pr<it, it> = p.` copies `p`. They sort, can be binary searched, and work in priority queues, which covers most uses of `pair` in C++ solutions. A pair can also be a map key when both halves are integers of at most 32 bits, characters or booleans: `map<pr<it, it>, it>` is the usual grid of coordinates.

## Maps

```go
_ count: map<st, it>.
count["apple"]++.              // a missing key starts at its default
count.has("pear")              // does the key exist? (doesn't insert)
count.del("apple")             // remove a key
count.sz()   count.emp()   count.clr()
_ keys: vec<st> = count.keys().  // every key, sorted
```

Keys can be any number type, `ch`, `bo`, `st` or a pair of small integers (see [Pairs](#pairs)). Values can be anything, including vectors, maps and structs, which are created on first use: `groups['a'].pb("apple").` just works. As in C++, *reading* a missing key with `m[k]` inserts it, so use `has` to check without inserting. Aliases: `count` and `contains` for `has`, `erase` for `del`, plus `size`, `empty` and `clear`.

## Priority queues

```go
_ q: pq<it>.                  // largest first, like C++'s priority_queue
_ dist: minpq<pr<ll, it>>.    // smallest first: the Dijkstra queue
q.ps(5).                      // push
q.tp()                        // the first element, without removing it
q.pp().                       // remove the first element
q.sz()   q.emp()   q.clr()
```

Elements can be anything with an order: numbers, characters, booleans, strings and pairs. Long aliases: `push`, `top`, `pop`, `size`, `empty` and `clear`. `tp()` and `pp()` on an empty queue are runtime errors.

## Structs

```go
struct Point { x: it. y: it. }
stc Node { value: it. next: Node. }   // a struct can refer to itself

_ origin: Point.              // a new Point with x = 0, y = 0
_ p: Point = Point(3, 4).     // every field, in order
p.x += 1.
_ list: Node = nil.
if list == nil { ... }
```

Struct variables are references: `_ q: Point = p.` makes `q` and `p` the same point, and passing a struct to a function lets the function change it. `==` compares identity, not contents. Struct fields that are structs start as `nil`, and reading a field through `nil` is a runtime error. Fields that are vectors or maps start empty.

## Built-in functions

| Function | Result |
|----------|--------|
| `min(a, b)`, `max(a, b)` | the smaller or larger number, in their common type |
| `abs(x)` | absolute value |
| `sqrt(x)` `floor(x)` `ceil(x)` `log(x)` `exp(x)` | `du` math |
| `prec(x, digits)` | `x` formatted with a fixed number of decimals, as a `st` |
| `eof()` | `true` once the input has only whitespace left |
| `gl()`, `getline()` | the rest of the current input line |
| `swap(a, b)` | exchanges two variables, elements or fields of the same type |
| `gcd(a, b)`, `lcm(a, b)` | greatest common divisor and least common multiple of two integers; `gcd(0, 0)` is 0 |
| `pc(x)`, `ctz(x)`, `clz(x)` | set bits, trailing zero bits and leading zero bits of an integer, like `__builtin_popcount` |

## Memory and the stack

CPL makes the trade-offs a short-lived program can afford and long-running software can't:

- **Memory is never freed.** Everything comes from one bump allocator carved out of a huge address space reservation. Allocating is a pointer bump, new memory is already zeroed by the OS, and there's no `malloc` bookkeeping per object. This is why vectors of vectors and structs are several times faster than in C++. When the newest allocation is a vector or string that needs to grow, it grows in place without copying.
- **The stack is huge.** `mn` runs on a stack of a quarter of the machine's memory (up to 16 GB), so a recursive DFS ten million levels deep just works. Only the part that's used costs memory. A recursion that never stops ends with a stack overflow error instead of a crash.
- **Big allocations use 2 MB pages** where the OS allows it, which makes random access into big arrays cheaper.

Under an address space limit (`ulimit -v`, which some judges use as the memory limit), the runtime reserves less up front and grows in steps instead, and the stack gets at most a quarter of the limit.

The compiler also works hard on the loops competitive programs live in:

- **Loop versioning.** In a `for (i in rng(a, b))` loop, every `v[i + E]` (where `E` doesn't change in the loop, like `dp[(i - 1) * w + j]` or `best[c - w]`) is checked against the vector's length once, before the loop. If they all fit, a copy of the loop without per-element bounds checks runs; otherwise the normal checked loop runs and reports the bad index. This needs the vector's length to stay fixed during the loop: no `pb`, `pp`, `clr` or `swap`, and no calls to your own functions inside it.
- **Branch-free `if`.** `if c { x = A. } else { x = B. }` (or without the `else`) compiles to a select instead of a jump when `A` and `B` have no side effects, no division and only indexes proven in bounds.
- **Constants.** A global number that starts as a literal and is never assigned is a compile-time constant, like `const` in C++, so `% mod` with `_ mod: ll = 998244353.` compiles to a multiplication.
- **The runtime is part of the program.** When clang is installed, the runtime is linked in as LLVM bitcode, so reading and printing numbers and indexing strings are inlined into the loops that use them.

[bench/README.md](bench/README.md) measures all of this against C++ on real problems.

## Runtime errors

These stop the program with exit code 1 and a message on stderr. Output printed before the error still appears.

```
~~~ RUNTIME ERROR: index 5 is out of bounds for length 3
~~~ RUNTIME ERROR: division by zero
~~~ RUNTIME ERROR: accessed a field of nil
~~~ RUNTIME ERROR: vector is empty
~~~ RUNTIME ERROR: expected an integer in the input
~~~ RUNTIME ERROR: stack overflow (the recursion is too deep, or never stops)
```

## Gotchas

- `f(1,2)` is `f(1.2)`. Put a space after commas.
- `r` at the start of a statement returns: `r (x + 1).` returns `x + 1`, while `r[0] = 1.` and `r = 1.` use a variable called `r`.
- Hot loops are fastest as `for (i in rng(a, b))`: those are the loops the compiler can take bounds checks out of (see below).
- A `.` directly followed by a name, with no space in between, is member access (`v.pb(x)`). Any other `.` ends the statement.
- `1 << 40` is computed in 32 bits. Use `ll(1) << 40`.
- Memory is never freed, which is great for a program that runs for a second and terrible for a server. See [Memory and the stack](#memory-and-the-stack).
