#!/usr/bin/env python3
"""Generate the MT16 Logisim project and deterministic hardware test vectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mt16.core import MICROCODE, Machine, Opcode, assemble  # noqa: E402


@dataclass
class Circuit:
    name: str
    items: list[str] = field(default_factory=list)

    def comp(self, lib: int, name: str, x: int, y: int, **attrs: object) -> None:
        body = "".join(
            f'<a name="{escape(str(key))}" val="{escape(str(value))}"/>'
            for key, value in attrs.items()
            if value is not None
        )
        self.items.append(f'<comp lib="{lib}" loc="({x},{y})" name="{escape(name)}">{body}</comp>')

    def memory(self, lib: int, name: str, x: int, y: int, contents: str, **attrs: object) -> None:
        body = "".join(
            f'<a name="{escape(str(key))}" val="{escape(str(value))}"/>'
            for key, value in attrs.items()
        )
        body += f'<a name="contents">{contents}</a>'
        self.items.append(f'<comp lib="{lib}" loc="({x},{y})" name="{escape(name)}">{body}</comp>')

    def wire(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.items.append(f'<wire from="({x1},{y1})" to="({x2},{y2})"/>')

    def tunnel(self, label: str, width: int, x: int, y: int) -> None:
        self.comp(0, "Tunnel", x, y, label=label, width=width if width != 1 else None)

    def constant(self, value: int, width: int, x: int, y: int) -> None:
        self.comp(0, "Constant", x, y, width=width if width != 1 else None, value=f"0x{value:x}")

    def input_pin(self, label: str, width: int, x: int, y: int) -> None:
        self.comp(0, "Pin", x, y, appearance="NewPins", label=label, width=width if width != 1 else None)

    def output_pin(self, label: str, width: int, x: int, y: int) -> None:
        self.comp(0, "Pin", x, y, appearance="NewPins", facing="west", label=label,
                  type="output", width=width if width != 1 else None)

    def register(self, label: str, width: int, x: int, y: int, data: str, enable: str) -> None:
        self.comp(4, "Register", x, y, appearance="classic", label=f"R{label}",
                  trigger="rising", width=width if width != 8 else None)
        self.tunnel(label, width, x, y)
        self.tunnel(data, width, x - 30, y)
        self.tunnel(enable, 1, x - 30, y + 10)
        self.tunnel("Clock", 1, x - 20, y + 20)
        self.tunnel("Reset", 1, x - 10, y + 20)

    def mux(self, label: str, inputs: list[str], select: str, width: int, x: int, y: int) -> None:
        bits = (len(inputs) - 1).bit_length()
        self.comp(2, "Multiplexer", x, y, enable="false", select=bits,
                  width=width if width != 1 else None)
        if len(inputs) == 2:
            for index, source in enumerate(inputs):
                self.tunnel(source, width, x - 30, y - 10 + index * 20)
            self.tunnel(select, bits, x - 20, y + 20)
        else:
            offset = -(len(inputs) // 2) * 10
            for index, source in enumerate(inputs):
                self.tunnel(source, width, x - 40, y + offset + index * 10)
            self.tunnel(select, bits, x - 20, y + (len(inputs) // 2) * 10)
        self.tunnel(label, width, x, y)

    def gate2(self, kind: str, output: str, left: str, right: str, x: int, y: int, width: int = 1) -> None:
        self.comp(1, f"{kind} Gate", x, y, width=width if width != 1 else None)
        # Default 50-unit gates place two inputs at y +/- 20. XOR has a 10-unit
        # extra lead-in compared with AND/OR.
        input_x = x - (60 if kind == "XOR" else 50)
        self.tunnel(left, width, input_x, y - 20)
        self.tunnel(right, width, input_x, y + 20)
        self.tunnel(output, width, x, y)

    def not_gate(self, output: str, source: str, x: int, y: int, width: int = 1) -> None:
        self.comp(1, "NOT Gate", x, y, width=width if width != 1 else None)
        self.tunnel(source, width, x - 30, y)
        self.tunnel(output, width, x, y)

    def comparator_eq(self, output: str, source: str, value: int, width: int, x: int, y: int) -> None:
        self.comp(3, "Comparator", x, y, mode="unsigned", width=width if width != 8 else None)
        self.tunnel(source, width, x - 40, y - 10)
        self.constant(value, width, x - 40, y + 10)
        self.tunnel(output, 1, x, y)

    def bit_selector(self, output: str, source: str, source_width: int, bit: int, x: int, y: int,
                     group: int = 1) -> None:
        self.comp(2, "BitSelector", x, y, group=group, width=source_width)
        self.tunnel(source, source_width, x - 30, y)
        groups = (source_width + group - 1) // group
        select_width = max(1, (groups - 1).bit_length())
        self.constant(bit // group, select_width, x - 10, y + 10)
        self.tunnel(output, group, x, y)

    def serialize(self) -> str:
        body = "\n    ".join(self.items)
        return (
            f'  <circuit name="{escape(self.name)}">\n'
            '    <a name="appearance" val="logisim_evolution"/>\n'
            f'    <a name="circuit" val="{escape(self.name)}"/>\n'
            '    <a name="circuitnamedboxfixedsize" val="true"/>\n'
            '    <a name="simulationFrequency" val="1.0"/>\n'
            f'    {body}\n'
            '  </circuit>'
        )


def rom_contents(values: list[int], address_width: int, data_width: int) -> str:
    digits = (data_width + 3) // 4
    rows = [" ".join(f"{value & ((1 << data_width) - 1):0{digits}x}" for value in values[i:i + 16])
            for i in range(0, len(values), 16)]
    return f"addr/data: {address_width} {data_width}\n" + "\n".join(rows) + "\n"


def add_alu(c: Circuit, prefix: str = "", microcoded: bool = False) -> None:
    p = prefix
    # Immediate extension.
    c.comp(0, "Bit Extender", 430, 1180, in_width=8, out_width=16, type="zero")
    c.tunnel(p + "OPERAND", 8, 390, 1180)
    c.tunnel(p + "IMM16", 16, 430, 1180)
    # Arithmetic and logic candidates.
    for name, kind, y in (("ADD_RESULT", "Adder", 1240), ("SUB_RESULT", "Subtractor", 1300)):
        c.comp(3, kind, 430, y, width=16)
        c.tunnel(p + "ACC", 16, 390, y - 10)
        c.tunnel(p + "MEM", 16, 390, y + 10)
        c.constant(0, 1, 410, y - 20)
        c.tunnel(p + name, 16, 430, y)
    for name, kind, y in (("AND_RESULT", "AND", 1360), ("OR_RESULT", "OR", 1420),
                          ("XOR_RESULT", "XOR", 1480)):
        c.gate2(kind, p + name, p + "ACC", p + "MEM", 440, y, 16)
    c.not_gate(p + "NOT_RESULT", p + "ACC", 440, 1540, 16)
    for name, shift, y in (("SHL_RESULT", "ll", 1600), ("SHR_RESULT", "lr", 1660)):
        c.comp(3, "Shifter", 440, y, shift=shift, width=16)
        c.tunnel(p + "ACC", 16, 400, y - 10)
        c.constant(1, 4, 400, y + 10)
        c.tunnel(p + name, 16, 440, y)
    if microcoded:
        alu_candidates = [
            p + "ACC", p + "ADD_RESULT", p + "SUB_RESULT", p + "AND_RESULT",
            p + "OR_RESULT", p + "XOR_RESULT", p + "NOT_RESULT", p + "SHL_RESULT",
            p + "SHR_RESULT",
        ] + [p + "ACC"] * 7
        c.mux(p + "ALU_RESULT", alu_candidates, p + "CTRL_ALU_OP", 16, 700, 1420)
        acc_candidates = [p + "ACC", p + "IMM16", p + "MEM", p + "ALU_RESULT",
                          p + "MEM", p + "ACC", p + "ACC", p + "ACC"]
        c.mux(p + "ACC_NEXT", acc_candidates, p + "CTRL_ACC_SOURCE", 16, 900, 1420)
    else:
        candidates = [
            p + "ACC", p + "IMM16", p + "MEM", p + "ACC",
            p + "ADD_RESULT", p + "SUB_RESULT", p + "AND_RESULT", p + "OR_RESULT",
            p + "XOR_RESULT", p + "NOT_RESULT", p + "SHL_RESULT", p + "SHR_RESULT",
            p + "ACC", p + "ACC", p + "MEM", p + "ACC",
        ]
        c.mux(p + "ACC_NEXT", candidates, p + "OPCODE", 16, 760, 1420)


def alu_circuit() -> Circuit:
    c = Circuit("ALU16")
    for label, width, y in (("ACC", 16, 100), ("MEM", 16, 140), ("OPERAND", 8, 180),
                            ("OPCODE", 4, 220)):
        c.input_pin(label, width, 100, y)
        c.tunnel(label, width, 100, y)
    add_alu(c)
    c.output_pin("RESULT", 16, 920, 1420)
    c.tunnel("ACC_NEXT", 16, 920, 1420)
    return c


def microcode_circuit(control: list[int]) -> Circuit:
    c = Circuit("MicrocodeControl")
    c.input_pin("Opcode", 4, 100, 100)
    c.memory(4, "ROM", 220, 80, rom_contents(control[:16], 4, 32),
             addrWidth=4, appearance="classic", dataWidth=32)
    c.wire(100, 100, 180, 100)
    c.wire(180, 90, 180, 100)
    c.wire(180, 90, 220, 90)
    c.output_pin("Control", 32, 560, 140)
    c.wire(460, 140, 560, 140)
    return c


def scheduler_circuit() -> Circuit:
    c = Circuit("Scheduler4")
    c.input_pin("Clock", 1, 100, 100)
    c.input_pin("Reset", 1, 100, 140)
    c.tunnel("Clock", 1, 100, 100)
    c.tunnel("Reset", 1, 100, 140)
    c.comp(3, "Adder", 300, 220, width=2)
    c.tunnel("TID", 2, 260, 210)
    c.constant(1, 2, 260, 230)
    c.constant(0, 1, 280, 200)
    c.tunnel("TID_NEXT", 2, 300, 220)
    c.register("TID", 2, 420, 220, "TID_NEXT", "ONE")
    c.constant(1, 1, 390, 230)
    c.output_pin("Thread", 2, 540, 220)
    c.tunnel("TID", 2, 540, 220)
    return c


def computer_circuit(programs: list[list[int]], control: list[int]) -> Circuit:
    c = Circuit("MT16_Computer")
    c.input_pin("Clock", 1, 100, 100)
    c.input_pin("Reset", 1, 100, 140)
    c.tunnel("Clock", 1, 100, 100)
    c.tunnel("Reset", 1, 100, 140)

    # Round-robin hardware-thread selector.
    c.comp(3, "Adder", 300, 220, width=2)
    c.tunnel("TID", 2, 260, 210)
    c.constant(1, 2, 260, 230)
    c.constant(0, 1, 280, 200)
    c.tunnel("TID_NEXT", 2, 300, 220)
    c.register("TID", 2, 420, 220, "TID_NEXT", "SCHED_EN")
    c.constant(1, 1, 390, 230)
    c.comp(2, "Decoder", 540, 220, enable="false", select=2)
    c.tunnel("TID", 2, 540, 220)
    for tid, y in enumerate((180, 190, 200, 210)):
        c.tunnel(f"ACTIVE{tid}", 1, 560, y)

    # Four complete architectural contexts.
    columns = (
        ("PC", 8, "PC_NEXT", "PC_WE", 300),
        ("ACC", 16, "ACC_NEXT", "ACC_WE", 500),
        ("IR", 8, "PROG", "IR_WE", 700),
        ("OPERAND", 8, "PROG", "OPERAND_WE", 900),
        ("STATE", 2, "STATE_NEXT", "STATE_WE", 1100),
        ("ZERO", 1, "ZERO_NEXT", "ZERO_WE", 1300),
        ("HALT", 1, "ONE", "HALT_WE", 1500),
    )
    for tid in range(4):
        y = 420 + tid * 100
        for name, width, data, global_we, x in columns:
            local_we = f"{global_we}{tid}"
            c.gate2("AND", local_we, global_we, f"ACTIVE{tid}", x - 80, y + 70)
            c.register(f"{name}{tid}", width, x, y, data, local_we)

    for name, width, _, _, x in columns:
        c.mux(name, [f"{name}{tid}" for tid in range(4)], "TID", width, x + 80, 860)

    # Program ROM per hardware thread; the selected context chooses the ROM output.
    for tid, y in enumerate((920, 1090, 1260, 1430)):
        c.memory(4, "ROM", 100, y, rom_contents(programs[tid], 8, 8),
                 addrWidth=8, appearance="classic", dataWidth=8, label=f"THREAD_{tid}_ROM")
        c.tunnel("PC", 8, 100, y + 10)
        c.tunnel(f"PROG{tid}", 8, 340, y + 60)
    c.mux("PROG", [f"PROG{tid}" for tid in range(4)], "TID", 8, 460, 1190)

    # Opcode extraction and genuine microcode control store.
    c.bit_selector("OPCODE", "IR", 8, 0, 720, 980, group=4)
    c.memory(4, "ROM", 800, 920, rom_contents(control[:16], 4, 32),
             addrWidth=4, appearance="classic", dataWidth=32, label="CONTROL_ROM")
    c.tunnel("OPCODE", 4, 800, 930)
    c.tunnel("CONTROL", 32, 1040, 980)
    c.bit_selector("CTRL_ACC_SOURCE", "CONTROL", 32, 0, 1100, 860, group=3)
    # Shift by three so the ALU operation in control bits 6:3 can be selected
    # as a naturally aligned four-bit field.
    c.comp(3, "Shifter", 1100, 900, shift="lr", width=32)
    c.tunnel("CONTROL", 32, 1060, 890)
    c.constant(3, 5, 1060, 910)
    c.tunnel("CONTROL_SHIFT3", 32, 1100, 900)
    c.bit_selector("CTRL_ALU_OP", "CONTROL_SHIFT3", 32, 0, 1180, 900, group=4)
    for name, bit, x in (("CTRL_WACC", 7, 1160), ("CTRL_WMEM", 8, 1220),
                         ("CTRL_WPC", 9, 1280), ("CTRL_COND", 10, 1340),
                         ("CTRL_ATOMIC", 11, 1400), ("CTRL_HALT", 12, 1460)):
        c.bit_selector(name, "CONTROL", 32, bit, x, 980)

    # Shared data memory. Ports are explicit to keep the generated project testable.
    c.comp(4, "RAM", 1720, 920, addrWidth=8, appearance="classic", asyncread="true",
           byteenables="NobyteEnables", dataWidth=16, databus="bibus", enables="byte",
           label="SHARED_RAM", trigger="rising")
    c.tunnel("OPERAND", 8, 1720, 930)
    c.tunnel("MEM_WRITE_DATA", 16, 1720, 1010)
    c.tunnel("MEM_WE", 1, 1720, 970)
    c.tunnel("ONE", 1, 1720, 980)
    c.tunnel("Clock", 1, 1720, 990)
    c.tunnel("MEM", 16, 1960, 1010)

    # Microsequencer: FETCH_OPCODE -> FETCH_OPERAND -> EXECUTE.
    for state, y in enumerate((1080, 1140, 1200)):
        c.comparator_eq(f"S{state}", "STATE", state, 2, 1180, y)
    c.not_gate("RUN", "HALT", 1280, 1080)
    c.gate2("AND", "FETCH_OPCODE", "RUN", "S0", 1380, 1080)
    c.gate2("AND", "FETCH_OPERAND", "RUN", "S1", 1380, 1140)
    c.gate2("AND", "EXECUTE", "RUN", "S2", 1380, 1200)
    c.mux("STATE_NEXT", ["CONST_STATE1", "CONST_STATE2", "CONST_STATE0", "CONST_STATE0"],
          "STATE", 2, 1580, 1140)
    c.constant(1, 2, 1540, 1120)
    c.constant(2, 2, 1540, 1130)
    c.constant(0, 2, 1540, 1140)
    c.constant(0, 2, 1540, 1150)
    c.tunnel("RUN", 1, 1640, 1200); c.tunnel("STATE_WE", 1, 1640, 1200)
    c.tunnel("FETCH_OPCODE", 1, 1640, 1220); c.tunnel("IR_WE", 1, 1640, 1220)
    c.tunnel("FETCH_OPERAND", 1, 1640, 1240); c.tunnel("OPERAND_WE", 1, 1640, 1240)

    # PC datapath and conditional branch decision.
    c.comp(3, "Adder", 1180, 1300, width=8)
    c.tunnel("PC", 8, 1140, 1290); c.constant(1, 8, 1140, 1310); c.constant(0, 1, 1160, 1280)
    c.tunnel("PC_PLUS1", 8, 1180, 1300)
    c.not_gate("UNCONDITIONAL", "CTRL_COND", 1280, 1300)
    c.gate2("OR", "BRANCH_OK", "UNCONDITIONAL", "ZERO", 1380, 1300)
    c.gate2("AND", "BRANCH_REQ", "EXECUTE", "CTRL_WPC", 1480, 1280)
    c.gate2("AND", "BRANCH_TAKEN", "BRANCH_REQ", "BRANCH_OK", 1580, 1300)
    c.mux("PC_NEXT", ["PC_PLUS1", "OPERAND"], "BRANCH_TAKEN", 8, 1700, 1320)
    c.gate2("OR", "FETCH_ANY", "FETCH_OPCODE", "FETCH_OPERAND", 1480, 1360)
    c.gate2("OR", "PC_WE", "FETCH_ANY", "BRANCH_TAKEN", 1580, 1360)

    # ALU candidates, accumulator writeback and zero flag.
    add_alu(c, microcoded=True)
    c.gate2("AND", "ACC_WE", "EXECUTE", "CTRL_WACC", 920, 1740)
    c.tunnel("ACC_WE", 1, 1020, 1740); c.tunnel("ZERO_WE", 1, 1020, 1740)
    c.comp(3, "Comparator", 920, 1800, mode="unsigned", width=16)
    c.tunnel("ACC_NEXT", 16, 880, 1790); c.constant(0, 16, 880, 1810)
    c.tunnel("ZERO_NEXT", 1, 920, 1800)

    # Store and atomic fetch-add share the same synchronous RAM write port.
    c.mux("MEM_WRITE_DATA", ["ACC", "ADD_RESULT"], "CTRL_ATOMIC", 16, 1180, 1840)
    c.gate2("AND", "MEM_WE", "EXECUTE", "CTRL_WMEM", 1300, 1840)
    c.gate2("AND", "HALT_WE", "EXECUTE", "CTRL_HALT", 1420, 1840)
    c.constant(1, 1, 1520, 1840); c.tunnel("ONE", 1, 1520, 1840)

    # Memory-mapped output latches and atomic-counter monitor.
    taps = (("OUT0", 0xF0), ("OUT1", 0xF1), ("OUT2", 0xF2), ("OUT3", 0xF3),
            ("ATOMIC_COUNT", 0x30))
    for index, (name, address) in enumerate(taps):
        y = 1940 + index * 80
        c.comparator_eq(f"ADDR_{name}", "OPERAND", address, 8, 1760, y)
        c.gate2("AND", f"WE_{name}", "MEM_WE", f"ADDR_{name}", 1860, y)
        c.register(name, 16, 2020, y, "MEM_WRITE_DATA", f"WE_{name}")

    # External observability: enough state to single-step and debug without opening subcircuits.
    outputs = (("OUT0", 16), ("OUT1", 16), ("OUT2", 16), ("OUT3", 16),
               ("ATOMIC_COUNT", 16), ("TID", 2), ("PC", 8), ("ACC", 16),
               ("IR", 8), ("OPERAND", 8), ("STATE", 2), ("HALT", 1))
    for index, (name, width) in enumerate(outputs):
        y = 120 + index * 50
        c.output_pin(name if name != "HALT" else "CurrentHalt", width, 2460, y)
        c.tunnel(name, width, 2460, y)
    c.comp(1, "AND Gate", 2320, 760, inputs=4)
    for tid, dy in enumerate((-20, -10, 10, 20)):
        c.tunnel(f"HALT{tid}", 1, 2270, 760 + dy)
    c.tunnel("ALL_HALTED", 1, 2320, 760)
    c.output_pin("AllHalted", 1, 2460, 760); c.tunnel("ALL_HALTED", 1, 2460, 760)
    return c


def alu_vectors() -> str:
    rows = ["ACC[16] MEM[16] OPERAND[8] OPCODE[4] RESULT[16]"]
    tests = {
        0x0: 0x1234, 0x1: 0x00AB, 0x2: 0x0100, 0x3: 0x1234,
        0x4: 0x1334, 0x5: 0x1134, 0x6: 0x0000, 0x7: 0x1334,
        0x8: 0x1334, 0x9: 0xEDCB, 0xA: 0x2468, 0xB: 0x091A,
        0xC: 0x1234, 0xD: 0x1234, 0xE: 0x0100, 0xF: 0x1234,
    }
    for opcode, expected in tests.items():
        rows.append(f"0x1234 0x0100 0xab 0x{opcode:x} 0x{expected:04x}")
    return "\n".join(rows) + "\n"


def microcode_vectors(control: list[int]) -> str:
    rows = ["Opcode[4] Control[32]"]
    rows.extend(f"0x{opcode:x} 0x{control[opcode]:08x}" for opcode in range(16))
    return "\n".join(rows) + "\n"


def scheduler_vectors() -> str:
    rows = ["<set> <seq> Clock Reset Thread[2]", "1 1 0 1 0x0", "1 2 1 1 0x0", "1 3 0 0 0x0"]
    seq = 4
    value = 0
    for _ in range(8):
        value = (value + 1) & 3
        rows.append(f"1 {seq} 1 0 0x{value:x}"); seq += 1
        rows.append(f"1 {seq} 0 0 0x{value:x}"); seq += 1
    return "\n".join(rows) + "\n"


def demo_vectors(ticks: int, expected: list[int], atomic: int) -> str:
    rows = ["<set> <seq> Clock Reset OUT0[16] OUT1[16] OUT2[16] OUT3[16] ATOMIC_COUNT[16] AllHalted TID[2] STATE[2]"]
    rows.append("1 1 0 1 0 0 0 0 0 0 0 0")
    rows.append("1 2 1 1 0 0 0 0 0 0 0 0")
    rows.append("1 3 0 0 <DC> <DC> <DC> <DC> <DC> 0 0 0")
    seq = 4
    for _ in range(ticks):
        rows.append(f"1 {seq} 1 0 <DC> <DC> <DC> <DC> <DC> <DC> <DC> <DC>"); seq += 1
        rows.append(f"1 {seq} 0 0 <DC> <DC> <DC> <DC> <DC> <DC> <DC> <DC>"); seq += 1
    rows.append(
        f"1 {seq} 0 0 " + " ".join(f"0x{value:04x}" for value in expected)
        + f" 0x{atomic:04x} 1 <DC> <DC>"
    )
    return "\n".join(rows) + "\n"


def main() -> int:
    source = (ROOT / "programs" / "demo.mt16").read_text(encoding="utf-8")
    image = assemble(source)
    machine = Machine(image).run()
    control = [0] * 16
    for word in MICROCODE:
        control[int(word.opcode)] = word.encode()
    circuits = [alu_circuit(), microcode_circuit(control), scheduler_circuit(),
                computer_circuit(image.programs, control)]
    project = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<project source="4.1.0" version="1.0">
  <lib desc="#Wiring" name="0"/><lib desc="#Gates" name="1"/><lib desc="#Plexers" name="2"/><lib desc="#Arithmetic" name="3"/><lib desc="#Memory" name="4"/><lib desc="#I/O" name="5"/><lib desc="#TTL" name="6"/><lib desc="#TCL" name="7"/><lib desc="#Base" name="8"/>
  <main name="MT16_Computer"/>
  <options><a name="gateUndefined" val="ignore"/><a name="simlimit" val="10000"/><a name="simrand" val="0"/></options>
""" + "\n".join(circuit.serialize() for circuit in circuits) + "\n</project>\n"
    (ROOT / "hardware" / "MT16-Barrel-PC.circ").write_text(project, encoding="utf-8")
    tests = ROOT / "hardware" / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "alu.txt").write_text(alu_vectors(), encoding="ascii")
    (tests / "microcode.txt").write_text(microcode_vectors(control), encoding="ascii")
    (tests / "scheduler.txt").write_text(scheduler_vectors(), encoding="ascii")
    (tests / "demo.txt").write_text(
        demo_vectors(machine.ticks, machine.memory[0xF0:0xF4], machine.memory[0x30]), encoding="ascii")
    print(f"generated MT16-Barrel-PC.circ and {2 * machine.ticks + 4} sequential demo vectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
