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
13. [Maps](#maps)
14. [Structs](#structs)
15. [Built-in functions](#built-in-functions)
16. [Runtime errors](#runtime-errors)
17. [Gotchas](#gotchas)

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

The short forms are real keywords, so `f`, `r` and `_` can't be used as variable names. Type names like `it` and `ch` can't be used as names either.

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
| any struct name | | an instance of that struct |

Numbers, characters, booleans and strings are **values**: assigning or passing them makes a copy, and strings can't be changed in place. Vectors, maps and structs are **references**, as in Java or Python: assigning one or passing it to a function shares the same object.

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

Because `^` binds tighter than unary minus, `-2 ^ 2` is `-4`.

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
```

Conditions can be `bo` values or numbers, where 0 is false. Parentheses around conditions are optional. `brk` and `cont` work on the innermost loop, and in a `for` loop `cont` still runs the step.

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
s.sub(start, length)       // substring; length is cut off at the end
s == "x"   s < t           // comparisons look at the contents
```

Strings are immutable, so `s[0] = 'x'` isn't allowed: build a new string instead. Joining a string with a number needs `st(x)`.

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
| `v.srt()` | `sort`      | sort ascending: numbers, characters, booleans or strings |
| `v.rev()` | `reverse`   | reverse in place |

Every `v[i]` is bounds-checked, and a bad index stops the program with a runtime error. `vec<T>(n, x)` isn't allowed when `T` is a vector, map or struct, because all elements would share one object. `vec<T>(n)` gives each element its own.

## Maps

```go
_ count: map<st, it>.
count["apple"]++.              // a missing key starts at its default
count.has("pear")              // does the key exist? (doesn't insert)
count.del("apple")             // remove a key
count.sz()   count.emp()   count.clr()
_ keys: vec<st> = count.keys().  // every key, sorted
```

Keys can be any number type, `ch`, `bo` or `st`. Values can be anything, including vectors, maps and structs, which are created on first use: `groups['a'].pb("apple").` just works. As in C++, *reading* a missing key with `m[k]` inserts it, so use `has` to check without inserting. Aliases: `count` and `contains` for `has`, `erase` for `del`, plus `size`, `empty` and `clear`.

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

## Runtime errors

These stop the program with exit code 1 and a message on stderr. Output printed before the error still appears.

```
~~~ RUNTIME ERROR: index 5 is out of bounds for length 3
~~~ RUNTIME ERROR: division by zero
~~~ RUNTIME ERROR: accessed a field of nil
~~~ RUNTIME ERROR: vector is empty
~~~ RUNTIME ERROR: expected an integer in the input
```

## Gotchas

- `f(1,2)` is `f(1.2)`. Put a space after commas.
- `f`, `r` and `_` are keywords, so `_ r: it.` is a syntax error. The error message says so.
- A `.` directly followed by a name, with no space in between, is member access (`v.pb(x)`). Any other `.` ends the statement.
- `1 << 40` is computed in 32 bits. Use `ll(1) << 40`.
- Memory is never freed. That's fine for competitive programming, and part of the parody.
