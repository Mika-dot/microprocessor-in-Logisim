#!/usr/bin/env python3
"""Generate a self-contained Logisim 7400-series implementation of the original 8-bit computer."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "logi7400" / "logi7400dip.circ"
IC_LIBRARY = ROOT / "logi7400" / "logi7400ic.circ"
OUT = ROOT / "ЭВМ-7400.circ"
TESTS = ROOT / "hardware7400" / "tests"


@dataclass
class Port:
    label: str
    width: int
    pin_x: int
    pin_y: int
    output: bool


@dataclass
class Circuit:
    name: str
    title: str | None = None
    items: list[str] = field(default_factory=list)
    inputs: list[Port] = field(default_factory=list)
    outputs: list[Port] = field(default_factory=list)

    def comp(self, name: str, x: int, y: int, lib: int | None = None, **attrs: object) -> None:
        prefix = f' lib="{lib}"' if lib is not None else ""
        body = "".join(
            f'<a name="{escape(str(k))}" val="{escape(str(v))}"/>'
            for k, v in attrs.items() if v is not None
        )
        self.items.append(f'<comp{prefix} loc="({x},{y})" name="{escape(name)}">{body}</comp>')

    def memory(self, name: str, x: int, y: int, contents: str, **attrs: object) -> None:
        body = "".join(
            f'<a name="{escape(str(k))}" val="{escape(str(v))}"/>'
            for k, v in attrs.items() if v is not None
        )
        body += f'<a name="contents">{contents}</a>'
        self.items.append(f'<comp lib="4" loc="({x},{y})" name="{escape(name)}">{body}</comp>')

    def wire(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.items.append(f'<wire from="({x1},{y1})" to="({x2},{y2})"/>')

    def tunnel(self, label: str, width: int, x: int, y: int, facing: str | None = None) -> None:
        self.comp("Tunnel", x, y, 0, label=label, width=width if width != 1 else None, facing=facing)

    def constant(self, label: str, value: int, width: int, x: int, y: int) -> None:
        self.comp("Constant", x, y, 0, width=width if width != 1 else None, value=f"0x{value:x}")
        self.tunnel(label, width, x, y)

    def text(self, text: str, x: int, y: int, size: int = 16) -> None:
        self.comp("Text", x, y, 6, text=text, font=f"SansSerif bold {size}", halign="left")

    def input_pin(self, label: str, width: int, x: int, y: int) -> None:
        self.comp("Pin", x, y, 0, label=label, width=width if width != 1 else None, tristate="false")
        self.tunnel(label, width, x, y)
        self.inputs.append(Port(label, width, x, y, False))

    def output_pin(self, label: str, width: int, x: int, y: int) -> None:
        self.comp("Pin", x, y, 0, label=label, width=width if width != 1 else None,
                  facing="west", output="true")
        self.tunnel(label, width, x, y)
        self.outputs.append(Port(label, width, x, y, True))

    def split_bus(self, bus: str, width: int, x: int, y: int, bits: list[str] | None = None) -> None:
        bits = bits or [f"{bus}{i}" for i in range(width)]
        self.comp("Splitter", x, y, 0, fanout=width, incoming=width)
        self.tunnel(bus, width, x, y)
        for i, bit in enumerate(bits):
            self.tunnel(bit, 1, x + 20, y - width * 10 + i * 10)

    def join_bus(self, bus: str, width: int, x: int, y: int, bits: list[str] | None = None) -> None:
        bits = bits or [f"{bus}{i}" for i in range(width)]
        self.comp("Splitter", x, y, 0, facing="west", fanout=width, incoming=width)
        self.tunnel(bus, width, x, y)
        for i, bit in enumerate(bits):
            self.tunnel(bit, 1, x - 20, y + 10 + i * 10)

    def serialize(self) -> str:
        appearance = ""
        if self.inputs or self.outputs:
            count = max(len(self.inputs), len(self.outputs), 2)
            height = max(70, 20 * count + 20)
            app = [
                f'<rect fill="#f7f2df" height="{height}" stroke="#3b3b3b" stroke-width="2" width="120" x="50" y="50"/>',
                f'<text font-family="SansSerif" font-size="12" font-weight="bold" text-anchor="middle" x="110" y="72">{escape(self.title or self.name)}</text>',
            ]
            for i, p in enumerate(self.inputs):
                app.append(f'<circ-port height="8" pin="{p.pin_x},{p.pin_y}" width="8" x="46" y="{76 + i * 20}"/>')
            for i, p in enumerate(self.outputs):
                app.append(f'<circ-port height="10" pin="{p.pin_x},{p.pin_y}" width="10" x="165" y="{75 + i * 20}"/>')
            app.append('<circ-anchor facing="east" height="6" width="6" x="167" y="77"/>')
            appearance = "<appear>" + "".join(app) + "</appear>"
        body = "\n    ".join(self.items)
        return f'  <circuit name="{escape(self.name)}">{appearance}\n    {body}\n  </circuit>'


class DipPins:
    def __init__(self, source: Path):
        root = ET.parse(source).getroot()
        self.ports: dict[str, dict[str, tuple[int, int]]] = {}
        for circuit in root.findall("circuit"):
            appear = circuit.find("appear")
            if appear is None or appear.find("circ-anchor") is None:
                continue
            labels: dict[str, str] = {}
            for comp in circuit.findall("comp"):
                if comp.get("name") != "Pin":
                    continue
                label = next((a.get("val") for a in comp.findall("a") if a.get("name") == "label"), None)
                if label:
                    labels[comp.get("loc", "").strip("()")] = label
            anchor = appear.find("circ-anchor")
            ax = int(anchor.get("x")) + int(anchor.get("width")) // 2
            ay = int(anchor.get("y")) + int(anchor.get("height")) // 2
            mapping: dict[str, tuple[int, int]] = {}
            for port in appear.findall("circ-port"):
                pin = port.get("pin", "").strip("()")
                label = labels.get(pin)
                if not label:
                    continue
                px = int(port.get("x")) + int(port.get("width")) // 2
                py = int(port.get("y")) + int(port.get("height")) // 2
                mapping[label] = (px - ax, py - ay)
            self.ports[circuit.get("name")] = mapping

    def chip(self, c: Circuit, name: str, x: int, y: int, signals: dict[str, str]) -> None:
        c.comp(name, x, y)
        mapping = self.ports[name]
        for port, signal in signals.items():
            dx, dy = mapping[port]
            c.tunnel(signal, 1, x + dx, y + dy)


DIP = DipPins(LIBRARY)
IC = DipPins(IC_LIBRARY)


def rom_contents(values: list[int], aw: int, dw: int) -> str:
    digits = (dw + 3) // 4
    rows = [" ".join(f"{v & ((1 << dw) - 1):0{digits}x}" for v in values[i:i + 16])
            for i in range(0, len(values), 16)]
    return f"addr/data: {aw} {dw}\n" + "\n".join(rows) + "\n"


def chip4(c: Circuit, name: str, x: int, y: int, a: list[str], b: list[str], q: list[str]) -> None:
    signals: dict[str, str] = {}
    for i in range(4):
        signals[f"A{i+1}"] = a[i]
        signals[f"B{i+1}"] = b[i]
        signals[f"Y{i+1}"] = q[i]
    DIP.chip(c, name, x, y, signals)


def register8() -> Circuit:
    c = Circuit("Register8_74xx", "4×7474 + 2×74157")
    c.input_pin("D", 8, 80, 100)
    c.input_pin("Clock", 1, 80, 140)
    c.input_pin("Load", 1, 80, 180)
    c.input_pin("ResetN", 1, 80, 220)
    c.output_pin("Q", 8, 1400, 100)
    c.constant("VCC", 1, 1, 100, 300)
    c.constant("GND", 0, 1, 100, 330)
    c.split_bus("D", 8, 170, 220, [f"D{i}" for i in range(8)])
    c.split_bus("Q", 8, 170, 380, [f"Q{i}" for i in range(8)])
    for base, y in ((0, 180), (4, 300)):
        sig = {"S0": "Load", "OE": "GND"}
        for i in range(4):
            sig[f"A{i+1}"] = f"Q{base+i}"
            sig[f"B{i+1}"] = f"D{base+i}"
            sig[f"Y{i+1}"] = f"NEXT{base+i}"
        DIP.chip(c, "DIP_74157", 360, y, sig)
    for pair in range(4):
        i = pair * 2
        instance(c, "IC_7474_FIXED", 600 + pair * 150, 220,
                 [(f"NEXT{i}", 1), ("Clock", 1), ("VCC", 1), ("ResetN", 1),
                  (f"NEXT{i+1}", 1), ("Clock", 1), ("VCC", 1), ("ResetN", 1)],
                 [(f"Q{i}", 1), (f"QN{i}", 1), (f"Q{i+1}", 1), (f"QN{i+1}", 1)])
    c.join_bus("Q", 8, 1280, 220, [f"Q{i}" for i in range(8)])
    c.text("U1/U2: 74HC157 — синхронный выбор hold/load без глитчей такта", 80, 520, 14)
    c.text("U3…U6: 74HC74 — восемь D-триггеров, /SET и /CLR подключены явно", 80, 545, 14)
    return c


def buffer8() -> Circuit:
    c = Circuit("Buffer8_74xx", "74HC244")
    c.input_pin("D", 8, 80, 100)
    c.input_pin("OEN", 1, 80, 140)
    c.output_pin("Q", 8, 760, 100)
    c.split_bus("D", 8, 170, 220, [f"D{i}" for i in range(8)])
    sig = {"OEA": "OEN", "OEB": "OEN"}
    sig.update({f"A{i+1}": f"D{i}" for i in range(4)})
    sig.update({f"B{i+1}": f"D{i+4}" for i in range(4)})
    sig.update({f"Y{i+1}": f"Q{i}" for i in range(4)})
    sig.update({f"Z{i+1}": f"Q{i+4}" for i in range(4)})
    DIP.chip(c, "DIP_74244", 470, 220, sig)
    c.join_bus("Q", 8, 680, 220, [f"Q{i}" for i in range(8)])
    c.text("U1: 74HC244 — реальный трёхстабильный драйвер системной шины", 80, 500, 14)
    return c


def and1() -> Circuit:
    c = Circuit("And1_7408", "74HC08")
    c.input_pin("A", 1, 80, 100)
    c.input_pin("B", 1, 80, 140)
    c.output_pin("Y", 1, 500, 100)
    DIP.chip(c, "DIP_7408", 300, 180, {"A1": "A", "B1": "B", "Y1": "Y"})
    return c


def ff_test() -> Circuit:
    c = Circuit("FFTest_7474", "74HC74 test")
    for label, y in (("D", 100), ("Clock", 140), ("SetN", 180), ("ClearN", 220)):
        c.input_pin(label, 1, 80, y)
    c.output_pin("Q", 1, 600, 100)
    c.output_pin("QN", 1, 600, 140)
    instance(c, "IC_7474_FIXED", 480, 180,
             [("D", 1), ("Clock", 1), ("SetN", 1), ("ClearN", 1),
              ("D", 1), ("Clock", 1), ("SetN", 1), ("ClearN", 1)],
             [("Q", 1), ("QN", 1), ("Q2", 1), ("QN2", 1)])
    return c


def fixed_7474() -> Circuit:
    """Corrected 7474 wrapper; the historical logi7400 pin model leaves state pins ambiguous."""
    c = Circuit("IC_7474_FIXED", "74HC74 corrected")
    for label, y in (("D1", 100), ("Clock1", 140), ("SetN1", 180), ("ClearN1", 220),
                     ("D2", 260), ("Clock2", 300), ("SetN2", 340), ("ClearN2", 380)):
        c.input_pin(label, 1, 80, y)
    for label, y in (("Q1", 100), ("R1", 140), ("Q2", 180), ("R2", 220)):
        c.output_pin(label, 1, 800, y)
    c.constant("VCC", 1, 1, 100, 460)
    DIP.chip(c, "DIP_7404", 300, 440,
             {"A1": "ClearN1", "Y1": "CLR1", "A2": "ClearN2", "Y2": "CLR2",
              "A3": "Q1", "Y3": "R1", "A4": "Q2", "Y4": "R2"})
    for idx, y in ((1, 180), (2, 320)):
        c.comp("Register", 560, y, 4, appearance="classic", trigger="rising", width=1)
        c.tunnel(f"D{idx}", 1, 530, y)
        c.tunnel("VCC", 1, 530, y + 10)
        c.tunnel(f"Clock{idx}", 1, 540, y + 20)
        c.tunnel(f"CLR{idx}", 1, 550, y + 20)
        c.tunnel(f"Q{idx}", 1, 560, y)
    c.text("Исправленная модель 74HC74: активный-low /CLR, фронт такта, два D-триггера", 80, 560, 14)
    return c


def pc8() -> Circuit:
    c = Circuit("PC8_74xx", "7474/7486/7408/74157")
    c.input_pin("D", 8, 80, 100)
    c.input_pin("Clock", 1, 80, 140)
    c.input_pin("ResetN", 1, 80, 180)
    c.input_pin("Inc", 1, 80, 220)
    c.input_pin("LoadN", 1, 80, 260)
    c.output_pin("Q", 8, 1550, 100)
    c.constant("VCC", 1, 1, 100, 340)
    c.split_bus("D", 8, 170, 260, [f"D{i}" for i in range(8)])
    c.split_bus("Q", 8, 170, 400, [f"Q{i}" for i in range(8)])
    carries = ["Inc"] + [f"C{i}" for i in range(1, 8)]
    chip4(c, "DIP_7486", 360, 180, [f"Q{i}" for i in range(4)], carries[:4], [f"IQ{i}" for i in range(4)])
    chip4(c, "DIP_7486", 360, 300, [f"Q{i}" for i in range(4, 8)], carries[4:], [f"IQ{i}" for i in range(4, 8)])
    chip4(c, "DIP_7408", 510, 180, [f"Q{i}" for i in range(4)], carries[:4], [f"C{i+1}" for i in range(4)])
    chip4(c, "DIP_7408", 510, 300, [f"Q{i}" for i in range(4, 8)], carries[4:], [f"C{i+1}" for i in range(4, 8)])
    for base, y in ((0, 180), (4, 300)):
        sig = {"S0": "LoadN", "OE": "GND"}
        for i in range(4):
            sig[f"A{i+1}"] = f"D{base+i}"
            sig[f"B{i+1}"] = f"IQ{base+i}"
            sig[f"Y{i+1}"] = f"NEXT{base+i}"
        DIP.chip(c, "DIP_74157", 660, y, sig)
    c.constant("GND", 0, 1, 100, 370)
    for pair in range(4):
        i = pair * 2
        instance(c, "IC_7474_FIXED", 850 + pair * 150, 420,
                 [(f"NEXT{i}", 1), ("Clock", 1), ("VCC", 1), ("ResetN", 1),
                  (f"NEXT{i+1}", 1), ("Clock", 1), ("VCC", 1), ("ResetN", 1)],
                 [(f"Q{i}", 1), (f"QN{i}", 1), (f"Q{i+1}", 1), (f"QN{i+1}", 1)])
    c.join_bus("Q", 8, 1450, 420, [f"Q{i}" for i in range(8)])
    c.text("Счётчик команд: восьмибитный инкрементатор + MUX загрузки + регистр 74xx", 80, 620, 14)
    return c


def step_counter() -> Circuit:
    c = Circuit("StepCounter_74xx", "74xx microstep")
    c.input_pin("Clock", 1, 80, 100)
    c.input_pin("ResetN", 1, 80, 140)
    c.input_pin("Run", 1, 80, 180)
    c.input_pin("LoadN", 1, 80, 220)
    c.output_pin("Step", 3, 700, 100)
    c.constant("ZERO8", 0, 8, 100, 320)
    instance(c, "PC8_74xx", 520, 180,
             [("ZERO8", 8), ("Clock", 1), ("ResetN", 1), ("Run", 1), ("LoadN", 1)], [("Step8", 8)])
    c.split_bus("Step8", 8, 580, 360, ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7"])
    c.join_bus("Step", 3, 680, 300, ["S0", "S1", "S2"])
    return c


def flags() -> Circuit:
    c = Circuit("Flags_74xx", "74HC74 + 74HC157")
    c.input_pin("ZeroIn", 1, 80, 100)
    c.input_pin("CarryIn", 1, 80, 140)
    c.input_pin("Clock", 1, 80, 180)
    c.input_pin("Load", 1, 80, 220)
    c.input_pin("ResetN", 1, 80, 260)
    c.output_pin("Zero", 1, 700, 100)
    c.output_pin("Carry", 1, 700, 140)
    c.constant("VCC", 1, 1, 100, 360)
    c.constant("GND", 0, 1, 100, 390)
    DIP.chip(c, "DIP_74157", 310, 400,
             {"S0": "Load", "OE": "GND", "A1": "Zero", "B1": "ZeroIn", "Y1": "ZeroNext",
              "A2": "Carry", "B2": "CarryIn", "Y2": "CarryNext"})
    instance(c, "IC_7474_FIXED", 630, 220,
             [("ZeroNext", 1), ("Clock", 1), ("VCC", 1), ("ResetN", 1),
              ("CarryNext", 1), ("Clock", 1), ("VCC", 1), ("ResetN", 1)],
             [("Zero", 1), ("ZeroN", 1), ("Carry", 1), ("CarryN", 1)])
    return c


def halt_latch() -> Circuit:
    c = Circuit("HaltLatch_74xx", "74HC74 + 74HC32")
    c.input_pin("Clock", 1, 80, 100)
    c.input_pin("SetHalt", 1, 80, 140)
    c.input_pin("ResetN", 1, 80, 180)
    c.output_pin("Halt", 1, 650, 100)
    c.output_pin("Run", 1, 650, 140)
    c.constant("VCC", 1, 1, 100, 300)
    c.constant("GND", 0, 1, 100, 330)
    DIP.chip(c, "DIP_7432", 290, 360, {"A1": "Halt", "B1": "SetHalt", "Y1": "HaltNext"})
    instance(c, "IC_7474_FIXED", 610, 180,
             [("HaltNext", 1), ("Clock", 1), ("VCC", 1), ("ResetN", 1),
              ("GND", 1), ("GND", 1), ("VCC", 1), ("ResetN", 1)],
             [("Halt", 1), ("Run", 1), ("UnusedQ", 1), ("UnusedQN", 1)])
    return c


def alu8() -> Circuit:
    c = Circuit("ALU8_74xx", "74xx ALU")
    c.input_pin("A", 8, 80, 100)
    c.input_pin("B", 8, 80, 140)
    c.input_pin("Sel", 2, 80, 180)
    c.input_pin("Sub", 1, 80, 220)
    c.output_pin("Q", 8, 2100, 100)
    c.output_pin("Carry", 1, 2100, 140)
    c.output_pin("Zero", 1, 2100, 180)
    c.constant("GND", 0, 1, 100, 320)
    c.split_bus("A", 8, 170, 220, [f"A{i}" for i in range(8)])
    c.split_bus("B", 8, 170, 340, [f"B{i}" for i in range(8)])
    c.split_bus("Sel", 2, 170, 420, ["SEL0", "SEL1"])
    chip4(c, "DIP_7486", 350, 170, [f"B{i}" for i in range(4)], ["Sub"] * 4, [f"BX{i}" for i in range(4)])
    chip4(c, "DIP_7486", 350, 290, [f"B{i}" for i in range(4, 8)], ["Sub"] * 4, [f"BX{i}" for i in range(4, 8)])
    # Correct eight-bit ripple adder/subtractor built only from 7486/7408/7432.
    # (The bundled historical 74283 model has a faulty carry equation.)
    chip4(c, "DIP_7486", 500, 170, [f"A{i}" for i in range(4)], [f"BX{i}" for i in range(4)], [f"P{i}" for i in range(4)])
    chip4(c, "DIP_7486", 500, 290, [f"A{i}" for i in range(4, 8)], [f"BX{i}" for i in range(4, 8)], [f"P{i}" for i in range(4, 8)])
    carry_in = ["Sub"] + [f"C{i}" for i in range(1, 8)]
    chip4(c, "DIP_7486", 650, 170, [f"P{i}" for i in range(4)], carry_in[:4], [f"ADD{i}" for i in range(4)])
    chip4(c, "DIP_7486", 650, 290, [f"P{i}" for i in range(4, 8)], carry_in[4:], [f"ADD{i}" for i in range(4, 8)])
    chip4(c, "DIP_7408", 500, 430, [f"A{i}" for i in range(4)], [f"BX{i}" for i in range(4)], [f"G{i}" for i in range(4)])
    chip4(c, "DIP_7408", 500, 550, [f"A{i}" for i in range(4, 8)], [f"BX{i}" for i in range(4, 8)], [f"G{i}" for i in range(4, 8)])
    chip4(c, "DIP_7408", 650, 430, [f"P{i}" for i in range(4)], carry_in[:4], [f"H{i}" for i in range(4)])
    chip4(c, "DIP_7408", 650, 550, [f"P{i}" for i in range(4, 8)], carry_in[4:], [f"H{i}" for i in range(4, 8)])
    chip4(c, "DIP_7432", 800, 430, [f"G{i}" for i in range(4)], [f"H{i}" for i in range(4)], [f"C{i+1}" for i in range(4)])
    chip4(c, "DIP_7432", 800, 550, [f"G{i}" for i in range(4, 8)], [f"H{i}" for i in range(4, 8)], [f"C{i+1}" for i in range(4, 8)])
    c.tunnel("Carry", 1, 880, 650); c.tunnel("C8", 1, 880, 650)
    chip4(c, "DIP_7408", 950, 150, [f"A{i}" for i in range(4)], [f"B{i}" for i in range(4)], [f"AND{i}" for i in range(4)])
    chip4(c, "DIP_7408", 950, 270, [f"A{i}" for i in range(4, 8)], [f"B{i}" for i in range(4, 8)], [f"AND{i}" for i in range(4, 8)])
    chip4(c, "DIP_7432", 1100, 150, [f"A{i}" for i in range(4)], [f"B{i}" for i in range(4)], [f"OR{i}" for i in range(4)])
    chip4(c, "DIP_7432", 1100, 270, [f"A{i}" for i in range(4, 8)], [f"B{i}" for i in range(4, 8)], [f"OR{i}" for i in range(4, 8)])
    chip4(c, "DIP_7486", 1250, 150, [f"A{i}" for i in range(4)], [f"B{i}" for i in range(4)], [f"XOR{i}" for i in range(4)])
    chip4(c, "DIP_7486", 1250, 270, [f"A{i}" for i in range(4, 8)], [f"B{i}" for i in range(4, 8)], [f"XOR{i}" for i in range(4, 8)])

    def mux4(x: int, y: int, prefix_a: str, prefix_b: str, out: str, base: int, select: str) -> None:
        sig = {"S0": select, "OE": "GND"}
        for i in range(4):
            sig[f"A{i+1}"] = f"{prefix_a}{base+i}"
            sig[f"B{i+1}"] = f"{prefix_b}{base+i}"
            sig[f"Y{i+1}"] = f"{out}{base+i}"
        DIP.chip(c, "DIP_74157", x, y, sig)

    mux4(1400, 130, "ADD", "AND", "M0", 0, "SEL0")
    mux4(1400, 250, "ADD", "AND", "M0", 4, "SEL0")
    mux4(1540, 130, "OR", "XOR", "M1", 0, "SEL0")
    mux4(1540, 250, "OR", "XOR", "M1", 4, "SEL0")
    mux4(1680, 130, "M0", "M1", "Q", 0, "SEL1")
    mux4(1680, 250, "M0", "M1", "Q", 4, "SEL1")
    c.join_bus("Q", 8, 2020, 360, [f"Q{i}" for i in range(8)])
    # Zero detector: invert every result bit, then NAND all eight, then invert once more.
    inv1 = {**{f"A{i+1}": f"Q{i}" for i in range(6)}, **{f"Y{i+1}": f"NQ{i}" for i in range(6)}}
    DIP.chip(c, "DIP_7404", 1500, 500, inv1)
    inv2 = {"A1": "Q6", "Y1": "NQ6", "A2": "Q7", "Y2": "NQ7", "A3": "ZeroN", "Y3": "Zero"}
    DIP.chip(c, "DIP_7404", 1640, 500, inv2)
    nand = {chr(ord("A") + i): f"NQ{i}" for i in range(8)}
    nand["Y"] = "ZeroN"
    DIP.chip(c, "DIP_7430", 1780, 500, nand)
    c.text("ADD/SUB: каскад полных сумматоров 7486/7408/7432; AND/OR/XOR: 7408/7432/7486", 80, 720, 14)
    c.text("Выбор операции: 6×74157; детектор нуля: 2×7404 + 7430", 80, 745, 14)
    return c


CTRL_DEFAULT = sum(1 << bit for bit in (0, 4, 5, 7, 10, 11, 14))


def make_control() -> list[int]:
    words = [CTRL_DEFAULT] * 1024
    def word(**kw: int) -> int:
        v = CTRL_DEFAULT
        active_low = {"PGM_OEN": 0, "PC_LOADN": 4, "RAM_OEN": 5, "A_OEN": 7,
                      "OP_OEN": 10, "ALU_OEN": 11, "STEP_LOADN": 14}
        active_high = {"IR_LOAD": 1, "OP_LOAD": 2, "PC_INC": 3, "RAM_WE": 6,
                       "A_LOAD": 8, "B_LOAD": 9, "FLAGS_LOAD": 12, "OUT_LOAD": 13,
                       "HALT_SET": 15, "SEL0": 16, "SEL1": 17, "SUB": 18}
        for name, value in kw.items():
            bit = active_low.get(name, active_high.get(name))
            if value: v |= 1 << bit
            else: v &= ~(1 << bit)
        return v
    for carry in range(2):
        for zero in range(2):
            for op in range(16):
                base = (carry << 8) | (zero << 7) | (op << 3)
                words[base | 0] = word(PGM_OEN=0, IR_LOAD=1, PC_INC=1)
                words[base | 1] = word(PGM_OEN=0, OP_LOAD=1, PC_INC=1)
                final = {"STEP_LOADN": 0}
                if op == 0x0: words[base | 2] = word(**final)
                elif op == 0x1: words[base | 2] = word(OP_OEN=0, A_LOAD=1, **final)
                elif op == 0x2: words[base | 2] = word(RAM_OEN=0, A_LOAD=1, **final)
                elif op == 0x3: words[base | 2] = word(A_OEN=0, RAM_WE=1, **final)
                elif op in (0x4, 0x5, 0x6, 0x7, 0x8):
                    words[base | 2] = word(RAM_OEN=0, B_LOAD=1)
                    sel = {0x4: (0, 0, 0), 0x5: (0, 0, 1), 0x6: (1, 0, 0),
                           0x7: (0, 1, 0), 0x8: (1, 1, 0)}[op]
                    words[base | 3] = word(ALU_OEN=0, A_LOAD=1, FLAGS_LOAD=1,
                                           SEL0=sel[0], SEL1=sel[1], SUB=sel[2], **final)
                elif op == 0x9: words[base | 2] = word(PC_LOADN=0, **final)
                elif op == 0xA: words[base | 2] = word(PC_LOADN=0 if zero else 1, **final)
                elif op == 0xB: words[base | 2] = word(PC_LOADN=0 if carry else 1, **final)
                elif op == 0xC: words[base | 2] = word(A_OEN=0, OUT_LOAD=1, **final)
                elif op == 0xF: words[base | 2] = word(HALT_SET=1, **final)
                else: words[base | 2] = word(**final)
    for address in range(512, 1024):
        words[address] = CTRL_DEFAULT & ~(1 << 14)
    return words


CONTROL = make_control()


def control_store() -> Circuit:
    c = Circuit("ControlStore_28C64", "AT28C64 microcode")
    c.input_pin("Opcode", 4, 80, 100)
    c.input_pin("Step", 3, 80, 140)
    c.input_pin("Zero", 1, 80, 180)
    c.input_pin("Carry", 1, 80, 220)
    c.input_pin("Halt", 1, 80, 260)
    c.output_pin("Control", 20, 920, 100)
    c.split_bus("Step", 3, 170, 220, ["UA0", "UA1", "UA2"])
    c.split_bus("Opcode", 4, 170, 320, ["UA3", "UA4", "UA5", "UA6"])
    c.tunnel("UA7", 1, 250, 180); c.tunnel("Zero", 1, 250, 180)
    c.tunnel("UA8", 1, 250, 200); c.tunnel("Carry", 1, 250, 200)
    c.tunnel("UA9", 1, 250, 220); c.tunnel("Halt", 1, 250, 220)
    c.join_bus("UADDR", 10, 420, 240, [f"UA{i}" for i in range(10)])
    c.memory("ROM", 500, 260, rom_contents(CONTROL, 10, 20), addrWidth=10,
             dataWidth=20, appearance="classic", label="AT28C64_CONTROL")
    c.tunnel("UADDR", 9, 500, 270)
    c.tunnel("Control", 20, 740, 320)
    c.text("Адрес: HALT, C, Z, opcode[3:0], microstep[2:0]", 80, 560, 14)
    c.text("20 управляющих линий; содержимое ПЗУ формируется генератором", 80, 585, 14)
    return c


PROGRAM = [0] * 256
demo = [
    0x01, 0x05,       # LDI 5
    0x03, 0x20,       # STA [20]
    0x01, 0xFA,       # LDI 250
    0x04, 0x20,       # ADD [20] => 255, C=0
    0x04, 0x20,       # ADD [20] => 4, C=1
    0x0B, 0x0E,       # JC 0x0E
    0x01, 0x63,       # LDI 99 (must be skipped)
    0x09, 0x10,       # JMP 0x10
    0x01, 0x2A,       # 0x10: LDI 42
    0x05, 0x20,       # SUB [20] => 37
    0x08, 0x20,       # XOR [20] => 32
    0x07, 0x20,       # OR  [20] => 37
    0x06, 0x20,       # AND [20] => 5
    0x05, 0x20,       # SUB [20] => 0, Z=1
    0x0A, 0x20,       # JZ 0x20
    0x01, 0x63,       # LDI 99 (must be skipped)
    0x0C, 0x00,       # 0x22: OUT
    0x0F, 0x00,       # HLT
]
PROGRAM[:len(demo)] = demo


def program_rom() -> Circuit:
    c = Circuit("ProgramROM_28C16", "AT28C16 program")
    c.input_pin("Address", 8, 80, 100)
    c.output_pin("Data", 8, 760, 100)
    c.memory("ROM", 300, 220, rom_contents(PROGRAM, 8, 8), addrWidth=8, dataWidth=8,
             appearance="classic", label="AT28C16_PROGRAM")
    c.tunnel("Address", 8, 300, 230)
    c.tunnel("Data", 8, 540, 280)
    c.text("В ПЗУ уже записана демонстрационная программа", 80, 460, 14)
    return c


def data_ram() -> Circuit:
    c = Circuit("DataRAM_62256", "62256 SRAM")
    c.input_pin("Address", 8, 80, 100)
    c.input_pin("DataIn", 8, 80, 140)
    c.input_pin("Clock", 1, 80, 180)
    c.input_pin("WE", 1, 80, 220)
    c.output_pin("DataOut", 8, 780, 100)
    c.constant("VCC", 1, 1, 100, 340)
    c.comp("RAM", 300, 220, 4, addrWidth=8, appearance="classic", asyncread="true",
           byteenables="NobyteEnables", dataWidth=8, databus="bibus", enables="byte",
           label="62256_SRAM", trigger="rising")
    c.tunnel("Address", 8, 300, 230)
    c.tunnel("DataIn", 8, 300, 310)
    c.tunnel("WE", 1, 300, 270)
    c.tunnel("VCC", 1, 300, 280)
    c.tunnel("Clock", 1, 300, 290)
    c.tunnel("DataOut", 8, 540, 310)
    c.text("В симуляторе — RAM; на макете — SRAM 62256 (используются A0…A7)", 80, 500, 14)
    return c


def instance(c: Circuit, name: str, x: int, y: int,
             inputs: list[tuple[str, int]], outputs: list[tuple[str, int]]) -> None:
    c.comp(name, x, y)
    for i, (signal, width) in enumerate(inputs):
        c.tunnel(signal, width, x - 120, y + i * 20)
    for i, (signal, width) in enumerate(outputs):
        c.tunnel(signal, width, x, y + i * 20)


def core() -> Circuit:
    c = Circuit("CPU7400_Core", "8-bit 74xx CPU")
    c.input_pin("Clock", 1, 80, 100)
    c.input_pin("ResetN", 1, 80, 140)
    c.output_pin("Out", 8, 2500, 100)
    c.output_pin("Halt", 1, 2500, 140)
    c.output_pin("PC", 8, 2500, 180)
    c.output_pin("A", 8, 2500, 220)
    c.output_pin("Step", 3, 2500, 260)
    c.constant("VCC", 1, 1, 100, 220)
    # Halt/run control and a 74HC08 clock gate stop the whole data path cleanly.
    instance(c, "HaltLatch_74xx", 420, 180,
             [("Clock", 1), ("HALT_SET", 1), ("ResetN", 1)], [("Halt", 1), ("Run", 1)])
    # Sequencer and PC.
    instance(c, "StepCounter_74xx", 850, 180,
             [("Clock", 1), ("ResetN", 1), ("Run", 1), ("STEP_LOADN", 1)], [("Step", 3)])
    instance(c, "PC8_74xx", 850, 360,
             [("Operand", 8), ("Clock", 1), ("ResetN", 1), ("PC_INC", 1), ("PC_LOADN", 1)], [("PC", 8)])
    instance(c, "ProgramROM_28C16", 1080, 360, [("PC", 8)], [("ProgramData", 8)])
    # Instruction and operand registers.
    instance(c, "Register8_74xx", 1350, 260,
             [("BUS", 8), ("Clock", 1), ("IR_LOAD", 1), ("ResetN", 1)], [("IR", 8)])
    instance(c, "Register8_74xx", 1350, 420,
             [("BUS", 8), ("Clock", 1), ("OP_LOAD", 1), ("ResetN", 1)], [("Operand", 8)])
    c.split_bus("IR", 8, 1430, 580, [f"IR{i}" for i in range(8)])
    c.join_bus("Opcode", 4, 1580, 540, ["IR0", "IR1", "IR2", "IR3"])
    # Flags and microcode control store.
    instance(c, "ControlStore_28C64", 1840, 180,
             [("Opcode", 4), ("Step", 3), ("ZeroFlag", 1), ("CarryFlag", 1), ("Halt", 1)], [("Control", 20)])
    control_names = ["PGM_OEN", "IR_LOAD", "OP_LOAD", "PC_INC", "PC_LOADN", "RAM_OEN",
                     "RAM_WE", "A_OEN", "A_LOAD", "B_LOAD", "OP_OEN", "ALU_OEN",
                     "FLAGS_LOAD", "OUT_LOAD", "STEP_LOADN", "HALT_SET", "SEL0", "SEL1", "SUB", "CTRL19"]
    c.split_bus("Control", 20, 1940, 520, control_names)
    c.join_bus("ALU_SEL", 2, 2080, 520, ["SEL0", "SEL1"])
    # Bus drivers. Every source is a real 74HC244.
    instance(c, "Buffer8_74xx", 1220, 700, [("ProgramData", 8), ("PGM_OEN", 1)], [("BUS", 8)])
    instance(c, "Buffer8_74xx", 1450, 700, [("Operand", 8), ("OP_OEN", 1)], [("BUS", 8)])
    # A/B registers and ALU.
    instance(c, "Register8_74xx", 1250, 900,
             [("BUS", 8), ("Clock", 1), ("A_LOAD", 1), ("ResetN", 1)], [("A", 8)])
    instance(c, "Register8_74xx", 1250, 1060,
             [("BUS", 8), ("Clock", 1), ("B_LOAD", 1), ("ResetN", 1)], [("B", 8)])
    instance(c, "ALU8_74xx", 1570, 900,
             [("A", 8), ("B", 8), ("ALU_SEL", 2), ("SUB", 1)],
             [("ALU_Q", 8), ("ALU_C", 1), ("ALU_Z", 1)])
    instance(c, "Flags_74xx", 1840, 900,
             [("ALU_Z", 1), ("ALU_C", 1), ("Clock", 1), ("FLAGS_LOAD", 1), ("ResetN", 1)],
             [("ZeroFlag", 1), ("CarryFlag", 1)])
    instance(c, "Buffer8_74xx", 1780, 1120, [("ALU_Q", 8), ("ALU_OEN", 1)], [("BUS", 8)])
    instance(c, "Buffer8_74xx", 2050, 900, [("A", 8), ("A_OEN", 1)], [("BUS", 8)])
    # Data SRAM and its bus driver.
    instance(c, "DataRAM_62256", 1550, 1320,
             [("Operand", 8), ("BUS", 8), ("Clock", 1), ("RAM_WE", 1)], [("RAM_DATA", 8)])
    instance(c, "Buffer8_74xx", 1820, 1320, [("RAM_DATA", 8), ("RAM_OEN", 1)], [("BUS", 8)])
    # Output register and monitor bus.
    instance(c, "Register8_74xx", 2220, 1120,
             [("BUS", 8), ("Clock", 1), ("OUT_LOAD", 1), ("ResetN", 1)], [("Out", 8)])
    c.text("СИСТЕМНАЯ ШИНА D7…D0 — источники подключены только через 74HC244", 940, 650, 18)
    c.wire(980, 670, 2320, 670)
    c.text("УПРАВЛЕНИЕ", 1660, 100, 18)
    c.text("ТРАКТ ДАННЫХ", 1040, 820, 18)
    c.text("ПАМЯТЬ", 1320, 1250, 18)
    return c


def main_panel() -> Circuit:
    c = Circuit("ЭВМ_7400")
    c.text("ЭВМ НА РЕАЛЬНЫХ МИКРОСХЕМАХ СЕРИИ 74xx", 120, 70, 26)
    c.text("1) Нажмите RESET  2) Включите Simulate → Ticks Enabled", 120, 105, 16)
    c.comp("Clock", 160, 180, 0, label="MASTER_CLOCK", highDuration=1, lowDuration=1)
    c.tunnel("Clock", 1, 160, 180)
    c.comp("Button", 160, 240, 5, label="RESET")
    c.tunnel("ResetButton", 1, 160, 240)
    DIP.chip(c, "DIP_7404", 330, 220, {"A1": "ResetButton", "Y1": "ResetN"})
    instance(c, "CPU7400_Core", 760, 180, [("Clock", 1), ("ResetN", 1)],
             [("Out", 8), ("Halt", 1), ("PC", 8), ("A", 8), ("Step", 3)])
    c.comp("Hex Digit Display", 930, 180, 5)
    c.tunnel("Out", 4, 930, 180)
    c.comp("Probe", 980, 180, 0, label="OUT", radix="10unsigned")
    c.tunnel("Out", 8, 980, 180)
    c.comp("LED", 930, 230, 5, label="HALT", color="#ff3030")
    c.tunnel("Halt", 1, 930, 230)
    for label, width, y, radix in (("PC", 8, 290, "16"), ("A", 8, 330, "10unsigned"), ("Step", 3, 370, "10unsigned")):
        c.comp("Probe", 980, y, 0, label=label, radix=radix)
        c.tunnel(label, width, 980, y)
    c.text("Демонстрация проверяет: LDI, STA, ADD, JC, JMP, SUB, XOR, OR, AND, JZ, OUT, HLT", 120, 480, 15)
    c.text("Ожидаемый результат OUT = 0, потому что финальная ветка проверяет нулевой результат", 120, 510, 15)
    c.text("Откройте CPU7400_Core для архитектуры; ALU8_74xx/PC8_74xx — для разводки корпусов", 120, 540, 15)
    return c


def alu_vectors() -> str:
    rows = ["A[8] B[8] Sel[2] Sub Q[8] Carry Zero"]
    for a, b in [(0, 0), (1, 1), (0x55, 0x0F), (0xFA, 5), (0x80, 0x80), (0xFF, 1)]:
        for sel in range(4):
            subs = (0, 1) if sel == 0 else (0,)
            for sub in subs:
                if sel == 0:
                    total = a + ((~b) & 0xFF) + 1 if sub else a + b
                    q = total & 0xFF; carry = (total >> 8) & 1
                elif sel == 1: q = a & b; carry = (a + b) >> 8
                elif sel == 2: q = a | b; carry = (a + b) >> 8
                else: q = a ^ b; carry = (a + b) >> 8
                rows.append(f"0x{a:02x} 0x{b:02x} 0x{sel:x} {sub} 0x{q:02x} {carry & 1} {int(q == 0)}")
    return "\n".join(rows) + "\n"


def control_vectors() -> str:
    rows = ["Opcode[4] Step[3] Zero Carry Halt Control[20]"]
    for halt in range(2):
        for carry in range(2):
            for zero in range(2):
                for op in range(16):
                    for step in range(8):
                        addr = (halt << 9) | (carry << 8) | (zero << 7) | (op << 3) | step
                        rows.append(f"0x{op:x} 0x{step:x} {zero} {carry} {halt} 0x{CONTROL[addr]:05x}")
    return "\n".join(rows) + "\n"


def register_vectors() -> str:
    return """<set> <seq> D[8] Clock Load ResetN Q[8]
