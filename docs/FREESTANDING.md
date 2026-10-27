# From scratch: making Jal Pari capable of its own OS

Goal (set 27 Oct 2026): an operating system **bigger than TempleOS,
written completely in Jal Pari, with no Linux anywhere in it**.
Not a Linux distro with a theme (that is what Black Moon OS is today),
and not a simulation (that is what JalOS is today): a real kernel
that boots on real hardware — starting with our own CPU, big32 —
plus the userspace on top of it, all in our own language.

This document is the capability roadmap. The order matters: the
language must be able to touch hardware **before** kernel code is
written in it. Each phase ends at a verified checkpoint; kernel
building starts after Phase E.

## Why TempleOS is the right yardstick — and what "bigger" means

TempleOS (Terry Davis, ~2005–2013, one person) was: its own
language (HolyC), its own kernel, its own window manager and
filesystem, ring-0-only, no networking, no multi-user, x86-64 only,
roughly 100,000 lines. "Bigger" here means beating it where it was
weak while matching where it was strong:

- Own language AND own CPU (TempleOS had only the language; big32
  is already ours) — the stack is more self-owned from the start.
- Networking (TempleOS had none) and real user programs written in
  the same language as the kernel.
- A windowed desktop, not just a terminal.
- Honest limits, stated up front: big32 is single-core and
  simulated, so "bigger" is measured in capability and completeness,
  not in raw performance or hardware range. A PC (x86-64) port is a
  later phase, not phase one: PC hardware needs ACPI, PCI, USB, GPU
  and NVMe drivers, each a project of its own.

## What the language cannot do today (the blockers)

- ~~No bitwise operators~~ — FIXED in Phase A. Device registers are
  all bitfields; without `& | ^ << >> ~` no driver code is possible.
- No raw memory access: no pointers, no volatile loads/stores, so
  no MMIO (UART, framebuffer, CLINT) can be touched.
- No freestanding mode: generated C links libc (stdio, pthread,
  sockets, files) and expects a hosted `main`. A kernel has no OS
  underneath to provide those.
- No trap/interrupt primitives: no CSR access, no way to install a
  trap handler, no timer interrupt path.
- No inline assembly: some things (trap entry, `mret`, `fence`)
  cannot be expressed without it, or need dedicated builtins.
- Heap depends on libc `malloc`: strings and arrays allocate
  through it. A kernel needs an allocator it owns.
- Int width differs by backend: 64-bit native/WASM, 32-bit big32.
  Kernel code must be written width-aware (see the shift-count
  note in Phase A).

## Phases

### Phase A — Bitwise operators (DONE 27 Oct 2026)

`& | ^ << >> ~` on ints, C-like precedence (`|` loosest, then `^`,
then `&`, then `==`/`!=`, then comparisons, then `<<` `>>`, then
`+` `-`, then `*` `/` `%`). Semantics, pinned by
`tests/test_bitwise.py` (18 checks: native, WASM, big32 model UART
transcript, checker rejections, formatter stability):

- `& | ^`: two's-complement, all backends.
- `<<`: wraps through the unsigned width, so a negative left
  operand is defined (plain C leaves it undefined).
- `>>`: arithmetic (sign-extending) on all backends.
- Shift counts are masked: 0..63 on native/WASM (i64), 0..31 on
  big32 (32-bit words). Counts at or above the word width therefore
  differ across backends **by design**; kernel code must keep
  counts below 32 to be portable, or accept the divergence.
- big32 already emitted `and`/`or`/`xor`/`sll`/`sra` for these
  operators before the parser produced them; the work was lexer,
  parser, checker, formatter, native shifts, WASM opcodes, and the
  big32 `~` (`xori` with -1). One real bug caught by the tests:
  WASM `>>` was first emitted as `shr_u` (0x88) instead of `shr_s`
  (0x87); fixed and re-verified.

### Phase B — Raw memory access (next)

Volatile `peek32`/`poke32` builtins (32-bit load/store through a
raw address): native emits a volatile pointer dereference, big32
emits `lw`/`sw`, WASM rejects loudly (no raw memory there).
This is what lets kernel code talk to UART MMIO, the CLINT timer,
and a framebuffer. Checkpoint: a native test program that pokes a
known buffer address and reads it back, plus a big32 model run
writing a byte to the UART address.

### Phase C — Freestanding codegen

A `--freestanding` build mode: no libc prelude (no stdio, pthread,
socket, or file helpers in the generated code), no hosted `main`
(a custom `_start` entry instead), `fail()` halts instead of
exiting, and strings/arrays allocate from a small bump allocator
emitted with the program — one the kernel can later replace with
its own allocator. Anything that needs the OS (files, sockets,
threads, `read_line`, clock) is a clean compile-time error in this
mode, not a link error. Checkpoint: a freestanding program that
builds with no libc symbols and runs on the big32 model.

### Phase D — Traps, interrupts, and firmware calls

- CSR builtins (`csr_read`/`csr_write`/`csr_set`/`csr_clear`) for
  `mstatus`, `mtvec`, `mie`, `mtimecmp` and friends.
- A trap-handler hook: the runtime's assembly entry saves
  registers and calls a Jal Pari function with a reserved name,
  so interrupt and exception handling is written in Jal Pari.
- An `ecall` builtin for SBI calls during bring-up. Using the
  existing big32 SBI firmware as a bootloader/firmware layer is
  honest, not cheating: TempleOS also ran on BIOS/UEFI firmware.
  The kernel itself is still ours; SBI is the floor it stands on,
  and later phases can replace SBI console/timer use with direct
  drivers.
- Checkpoint: a timer tick reaching Jal Pari code, counted and
  printed to UART.

### Phase E — Boot story and the first kernel

Linker script, `_start`, trap vector, and the first kernel:
UART hello, timer tick, and a round-robin scheduler — the JalOS
concepts (scheduler, allocator, VFS ideas) rewritten as real
bare-metal code. **Kernel building starts here, not before.**
Checkpoint: the kernel boots on the big32 model and prints its
own banner, tick count, and task switches to UART.

### Phase F and beyond — the OS itself

In order, each its own checkpoint: physical memory management and
paging; a real filesystem (start with a tiny read-only one, then
writable); processes and syscalls; a shell; a window manager and
GUI toolkit in Jal Pari; keyboard, disk, and display drivers;
networking (the capability TempleOS never had); user programs —
the Moon apps, rewritten as native OS programs. A PC port comes
only after the big32 OS is real.

## What does not change

- Black Moon OS (the Linux distro) continues as the system people
  can actually use today. The from-scratch OS is a second track,
  not a replacement, until it can stand on its own.
- JalOS (the simulation) stays as the concepts prototype; its
  code does not become kernel code, its ideas do.
- Numbers in this document come from verified runs only; anything
  unbuilt is labelled as a plan, not a result.
