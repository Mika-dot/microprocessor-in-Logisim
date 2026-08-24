"""Assembler, microcode description and cycle-accurate MT16 reference model.

The Logisim machine uses four hardware contexts and one shared datapath.  Every
instruction is exactly two bytes and is executed by the same three-step
microprogram: FETCH_OPCODE, FETCH_OPERAND, EXECUTE.  The scheduler selects the
next context after every microstep, so independent threads hide the latency of
the microcoded core rather than merely time-slicing whole programs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import re
from typing import Iterable


class Opcode(IntEnum):
    NOP = 0x00
    LDI = 0x01
    LD = 0x02
    ST = 0x03
    ADD = 0x04
    SUB = 0x05
    AND = 0x06
    OR = 0x07
    XOR = 0x08
    NOT = 0x09
    SHL = 0x0A
    SHR = 0x0B
    JMP = 0x0C
    JZ = 0x0D
    ATOMADD = 0x0E
    HALT = 0x0F


@dataclass(frozen=True)
class MicrocodeWord:
    opcode: Opcode
    mnemonic: str
    acc_source: str = "hold"
    alu: str = "pass"
    write_acc: bool = False
    write_memory: bool = False
    write_pc: bool = False
    conditional_zero: bool = False
    atomic: bool = False
    halt: bool = False

    def encode(self) -> int:
        """Encode the control word exactly as stored in Logisim's control ROM."""
        acc_sources = {"hold": 0, "immediate": 1, "memory": 2, "alu": 3, "old_memory": 4}
        alu_ops = {"pass": 0, "add": 1, "sub": 2, "and": 3, "or": 4,
                   "xor": 5, "not": 6, "shl": 7, "shr": 8}
        value = acc_sources[self.acc_source]
        value |= alu_ops[self.alu] << 3
        value |= int(self.write_acc) << 7
        value |= int(self.write_memory) << 8
        value |= int(self.write_pc) << 9
        value |= int(self.conditional_zero) << 10
        value |= int(self.atomic) << 11
        value |= int(self.halt) << 12
        return value


MICROCODE: tuple[MicrocodeWord, ...] = (
    MicrocodeWord(Opcode.NOP, "NOP"),
    MicrocodeWord(Opcode.LDI, "LDI", "immediate", write_acc=True),
    MicrocodeWord(Opcode.LD, "LD", "memory", write_acc=True),
    MicrocodeWord(Opcode.ST, "ST", write_memory=True),
    MicrocodeWord(Opcode.ADD, "ADD", "alu", "add", write_acc=True),
    MicrocodeWord(Opcode.SUB, "SUB", "alu", "sub", write_acc=True),
    MicrocodeWord(Opcode.AND, "AND", "alu", "and", write_acc=True),
    MicrocodeWord(Opcode.OR, "OR", "alu", "or", write_acc=True),
    MicrocodeWord(Opcode.XOR, "XOR", "alu", "xor", write_acc=True),
    MicrocodeWord(Opcode.NOT, "NOT", "alu", "not", write_acc=True),
    MicrocodeWord(Opcode.SHL, "SHL", "alu", "shl", write_acc=True),
    MicrocodeWord(Opcode.SHR, "SHR", "alu", "shr", write_acc=True),
    MicrocodeWord(Opcode.JMP, "JMP", write_pc=True),
    MicrocodeWord(Opcode.JZ, "JZ", write_pc=True, conditional_zero=True),
    MicrocodeWord(Opcode.ATOMADD, "ATOMADD", "old_memory", "add", True, True, atomic=True),
    MicrocodeWord(Opcode.HALT, "HALT", halt=True),
)


@dataclass
class AssembledImage:
    programs: list[list[int]]
    data: list[int]
    symbols: list[dict[str, int]]


@dataclass
class _SourceInstruction:
    opcode: Opcode
    operand: str | None
    line: int


def _number(token: str) -> int:
    token = token.replace("_", "")
    if token.startswith("'") and token.endswith("'") and len(token) == 3:
        return ord(token[1])
    return int(token, 0)


