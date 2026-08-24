#!/usr/bin/env python3
"""Build and run MT16 programs without external dependencies."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mt16.core import MICROCODE, Machine, assemble, hex_image  # noqa: E402


def build(source: Path, output: Path) -> None:
    image = assemble(source.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    for tid, program in enumerate(image.programs):
        (output / f"thread{tid}.hex").write_text(hex_image(program, 8), encoding="ascii")
    (output / "data.hex").write_text(hex_image(image.data, 16), encoding="ascii")
    control = [0] * 256
    for word in MICROCODE:
        control[int(word.opcode)] = word.encode()
    (output / "microcode.hex").write_text(hex_image(control, 32), encoding="ascii")


def run(source: Path, trace: bool) -> None:
    machine = Machine(assemble(source.read_text(encoding="utf-8"))).run()
    if trace:
        for event in machine.trace:
            print(f"{event.tick:06d} T{event.thread} {event.opcode:7s} PC={event.pc:02x} ACC={event.acc:04x}")
    print(f"halted after {machine.ticks} hardware ticks")
    print("retired:", ", ".join(f"T{i}={count}" for i, count in enumerate(machine.retired_by_thread())))
    print("ports:", " ".join(f"F{i:x}={machine.memory[0xF0+i]:04x}" for i in range(4)))
    print(f"atomic counter [30]={machine.memory[0x30]:04x}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_build = sub.add_parser("build", help="assemble ROM/RAM images")
    p_build.add_argument("source", type=Path)
    p_build.add_argument("--output", type=Path, default=ROOT / "build")
    p_run = sub.add_parser("run", help="run the cycle-accurate reference model")
    p_run.add_argument("source", type=Path)
    p_run.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    if args.command == "build":
        build(args.source, args.output)
    else:
        run(args.source, args.trace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
