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
    appearance: list[str] = field(default_factory=list)

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

    def bus(self, label: str, width: int, x1: int, y: int, x2: int) -> None:
        """Draw a real named backplane wire, not a decorative line."""
        self.tunnel(label, width, x1, y)
        self.wire(x1, y, x2, y)
        self.tunnel(label, width, x2, y)

    def tunnel(self, label: str, width: int, x: int, y: int) -> None:
        self.comp(0, "Tunnel", x, y, label=label, width=width if width != 1 else None)

    def constant(self, value: int, width: int, x: int, y: int) -> None:
        self.comp(0, "Constant", x, y, width=width if width != 1 else None, value=f"0x{value:x}")

    def input_pin(self, label: str, width: int, x: int, y: int) -> None:
        self.comp(0, "Pin", x, y, appearance="NewPins", label=label, width=width if width != 1 else None)

    def output_pin(self, label: str, width: int, x: int, y: int) -> None:
        self.comp(0, "Pin", x, y, appearance="NewPins", facing="west", label=label,
                  type="output", width=width if width != 1 else None)

    def text(self, value: str, x: int, y: int, size: int = 14, bold: bool = False,
             align: str = "left") -> None:
        weight = "bold" if bold else "plain"
        self.comp(8, "Text", x, y, text=value, font=f"SansSerif {weight} {size}",
                  halign=align)

    def register(self, label: str, width: int, x: int, y: int, data: str, enable: str) -> None:
        self.comp(4, "Register", x, y, appearance="classic", label=f"R{label}",
                  trigger="rising", width=width if width != 8 else None)
        self.wire(x, y, x + 10, y); self.tunnel(label, width, x + 10, y)
        self.tunnel(data, width, x - 40, y); self.wire(x - 40, y, x - 30, y)
        self.tunnel(enable, 1, x - 40, y + 10); self.wire(x - 40, y + 10, x - 30, y + 10)
        self.tunnel("Clock", 1, x - 20, y + 30); self.wire(x - 20, y + 20, x - 20, y + 30)
        self.tunnel("Reset", 1, x - 10, y + 30); self.wire(x - 10, y + 20, x - 10, y + 30)

    def mux(self, label: str, inputs: list[str], select: str, width: int, x: int, y: int) -> None:
        bits = (len(inputs) - 1).bit_length()
        self.comp(2, "Multiplexer", x, y, enable="false", select=bits,
                  width=width if width != 1 else None)
        if len(inputs) == 2:
            for index, source in enumerate(inputs):
                py = y - 10 + index * 20
                self.tunnel(source, width, x - 40, py); self.wire(x - 40, py, x - 30, py)
            self.tunnel(select, bits, x - 20, y + 30); self.wire(x - 20, y + 20, x - 20, y + 30)
        else:
            offset = -(len(inputs) // 2) * 10
            for index, source in enumerate(inputs):
                py = y + offset + index * 10
                self.tunnel(source, width, x - 50, py); self.wire(x - 50, py, x - 40, py)
            sy = y + (len(inputs) // 2) * 10
            self.tunnel(select, bits, x - 20, sy + 10); self.wire(x - 20, sy, x - 20, sy + 10)
        self.wire(x, y, x + 10, y); self.tunnel(label, width, x + 10, y)

    def gate2(self, kind: str, output: str, left: str, right: str, x: int, y: int, width: int = 1) -> None:
        self.comp(1, f"{kind} Gate", x, y, width=width if width != 1 else None)
        # Default 50-unit gates place two inputs at y +/- 20. XOR has a 10-unit
        # extra lead-in compared with AND/OR.
        input_x = x - (60 if kind == "XOR" else 50)
        self.tunnel(left, width, input_x - 10, y - 20); self.wire(input_x - 10, y - 20, input_x, y - 20)
        self.tunnel(right, width, input_x - 10, y + 20); self.wire(input_x - 10, y + 20, input_x, y + 20)
        self.wire(x, y, x + 10, y); self.tunnel(output, width, x + 10, y)

    def not_gate(self, output: str, source: str, x: int, y: int, width: int = 1) -> None:
        self.comp(1, "NOT Gate", x, y, width=width if width != 1 else None)
        self.tunnel(source, width, x - 40, y); self.wire(x - 40, y, x - 30, y)
        self.wire(x, y, x + 10, y); self.tunnel(output, width, x + 10, y)

    def comparator_eq(self, output: str, source: str, value: int, width: int, x: int, y: int) -> None:
        self.comp(3, "Comparator", x, y, mode="unsigned", width=width if width != 8 else None)
        self.tunnel(source, width, x - 50, y - 10); self.wire(x - 50, y - 10, x - 40, y - 10)
        self.constant(value, width, x - 40, y + 10)
        self.wire(x, y, x + 10, y); self.tunnel(output, 1, x + 10, y)

    def bit_selector(self, output: str, source: str, source_width: int, bit: int, x: int, y: int,
                     group: int = 1) -> None:
        self.comp(2, "BitSelector", x, y, group=group, width=source_width)
        self.tunnel(source, source_width, x - 40, y); self.wire(x - 40, y, x - 30, y)
        groups = (source_width + group - 1) // group
        select_width = max(1, (groups - 1).bit_length())
        self.constant(bit // group, select_width, x - 10, y + 10)
        self.wire(x, y, x + 10, y); self.tunnel(output, group, x + 10, y)

    def serialize(self) -> str:
        body = "\n    ".join(self.items)
        appearance = ""
        if self.appearance:
            appearance = "    <appear>\n      " + "\n      ".join(self.appearance) + "\n    </appear>\n"
        appearance_mode = "custom" if self.appearance else "logisim_evolution"
        return (
            f'  <circuit name="{escape(self.name)}">\n'
            f'    <a name="appearance" val="{appearance_mode}"/>\n'
            f'    <a name="circuit" val="{escape(self.name)}"/>\n'
            '    <a name="circuitnamedboxfixedsize" val="true"/>\n'
            '    <a name="simulationFrequency" val="1.0"/>\n'
            f'{appearance}'
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
    """One completely flat computer made only from Logisim library parts."""
    c = Circuit("MT16_Computer")
    c.text("MT16 · 4-ПОТОЧНЫЙ МИКРОПРОГРАММНЫЙ КОМПЬЮТЕР", 60, 35, 25, True)
    c.text("Плоская схема: все регистры, ROM, RAM, АЛУ и управление находятся на этом листе", 60, 62, 14)
    c.text("Нажмите ▶ Ticks Enabled — встроенная программа запускается сразу", 60, 84, 14)

    # One-click clock plus deterministic pins used by the headless test bench.
    c.text("УПРАВЛЕНИЕ", 60, 118, 14, True)
    c.comp(0, "Clock", 100, 150)
    c.input_pin("Clock", 1, 100, 190)
    c.comp(1, "OR Gate", 220, 170)
    c.wire(100, 150, 170, 150); c.wire(100, 190, 170, 190)
    c.wire(220, 170, 270, 170); c.tunnel("Clock", 1, 270, 170)
    c.text("автотакт", 120, 154, 11)
    c.comp(5, "Button", 100, 250)
    c.input_pin("Reset", 1, 100, 290)
    c.comp(1, "OR Gate", 220, 270)
    c.wire(100, 250, 170, 250); c.wire(100, 290, 170, 290)
    c.wire(220, 270, 270, 270); c.tunnel("Reset", 1, 270, 270)
    c.text("сброс", 120, 254, 11)
    c.text("ПЛАНИРОВЩИК ПОТОКОВ", 300, 125, 14, True)

    # Visible master backplane. Every rail is electrically part of the named
    # signal; the nearby functional blocks tap the same nets through connectors.
    c.text("МАГИСТРАЛИ ДАННЫХ И УПРАВЛЕНИЯ", 650, 105, 14, True)
    backplane = (
        ("Clock", 1), ("Reset", 1), ("TID", 2), ("PC", 8), ("ACC", 16),
        ("IR", 8), ("OPERAND", 8), ("STATE", 2), ("CONTROL", 32), ("MEM", 16),
    )
    for index, (name, width) in enumerate(backplane):
        c.bus(name, width, 680, 130 + index * 20, 2220)

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

    c.text("4 АППАРАТНЫХ КОНТЕКСТА · PC / ACC / IR / OPERAND / STATE / ZERO / HALT", 260, 350, 14, True)

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

    # Four private program ROMs are real components on this same sheet.
    c.text("ПРОГРАММНЫЕ ROM ЧЕТЫРЁХ ПОТОКОВ", 40, 860, 14, True)
    summaries = ("SUM 1…10 → OUT0", "ЛОГИКА → OUT1", "СДВИГИ → OUT2", "40 + 2 → OUT3")
    for tid, y in enumerate((900, 1060, 1220, 1380)):
        c.memory(4, "ROM", 80, y, rom_contents(programs[tid], 8, 8),
                 addrWidth=8, appearance="classic", dataWidth=8, label=f"THREAD {tid} PROGRAM")
        c.tunnel(f"PC{tid}", 8, 20, y + 10); c.wire(20, y + 10, 80, y + 10)
        c.wire(320, y + 60, 370, y + 60); c.tunnel(f"PROG{tid}", 8, 370, y + 60)
        c.text(f"T{tid} · {summaries[tid]}", 90, y - 12, 11, True)
    c.mux("PROG", [f"PROG{tid}" for tid in range(4)], "TID", 8, 520, 1090)

    # Opcode extraction and genuine microcode control store.
    c.text("УПРАВЛЯЮЩАЯ ROM · 32-БИТНОЕ МИКРОСЛОВО", 760, 860, 14, True)
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

    # Microsequencer: FETCH_OPCODE -> FETCH_OPERAND -> EXECUTE.
    c.text("МИКРОСЕКВЕНСОР · FETCH OPCODE → FETCH OPERAND → EXECUTE", 1120, 1035, 14, True)
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
    c.text("АЛУ 16 БИТ · БАЗОВЫЕ СУММАТОРЫ, ЛОГИКА И СДВИГАТЕЛИ", 360, 1135, 14, True)
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

    # Shared 256x16 data RAM is also exposed on the main sheet. Reset clears it,
    # so reopening the project always starts the bundled demo from a clean state.
    c.text("ОБЩАЯ RAM ДАННЫХ · 256 × 16", 1880, 850, 14, True)
    c.comp(4, "RAM", 1900, 900, addrWidth=8, appearance="classic", asyncread="true",
           byteenables="NobyteEnables", dataWidth=16, databus="bibus", enables="byte",
           label="SHARED DATA RAM", trigger="rising", clearpin="true")
    c.tunnel("OPERAND", 8, 1820, 910); c.wire(1820, 910, 1900, 910)
    c.tunnel("MEM_WE", 1, 1820, 950); c.wire(1820, 950, 1900, 950)
    c.tunnel("ONE", 1, 1820, 960); c.wire(1820, 960, 1900, 960)
    c.tunnel("Clock", 1, 1820, 970); c.wire(1820, 970, 1900, 970)
    c.tunnel("MEM_WRITE_DATA", 16, 1820, 990); c.wire(1820, 990, 1900, 990)
    c.tunnel("Reset", 1, 2020, 840); c.wire(2020, 840, 2020, 900)
    c.wire(2140, 990, 2200, 990); c.tunnel("MEM", 16, 2200, 990)

    # Memory-mapped output latches and atomic-counter monitor.
    c.text("ВЫХОДНЫЕ ЗАЩЁЛКИ И АТОМАРНЫЙ СЧЁТЧИК", 1680, 1890, 14, True)
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
    c.text("НАБЛЮДЕНИЕ / РЕЗУЛЬТАТЫ", 2300, 75, 14, True)
    for index, (name, width) in enumerate(outputs):
        y = 120 + index * 50
        c.output_pin(name if name != "HALT" else "CurrentHalt", width, 2460, y)
        c.tunnel(name, width, 2380, y); c.wire(2380, y, 2460, y)
    c.comp(1, "AND Gate", 2320, 760, inputs=4)
    for tid, dy in enumerate((-20, -10, 10, 20)):
        c.tunnel(f"HALT{tid}", 1, 2270, 760 + dy)
    c.tunnel("ALL_HALTED", 1, 2320, 760)
    c.output_pin("AllHalted", 1, 2460, 760)
    c.tunnel("ALL_HALTED", 1, 2380, 760); c.wire(2380, 760, 2460, 760)
    for tid in range(4):
        c.output_pin(f"PC{tid}", 8, 2460, 820 + tid * 50)
        c.tunnel(f"PC{tid}", 8, 2380, 820 + tid * 50)
        c.wire(2380, 820 + tid * 50, 2460, 820 + tid * 50)
    c.output_pin("MEM_ADDRESS", 8, 2460, 1420)
    c.tunnel("OPERAND", 8, 2380, 1420); c.wire(2380, 1420, 2460, 1420)
    c.output_pin("MEM_WRITE_DATA", 16, 2460, 1470)
    c.tunnel("MEM_WRITE_DATA", 16, 2380, 1470); c.wire(2380, 1470, 2460, 1470)
    c.output_pin("MEM_WE", 1, 2460, 1520)
    c.tunnel("MEM_WE", 1, 2380, 1520); c.wire(2380, 1520, 2460, 1520)
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