def assemble(source: str) -> AssembledImage:
    """Assemble a four-thread MT16 source file.

    Directives:
      .thread N              select program ROM 0..3
      .data ADDRESS VALUE    initialize a shared 16-bit RAM word
      .fill ADDRESS COUNT VALUE
    Labels are local to their thread and resolve to byte addresses.
    """
    pending: list[list[_SourceInstruction]] = [[] for _ in range(4)]
    symbols: list[dict[str, int]] = [dict() for _ in range(4)]
    data = [0] * 256
    thread = 0

    for line_no, raw in enumerate(source.splitlines(), 1):
        line = re.split(r"[;#]", raw, maxsplit=1)[0].strip()
        if not line:
            continue
        if line.startswith(".thread"):
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"line {line_no}: expected '.thread N'")
            thread = _number(parts[1])
            if not 0 <= thread < 4:
                raise ValueError(f"line {line_no}: thread must be 0..3")
            continue
        if line.startswith(".data"):
            parts = line.split()
            if len(parts) != 3:
                raise ValueError(f"line {line_no}: expected '.data address value'")
            address, value = _number(parts[1]), _number(parts[2])
            if not 0 <= address <= 0xFF or not -0x8000 <= value <= 0xFFFF:
                raise ValueError(f"line {line_no}: data value or address is out of range")
            data[address] = value & 0xFFFF
            continue
        if line.startswith(".fill"):
            parts = line.split()
            if len(parts) != 4:
                raise ValueError(f"line {line_no}: expected '.fill address count value'")
            address, count, value = map(_number, parts[1:])
            if address < 0 or count < 0 or address + count > 256:
                raise ValueError(f"line {line_no}: fill is out of RAM range")
            data[address:address + count] = [value & 0xFFFF] * count
            continue

        if ":" in line:
            label, line = (part.strip() for part in line.split(":", 1))
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
                raise ValueError(f"line {line_no}: invalid label {label!r}")
            if label in symbols[thread]:
                raise ValueError(f"line {line_no}: duplicate label {label!r}")
            symbols[thread][label] = len(pending[thread]) * 2
            if not line:
                continue

        parts = line.replace(",", " ").split()
        try:
            opcode = Opcode[parts[0].upper()]
        except KeyError as error:
            raise ValueError(f"line {line_no}: unknown instruction {parts[0]!r}") from error
        if len(parts) > 2:
            raise ValueError(f"line {line_no}: too many operands")
        pending[thread].append(_SourceInstruction(opcode, parts[1] if len(parts) == 2 else None, line_no))

    programs: list[list[int]] = []
    no_operand = {Opcode.NOP, Opcode.NOT, Opcode.SHL, Opcode.SHR, Opcode.HALT}
    for tid, instructions in enumerate(pending):
        program: list[int] = []
        for instruction in instructions:
            if instruction.operand is None:
                if instruction.opcode not in no_operand:
                    raise ValueError(f"line {instruction.line}: {instruction.opcode.name} needs an operand")
                operand = 0
            else:
                if instruction.opcode in no_operand:
                    raise ValueError(f"line {instruction.line}: {instruction.opcode.name} takes no operand")
                token = instruction.operand
                operand = symbols[tid].get(token, None)
                if operand is None:
                    try:
                        operand = _number(token)
                    except ValueError as error:
                        raise ValueError(f"line {instruction.line}: unknown label {token!r}") from error
            if not 0 <= operand <= 0xFF:
                raise ValueError(f"line {instruction.line}: operand is out of 8-bit range")
            program.extend((int(instruction.opcode), operand))
        if len(program) > 256:
            raise ValueError(f"thread {tid}: program exceeds 256 bytes")
        programs.append(program + [0] * (256 - len(program)))
    return AssembledImage(programs, data, symbols)


@dataclass
class ThreadContext:
    pc: int = 0
    acc: int = 0
    ir: int = 0
    operand: int = 0
    microstep: int = 0
    zero: bool = True
    halted: bool = False
    retired: int = 0


