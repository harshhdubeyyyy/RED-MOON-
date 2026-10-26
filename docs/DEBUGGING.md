# Debugging Jal Pari programs (0.5.0)

There is no source-level debugger yet — this page documents
what exists today, honestly, and what is missing.

## What works today

### 1. Print tracing
`println` is the everyday tool. For training loops, print
loss every N steps; stdout is fully buffered when piped,
so for a crashing binary use
`forge.py build -o bin` + `script -qec "stdbuf -o0 -e0 bin"`.

### 2. Emit C and use gdb
```sh
python3 forge.py emit program.fg -o program.c
cc -g program.c -o program -lm
gdb ./program
```
Generated C locals keep the `.fg` variable names, so
`print myvar` in gdb works. Breakpoints land on C lines,
not `.fg` lines (see the gap below).

### 3. Leak hunting with allocation counters
```fg
println("allocs", arr_alloc_count(), "frees", arr_free_count());
```
If allocs climb across loop iterations while frees stay
flat, something created inside the loop is never freed.
This is exactly how the 0.5.0 tape leak was found: loop
bodies never freed their locals, so each training step's
tape leaked. That specific leak is fixed (block-end
freeing in codegen.py); the counters remain the tool for
the next one.

### 4. Safe-mode checks
Safe mode (the default) aborts on out-of-bounds access,
integer overflow, and division by zero with a message
naming the failure kind. It does not yet name the `.fg`
source line — see below.

## What is missing (not claimed)

A source-level debugger (breakpoints and stepping on
`.fg` lines) needs `#line` directives in the emitted C,
and those need correct file attribution: AST nodes carry
a line number but not a filename, and imports are merged
into one program, so a naive `#line` would misattribute
stdlib code to the main file. The fix is file tracking
through the parser — real work, not a flag flip. Until
then, gdb on the emitted C (above) is the debugger.
