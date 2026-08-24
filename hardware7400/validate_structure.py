#!/usr/bin/env python3
"""Structural checks for the generated 74xx computer."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "ЭВМ-7400.circ"

REQUIRED = {
    "ЭВМ_7400", "CPU7400_Core", "ALU8_74xx", "Register8_74xx", "Buffer8_74xx",
    "PC8_74xx", "StepCounter_74xx", "Flags_74xx", "HaltLatch_74xx",
    "ControlStore_28C64", "ProgramROM_28C16", "DataRAM_62256",
}

TERMINALS = {
    "IC_7474_FIXED": "74HC74",
    "DIP_7404": "74HC04",
    "DIP_7408": "74HC08",
    "DIP_7430": "74HC30",
    "DIP_7432": "74HC32",
    "DIP_7486": "74HC86",
    "DIP_74157": "74HC157",
    "DIP_74244": "74HC244",
    "ProgramROM_28C16": "AT28C16",
    "ControlStore_28C64": "AT28C64",
    "DataRAM_62256": "62256 SRAM",
}


def main() -> int:
    root = ET.parse(PROJECT).getroot()
    circuits = {c.get("name"): c for c in root.findall("circuit")}
    missing = REQUIRED - circuits.keys()
    if missing:
        raise SystemExit(f"missing circuits: {sorted(missing)}")

    # No ideal Logisim gates, arithmetic blocks, muxes, counters or registers are
    # allowed in the hardware design. Such primitives may only exist inside the
    # embedded, corrected models of physical ICs and the three memory devices.
    design = REQUIRED - {"ControlStore_28C64", "ProgramROM_28C16", "DataRAM_62256"}
    forbidden: list[str] = []
    for name in design:
        for comp in circuits[name].findall("comp"):
            lib = comp.get("lib")
            component = comp.get("name", "")
            if lib in {"1", "2", "3"}:
                forbidden.append(f"{name}: lib {lib} {component}")
            if lib == "4" and component in {"Register", "Counter", "D Flip-Flop"}:
                forbidden.append(f"{name}: ideal state component {component}")
    if forbidden:
        raise SystemExit("forbidden ideal blocks:\n" + "\n".join(forbidden))

    if any(comp.get("name") in {"DIP_74283", "IC_74283"}
           for c in design for comp in circuits[c].findall("comp")):
        raise SystemExit("historical 74283 model must not be used: its carry equation is wrong")

    def expand(name: str) -> Counter[str]:
        if name in TERMINALS:
            return Counter({TERMINALS[name]: 1})
        total: Counter[str] = Counter()
        for comp in circuits[name].findall("comp"):
            child = comp.get("name", "")
            if child in TERMINALS or child in circuits and child not in {"D_Flip_Flop"}:
                total += expand(child)
        return total

    bom = expand("CPU7400_Core")
    expected = Counter({
        "74HC04": 2, "74HC08": 10, "74HC30": 1, "74HC32": 5, "74HC74": 30,
        "74HC86": 12, "74HC157": 21, "74HC244": 5,
        "AT28C16": 1, "AT28C64": 1, "62256 SRAM": 1,
    })
    if bom != expected:
        raise SystemExit(f"BOM changed unexpectedly: {bom}")
    print(f"PASS structure: {len(circuits)} circuits, {sum(bom.values())} physical ICs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