@dataclass
class TraceEvent:
    tick: int
    thread: int
    microstep: int
    pc: int
    opcode: str
    acc: int


@dataclass
class Machine:
    image: AssembledImage
    contexts: list[ThreadContext] = field(default_factory=lambda: [ThreadContext() for _ in range(4)])
    scheduler: int = 0
    ticks: int = 0
    trace: list[TraceEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.programs = [list(program) for program in self.image.programs]
        self.memory = list(self.image.data)

    def _set_acc(self, context: ThreadContext, value: int) -> None:
        context.acc = value & 0xFFFF
        context.zero = context.acc == 0

    def tick(self) -> None:
        tid = self.scheduler
        context = self.contexts[tid]
        self.scheduler = (self.scheduler + 1) & 3
        self.ticks += 1
        if context.halted:
            return

        if context.microstep == 0:
            context.ir = self.programs[tid][context.pc]
            context.pc = (context.pc + 1) & 0xFF
            context.microstep = 1
        elif context.microstep == 1:
            context.operand = self.programs[tid][context.pc]
            context.pc = (context.pc + 1) & 0xFF
            context.microstep = 2
        else:
            try:
                opcode = Opcode(context.ir)
            except ValueError as error:
                raise RuntimeError(f"thread {tid}: illegal opcode 0x{context.ir:02x}") from error
            self._execute(context, opcode, context.operand)
            context.microstep = 0
            context.retired += 1
            self.trace.append(TraceEvent(self.ticks, tid, 2, context.pc, opcode.name, context.acc))

    def _execute(self, c: ThreadContext, opcode: Opcode, operand: int) -> None:
        memory_value = self.memory[operand]
        if opcode == Opcode.NOP:
            pass
        elif opcode == Opcode.LDI:
            self._set_acc(c, operand)
        elif opcode == Opcode.LD:
            self._set_acc(c, memory_value)
        elif opcode == Opcode.ST:
            self.memory[operand] = c.acc
        elif opcode == Opcode.ADD:
            self._set_acc(c, c.acc + memory_value)
        elif opcode == Opcode.SUB:
            self._set_acc(c, c.acc - memory_value)
        elif opcode == Opcode.AND:
            self._set_acc(c, c.acc & memory_value)
        elif opcode == Opcode.OR:
            self._set_acc(c, c.acc | memory_value)
        elif opcode == Opcode.XOR:
            self._set_acc(c, c.acc ^ memory_value)
        elif opcode == Opcode.NOT:
            self._set_acc(c, ~c.acc)
        elif opcode == Opcode.SHL:
            self._set_acc(c, c.acc << 1)
        elif opcode == Opcode.SHR:
            self._set_acc(c, c.acc >> 1)
        elif opcode == Opcode.JMP:
            c.pc = operand
        elif opcode == Opcode.JZ:
            if c.zero:
                c.pc = operand
        elif opcode == Opcode.ATOMADD:
            # The complete read-modify-write happens in one EXECUTE microstep.
            self.memory[operand] = (memory_value + c.acc) & 0xFFFF
            self._set_acc(c, memory_value)
        elif opcode == Opcode.HALT:
            c.halted = True
        else:  # pragma: no cover - IntEnum and exhaustive branch above guard this.
            raise AssertionError(opcode)

    def run(self, max_ticks: int = 100_000) -> "Machine":
        while not all(context.halted for context in self.contexts):
            if self.ticks >= max_ticks:
                raise TimeoutError(f"machine did not halt after {max_ticks} ticks")
            self.tick()
        return self

    def retired_by_thread(self) -> tuple[int, int, int, int]:
        return tuple(c.retired for c in self.contexts)  # type: ignore[return-value]


def hex_image(values: Iterable[int], width: int) -> str:
    digits = (width + 3) // 4
    return "v3.0 hex words addressed\n" + " ".join(f"{value & ((1 << width) - 1):0{digits}x}" for value in values) + "\n"