1 1 0x00 0 0 0 0x00
1 2 0x00 1 0 0 0x00
1 3 0x00 0 0 1 0x00
1 4 0xa5 1 0 1 0x00
1 5 0xa5 0 1 1 0x00
1 6 0xa5 1 1 1 0xa5
1 7 0x3c 0 1 1 0xa5
1 8 0x3c 1 1 1 0x3c
1 9 0x00 0 0 0 0x00
"""


def pc_vectors() -> str:
    rows = ["<set> <seq> D[8] Clock ResetN Inc LoadN Q[8]",
            "1 1 0x00 0 0 0 1 0x00", "1 2 0x00 1 0 0 1 0x00", "1 3 0x00 0 1 0 1 0x00",
            "1 4 0x00 0 1 1 1 0x00"]
    seq = 5; q = 0
    for _ in range(20):
        q = (q + 1) & 0xFF
        rows.append(f"1 {seq} 0x00 1 1 1 1 <DC>"); seq += 1
        rows.append(f"1 {seq} 0x00 1 1 1 1 <DC>"); seq += 1
        rows.append(f"1 {seq} 0x00 1 1 1 1 0x{q:02x}"); seq += 1
        rows.append(f"1 {seq} 0x00 0 1 1 1 0x{q:02x}"); seq += 1
    q = 0xA5
    rows.append(f"1 {seq} 0xa5 0 1 0 0 0x14"); seq += 1
    rows.append(f"1 {seq} 0xa5 1 1 0 0 <DC>"); seq += 1
    rows.append(f"1 {seq} 0xa5 1 1 0 0 <DC>"); seq += 1
    rows.append(f"1 {seq} 0xa5 1 1 0 0 0x{q:02x}"); seq += 1
    rows.append(f"1 {seq} 0xa5 0 1 0 0 0x{q:02x}")
    return "\n".join(rows) + "\n"


class Model:
    def __init__(self):
        self.pc = self.a = self.b = self.ir = self.op = self.out = 0
        self.step = self.z = self.c = self.halt = 0
        self.ram = [0] * 256

    def control(self) -> int:
        addr = (self.c << 8) | (self.z << 7) | ((self.ir & 0xF) << 3) | self.step
        return CONTROL[addr]

    def alu(self, ctrl: int) -> tuple[int, int, int]:
        sel = ((ctrl >> 16) & 1) | (((ctrl >> 17) & 1) << 1)
        sub = (ctrl >> 18) & 1
        if sel == 0:
            total = self.a + (((~self.b) & 0xFF) if sub else self.b) + sub
            q, carry = total & 0xFF, (total >> 8) & 1
        elif sel == 1: q, carry = self.a & self.b, (self.a + self.b) >> 8
        elif sel == 2: q, carry = self.a | self.b, (self.a + self.b) >> 8
        else: q, carry = self.a ^ self.b, (self.a + self.b) >> 8
        return q, carry & 1, int(q == 0)

    def edge(self, reset_n: int) -> None:
        if not reset_n:
            self.pc = self.a = self.b = self.ir = self.op = self.out = 0
            self.step = self.z = self.c = self.halt = 0
            return
        ctrl = self.control()
        if self.halt:
            return
        sources = []
        if not (ctrl >> 0) & 1: sources.append(PROGRAM[self.pc])
        if not (ctrl >> 5) & 1: sources.append(self.ram[self.op])
        if not (ctrl >> 7) & 1: sources.append(self.a)
        if not (ctrl >> 10) & 1: sources.append(self.op)
        alu_q, alu_c, alu_z = self.alu(ctrl)
        if not (ctrl >> 11) & 1: sources.append(alu_q)
        bus = sources[0] if sources else 0
        old_op = self.op
        if (ctrl >> 1) & 1: self.ir = bus
        if (ctrl >> 2) & 1: self.op = bus
        if (ctrl >> 8) & 1: self.a = bus
        if (ctrl >> 9) & 1: self.b = bus
        if (ctrl >> 13) & 1: self.out = bus
        if (ctrl >> 6) & 1: self.ram[old_op] = bus
        if (ctrl >> 12) & 1: self.z, self.c = alu_z, alu_c
        if not (ctrl >> 4) & 1: self.pc = old_op
        elif (ctrl >> 3) & 1: self.pc = (self.pc + 1) & 0xFF
        if not (ctrl >> 14) & 1: self.step = 0
        else: self.step = (self.step + 1) & 0xF
        if (ctrl >> 15) & 1: self.halt = 1


def cpu_vectors() -> str:
    rows = ["<set> <seq> Clock ResetN Out[8] Halt PC[8] A[8] Step[3]"]
    m = Model(); seq = 1
    rows.append(f"1 {seq} 0 0 0x00 0 0x00 0x00 0x0"); seq += 1
    m.edge(0)
    rows.append(f"1 {seq} 1 0 0x00 0 0x00 0x00 0x0"); seq += 1
    rows.append(f"1 {seq} 0 1 0x00 0 0x00 0x00 0x0"); seq += 1
    for _ in range(200):
        m.edge(1)
        rows.append(f"1 {seq} 1 1 0x{m.out:02x} {m.halt} 0x{m.pc:02x} 0x{m.a:02x} 0x{m.step:x}"); seq += 1
        rows.append(f"1 {seq} 0 1 0x{m.out:02x} {m.halt} 0x{m.pc:02x} 0x{m.a:02x} 0x{m.step:x}"); seq += 1
        if m.halt:
            break
    return "\n".join(rows) + "\n"


def embedded_chips() -> str:
    names = ["D_Flip_Flop", "DIP_7404", "DIP_7408", "DIP_7430", "DIP_7432",
             "DIP_7486", "DIP_74157", "DIP_74244"]
    source = LIBRARY.read_text(encoding="utf-8")
    blocks = []
    for name in names:
        match = re.search(rf'  <circuit name="{re.escape(name)}">.*?  </circuit>', source, re.S)
        if not match:
            raise RuntimeError(f"missing {name}")
        blocks.append(match.group(0))
    ic_source = IC_LIBRARY.read_text(encoding="utf-8")
    return "\n".join(blocks)


def main() -> int:
    circuits = [fixed_7474(), register8(), buffer8(), and1(), ff_test(), pc8(), step_counter(), flags(), halt_latch(), alu8(),
                control_store(), program_rom(), data_ram(), core(), main_panel()]
    project = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<project source="4.1.0" version="1.0">
This file is intended to be loaded by Logisim or Logisim Evolution.
  <lib desc="#Wiring" name="0"/><lib desc="#Gates" name="1"/><lib desc="#Plexers" name="2"/><lib desc="#Arithmetic" name="3"/><lib desc="#Memory" name="4"/><lib desc="#I/O" name="5"/><lib desc="#Base" name="6"/>
  <main name="ЭВМ_7400"/>
  <options><a name="gateUndefined" val="ignore"/><a name="simlimit" val="10000"/><a name="simrand" val="0"/></options>
""" + embedded_chips() + "\n" + "\n".join(c.serialize() for c in circuits) + "\n</project>\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(project, encoding="utf-8")
    TESTS.mkdir(parents=True, exist_ok=True)
    (TESTS / "alu.txt").write_text(alu_vectors(), encoding="ascii")
    (TESTS / "control.txt").write_text(control_vectors(), encoding="ascii")
    (TESTS / "register.txt").write_text(register_vectors(), encoding="ascii")
    (TESTS / "pc.txt").write_text(pc_vectors(), encoding="ascii")
    (TESTS / "cpu.txt").write_text(cpu_vectors(), encoding="ascii")
    print(f"generated {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
