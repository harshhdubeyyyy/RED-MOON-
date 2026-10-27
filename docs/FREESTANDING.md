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
- Trap-handler hook: defining `fn trap_handler()` (no args, or
  one int = the trap-frame pointer since Phase E — enforced by
  the big32 backend) makes `_start` point `mtvec` at an assembly
  stub that saves all 30 clobberable registers on the stack,
  passes the frame pointer in `a0`, calls the handler, and —
  if the handler wrote a non-zero frame pointer to `mscratch` —
  switches stacks before restoring and `mret`ing. The stub does
  NOT touch `mepc`: advancing past an ecall is the handler's
  job (read `mcause`/`mepc`, write `mepc+4` for ecall traps).
  Program end still halts with a handler wired: main's ending
  (and fail/assert paths) clear `mtvec` before the final ecall,
  since a bare ecall with `mtvec` set would trap, not halt.
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

**Checkpoint 1 DONE 27 Oct 2026 — timer tick (model + kernel):**
the Python big32 model gained a minimal timer (mtime 0x10000010,
mtimecmp 0x10000018, 32-bit halves, mtime +1 per step; mip.MTIP
level-sensitive while mtime >= mtimecmp; delivery needs mtvec set
+ mstatus.MIE + mie.MTIE; trap entry saves MIE into MPIE and
clears MIE, mret restores it — without that, the first handler
instruction would re-trap before the handler could reprogram
mtimecmp). The Verilog has no CLINT yet, so this is model-only
so far. Kernel `examples/os/kernel_tick.fg` enables ONLY the
timer interrupt (no mcause dispatch needed), keeps its tick count
in RAM scratch 0x8000 (freestanding has no globals), prints `T`
per tick, and reprograms mtimecmp before mret. Verified:
`tests/test_kernel_tick.py` 5/5, exact UART transcript
`KERNTTTTTDONE`, halted, 5,474 steps. Phase D trap suite still
passes unchanged. NOT done yet: the round-robin scheduler
(checkpoint 2 — needs a yield path and per-task stacks, since
the trap stub restores the same frame it saved).

**Checkpoint 2 DONE 27 Oct 2026 — preemptive round-robin
scheduler:** the trap stub now passes the trap-frame pointer in
`a0` (no-arg handlers ignore it — Phase D programs unaffected)
and switches stacks when the handler writes a non-zero frame
pointer to `mscratch`. The scheduler handler saves the current
task's frame+`mepc` into its TCB each timer tick, loads the next
task's, and hands the next frame to the stub. Tasks are created
by fork: `ecall(2, 0)` copies the 120-byte trap frame onto a
fresh stack, sets the child's saved-`a0` slot to 0 and the
parent's to 1, records the child in TCB[1], and advances `mepc`
past the ecall for both. Kernel `examples/os/kernel_sched.fg`:
`KERN`, then task_a/task_b printing A/B until tick 20, when the
handler clears `mtvec` and the next ecall halts. Verified:
`tests/test_kernel_sched.py` — 907 A + 981 B, 19 A↔B switches,
halted, tick count exactly 20, 21,328 steps; trap + tick suites
still green. Honest limits: tasks must be helper functions
(main's locals live in main's frame, which fork does not copy);
explicit yield is not a switch yet (unknown ecall ids only
advance `mepc`); the timer is still model-only, Verilog has no
CLINT yet. **Phase E's three pieces — UART hello, timer tick,
scheduler — are all done.**

### Phase F and beyond — the OS itself

In order, each its own checkpoint: physical memory management and
paging; a real filesystem (start with a tiny read-only one, then
writable); processes and syscalls; a shell; a window manager and
GUI toolkit in Jal Pari; keyboard, disk, and display drivers;
networking (the capability TempleOS never had); user programs —
the Moon apps, rewritten as native OS programs. A PC port comes
only after the big32 OS is real.

**Checkpoint 1 DONE 27 Oct 2026 — bump allocator:** an allocator
needs no pointers (addresses are ints, peek32/poke32 are the
read/write). Heap [0xA000, 0xC000), bump pointer in RAM scratch
0x8040. `alloc` aligns up to 4, fails with -1 past the heap end,
else advances and returns the block; `free` is deliberately a
no-op (a free-list is checkpoint 2). Kernel
`examples/os/kernel_alloc.fg` verified by
`tests/test_kernel_alloc.py` 6/6: exact transcript
`KERNKKKKDONE`, halted, patterns intact in the model heap.
Phase E push also landed (RED-MOON- 10d9a19f -> 1c815883,
verified live) and the Phase E model timer was pushed to BIG-32
(commit 9e7ef047, verified live) — the model change is no longer
local-only.

