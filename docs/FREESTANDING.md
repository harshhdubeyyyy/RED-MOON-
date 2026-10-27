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

### Phase B — Raw memory access (DONE 27 Oct 2026)

Volatile `peek32`/`poke32` builtins (32-bit load/store through a
raw address): native emits a volatile pointer dereference
(`forge_peek32`/`forge_poke32` helpers, so the compiler can never
optimise an MMIO access away), big32 emits `lw`/`sw`, WASM
rejects loudly (no raw addresses there). `peek32(addr) -> int`
is an expression; `poke32(addr, val)` is statement-only, like
`push` — a write has no value, and the checker rejects using it
as one (this rule was found by the tests, not planned: the first
version made poke32 an expression and the checker refused bare
`poke32(...);` statements). Both are UNCHECKED in every mode, by
design: a raw address is unsafe by definition. Pinned by
`tests/test_peek_poke.py` (13 checks): big32 model run writes
byte `A` to the UART address and reads back status 0, RX -1,
and a RAM round-trip (`A0\n-1\n123456` transcript); native
generated C contains the volatile helpers; checker rejections;
WASM rejections. Note for kernel code: the language has no
address-of operator, so native round-trips cannot be addressed
from Jal Pari itself — big32 is where these builtins are truly
proven.

### Phase C — Freestanding codegen (DONE 27 Oct 2026)

`forge.py build --freestanding` (also `check`/`emit`): the
program stands without libc or Linux. Native builds with
`-nostdlib`; the program's own `_start` entry calls
`jalpari_main` and exits via the raw Linux `exit_group` syscall
with main's return value (int main -> exit code, void main ->
exit 0), so a freestanding program's only observable output is
its exit code. The prelude is a minimal header (only the
freestanding-compatible `<stdint.h>`/`<stdbool.h>` types, checked
arithmetic via gcc builtins, volatile peek/poke helpers);
`fail()` halts in an infinite loop, since there is no OS to
exit to. Anything needing the OS is a clean error, not a link
error: the checker rejects files, sockets, threads (spawn and
scope), clock, args, print/println, libm builtins (sqrt/exp/log/
pow/abs), and extern C functions; the codegen rejects any
string/array value (including structs carrying str/array fields)
and `emit_free_owned` is a no-op, since no owned values can
exist. big32 runs under the same flag (its output is already
bare metal); WASM refuses the flag outright. Pinned by
`tests/test_freestanding.py` (24 checks): native exit codes
(27 computed, 0 void, 42 fast), ldd statically linked, nm zero
undefined symbols, `_start` + `jalpari_main` present, checked
overflow halts (proven by timeout, not exit), big32 model
"OK" via poke32 + RAM round-trip, all rejections, and the
hosted control (the same print program builds fine without the
flag). Two real bugs found by testing, both fixed: the Return
path in main also emitted `forge_join_threads`, and unused
str/array parameters could emit frees for helpers that don't
exist. Limits: x86_64 Linux only for native (the `_start` asm);
freestanding v1 has no allocator, so no strings/arrays and no
I/O library — output is via poke32 (MMIO) and exit codes. The
bump allocator for strings/arrays is now kernel work, not a
Phase C promise: the roadmap's original allocator line is
superseded by this honest v1.

### Phase D — Traps, interrupts, and firmware calls (DONE 27 Oct 2026)

- CSR builtins: `csr_read(csr) -> int` (expression) and
  statement-only `csr_write`/`csr_set`/`csr_clear` (like
  `poke32`). The CSR number must be a literal: RISC-V CSR
  instructions take a 12-bit immediate, not a register, so a
  runtime value cannot encode one — the checker enforces this.
  Native and WASM reject all four loudly (no RISC-V CSRs there).
- Trap-handler hook: defining `fn trap_handler()` (no args,
  void — enforced by the big32 backend) makes `_start` point
  `mtvec` at an assembly stub that saves all 30 clobberable
  registers on the stack, calls the handler, restores, and
  `mret`s. The stub does NOT touch `mepc`: advancing past an
  ecall is the handler's job (read `mcause`/`mepc`, write
  `mepc+4` for ecall traps). Program end still halts with a
  handler wired: main's ending (and fail/assert paths) clear
  `mtvec` before the final ecall, since a bare ecall with
  `mtvec` set would trap, not halt.
- `ecall(eid, arg) -> int`: extension id in `a7`, argument in
  `a0`, result back in `a0`. On SBI firmware this is the SBI
  call primitive; on the model it traps to the program's own
  handler. v1 covers single-argument calls only — full `sbiret`
  (error in `a0`, value in `a1`) and two-argument calls are
  named follow-up, not done.
- Honest checkpoint correction: the model's timer does not
  exist — there is no CLINT, no interrupt delivery, and no SBI
  emulation in `model.py`, so a "timer tick" cannot reach Jal
  Pari code there. The checkpoint is therefore ecall-driven,
  not timer-driven: `tests/test_traps.py` (18 checks) proves
  CSR set/clear/read, an `mscratch` round-trip, an ecall trap
  firing the handler and returning to continue, the exact UART
  transcript `SCRTK`, and a clean halt (not a slide through
  NOPs). A real timer tick needs model or hardware interrupt
  delivery first — that is Phase E bring-up work, not something
  Phase D can fake. Using the existing big32 SBI firmware as a
  bootloader/firmware layer stays honest, not cheating:
  TempleOS also ran on BIOS/UEFI firmware. The kernel itself
  is still ours; SBI is the floor it stands on, and later
  phases can replace SBI console/timer use with direct
  drivers.

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
