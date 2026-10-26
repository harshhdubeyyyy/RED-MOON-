# Forge v2 Specification

## 1. Types

`int` (signed 64-bit), `float` (64-bit double), `bool`, `str`,
`void` (function return only), and `[T]` dynamic arrays where `T`
is `int`, `float`, `bool`, or `str`. Nested arrays are not yet
supported. There is no null.

## 2. Functions, variables, control flow

```
fn name(a: int, b: [float]) -> float { ... }
let x: int = 5;          // immutable
let mut y = 10;          // mutable, type inferred
let xs: [float] = [];    // empty array needs an annotation
```

Statements: `let`, assignment (`x = ...`, `a[i] = ...`), `if` /
`else if` / `else`, `while`, `for v in array { ... }`, `return`,
bare blocks. Conditions must be `bool`. A non-void function must
end its body with a `return`. `fn main()` takes no arguments and
returns `int` or nothing.

## 3. Expressions

Precedence: `||` -> `&&` -> `== !=` -> `< <= > >=` -> `+ -` ->
`* / %` -> unary -> postfix (`a[i]`, `x as float`) -> primary.

* Arithmetic: matching `int` or `float` operands, except `str + str`
  (concatenation) and `int % int`. Integer arithmetic is checked
  in safe mode (overflow, division/modulo by zero abort cleanly);
  in fast mode it is unchecked, like C.
* Comparison and equality: matching numeric operands, plus `str`
  equality by contents.
* Logic: `&&`, `||` on `bool`; unary `-` on numeric, `!` on `bool`.
* Casts: `int as float` and `float as int` (truncation) only.
* Array literals: `[1, 2, 3]`, `[1.0, 2.5]`; all elements must
  have the same type. Arrays are shared by reference on assignment,
  like Python lists: assigning an array does not copy its elements.

## 4. Builtins

Statement-only: `print(...)`, `println(...)`, `push(array, value)`,
`fail("message")` (prints to stderr and exits 1).

Expression: `len(str or array) -> int`, `range(n: int) -> [int]`
(0..n-1), `clock_micros() -> int` (monotonic microseconds),
`sqrt/exp/log(float) -> float`, `pow(float, float) -> float`,
`abs(int) -> int`, `read_file(path: str) -> str` (fails if the file
cannot be read), `write_file(path: str, content: str) -> bool`
(true on success), `args() -> [str]` (command-line arguments after
the program name; pass them with `forge.py run file.fg -- a b`),
`parse_int(str) -> int` (fails on non-integer input).

## 4b. Structs (added in Phase C, 26 Oct 2026)

```
struct Point {
    x: float;
    y: float;
}
let p: Point = Point { x: 0.0, y: 0.0 };
let mut q: Point = Point { x: 3.0, y: 4.0 };
q.x = 6.0;
println("distance =", distance(p, q));
```

Rules: every field must be supplied exactly once in a literal,
field types must match, field access requires a struct value,
and field assignment requires the outermost variable to be
`let mut`. Structs can be function parameters and return values
(by value). Recursive structs and arrays of structs are rejected
for now. Parser note: `Name { field: value }` is only treated as
a struct literal when the brace is followed by `field:` or `}` —
so `for v in xs {` and `if x {` still parse as blocks.

## 5. Imports and the standard library

```
import "ml.fg";
```

Imports are resolved relative to the importing file, then the
current directory, then `stdlib/`. `stdlib/ml.fg` provides `dot`,
`mean`, `relu`, `sigmoid`, and `matmul` (flat row-major matrices).

## 6. Modes and compilation

Forge -> C -> `cc` -> native binary, with `-lm` linked.

* Safe mode (default): `-O2`, checked int arithmetic, bounds-checked
  indexing, readable runtime errors.
* Fast mode (`--mode fast`): `-O3 -march=native`, unchecked
  arithmetic and indexing. The binary is less portable and can
  wrap, crash, or read out of bounds on bad input. Use it only for
  hot code you have already validated in safe mode.

## 7. What v2 deliberately lacks (next phases)

Generics (which `Option`/`Result` depend on), concurrency
(channels/actors), GPU kernels, Python interop, a package manager,
a formatter, and an LSP. Array and string values are not yet freed
(GC is the Phase B memory-manager item). Structs, file I/O, CLI
args, and `forge test` are DONE (Phase C, 26 Oct 2026). Claiming
v2 "combines C++, Mojo, and Python" means it combines their
*approach* — native speed, Python-like ML syntax, Mojo-like
compiled kernels for small models — not their full ecosystems,
libraries, or GPU stacks.