**Checkpoint 2 DONE 27 Oct 2026 — free-list allocator:**
every block carries an 8-byte header [next, total_size] before
its payload; freed blocks live in an address-ordered list.
`alloc` first-fit searches, splits when the remainder is at
least 16 bytes, else takes the block whole, and falls back to
bump allocation; `free` inserts address-ordered and coalesces
with the next physical neighbour first, then the previous one.
Kernel `examples/os/kernel_freelist.fg` verified by
`tests/test_kernel_freelist.py` 6/6: exact transcript
`KERNKKKKDONE` (reuse of b's exact block, patterns, coalesced
re-alloc), halted, and the predicted heap state (16-byte split
remainder at 0xA038 as free-list head). Next: filesystem.

**Checkpoint 3 DONE 27 Oct 2026 — tiny filesystem:** files are
identified by numeric id, not names (freestanding rejects string
values, so names wait for a later checkpoint). Files are
fixed-size at create time, stored as contiguous 256-byte blocks:
file table in scratch 0x8060 (8 slots x 16 bytes [id, used,
size_words, start_block]), next-free-block in scratch 0x8050,
data blocks at 0xD000 (16 x 256 bytes). API: format, create,
write, read (0 ok, -1 fail; read returns -1 as a sentinel for
missing/out-of-bounds). Delete is NOT in v1 — freed blocks are
reclaimed only by reformat. Kernel `examples/os/kernel_fs.fg`
verified by `tests/test_kernel_fs.py`: exact transcript
`KERNKKKKKDONE` (create, readback, cross-block boundary,
disk-full failure, out-of-bounds failure), halted, file
contents intact in the model heap. This checkpoint also caught
and fixed a real big32 backend bug: argument registers used to
be expression temps, so under temp pressure the call-staging
loop overwrote an argument with another one (`fs_write(1, 3,
44)` stored 3 instead of 44); a-regs are now excluded from
TEMPS in `forge_lang/codegen_rv.py`. Next: delete with block
reclaim, then processes.

**Checkpoint 4 DONE 27 Oct 2026 — filesystem v2, delete with
block reclaim:** v1's contiguous files stranded freed blocks,
so v2 uses indexed allocation (the Unix direct-blocks idea):
each file owns a row of up to 16 block indices, and freed
blocks go on a free-list whose links live in the freed blocks
themselves. `create` allocates block by block (free-list first,
then bump) with clean rollback when a block allocation fails
mid-create; `delete` pushes every mapped block onto the
free-list. Kernel `examples/os/kernel_fs2.fg` verified by
`tests/test_kernel_fs2.py` 6/6: exact transcript
`KERNKKKKKDONE` (boundary, delete + reuse, disk-full failure,
full-disk re-alloc after deletes), halted, and the predicted
heap state (bump 16, free-list empty, file 5's map row in
free-list pop order). Next: processes.

**Checkpoint 5 DONE 27 Oct 2026 — processes:** process table
in scratch 0x8000 (4 slots x 16 bytes [state, frame, mepc,
exit_code]; 0 free, 1 ready, 2 running, 3 done), cooperative
switching via ecall: 2 = spawn (fork into a free slot; parent
gets the pid, child 0, -1 if no slot), 3 = yield (round-robin
to the next ready task), 4 = exit(code) (mark done, switch on;
if nobody is ready, clear mtvec and ecall, which halts). The
sharp rule: fork copies only the trap frame, not main's
function frame, so the child must branch on the spawn result
immediately, and the parent records pids into scratch before
any yield and waits on those copies, never on the shared
locals. Kernel `examples/os/kernel_proc.fg` verified by
`tests/test_kernel_proc.py` 9/9: exact transcript
`KERNABABABDONE` (the ABABAB interleave proves switching),
halted, final states [running, done, done, free], exit codes
0, pids 1 and 2 recorded, plus a probe proving the
exit-with-nobody-left halt path. Next: shell.

## What does not change

- Black Moon OS (the Linux distro) continues as the system people
  can actually use today. The from-scratch OS is a second track,
  not a replacement, until it can stand on its own.
- JalOS (the simulation) stays as the concepts prototype; its
  code does not become kernel code, its ideas do.
- Numbers in this document come from verified runs only; anything
  unbuilt is labelled as a plan, not a result.
