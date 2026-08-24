from pathlib import Path
import unittest

from mt16.core import MICROCODE, Machine, Opcode, assemble


ROOT = Path(__file__).resolve().parents[1]


class AssemblerTests(unittest.TestCase):
    def test_labels_resolve_to_byte_addresses(self) -> None:
        image = assemble(""".thread 0\nstart: NOP\nJMP start\n.thread 1\nHALT\n.thread 2\nHALT\n.thread 3\nHALT\n""")
        self.assertEqual(image.programs[0][:4], [Opcode.NOP, 0, Opcode.JMP, 0])

    def test_all_opcodes_have_unique_control_words(self) -> None:
        self.assertEqual([word.opcode for word in MICROCODE], list(Opcode))
        self.assertEqual(len({word.encode() for word in MICROCODE}), 16)

    def test_rejects_bad_program(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown instruction"):
            assemble("WAT 1")


class MachineTests(unittest.TestCase):
    def test_demo_program_runs_end_to_end(self) -> None:
        source = (ROOT / "programs" / "demo.mt16").read_text(encoding="utf-8")
        machine = Machine(assemble(source)).run()
        self.assertEqual(machine.memory[0xF0:0xF4], [55, 0xFA, 24, 42])
        self.assertEqual(machine.memory[0x30], 4)
        self.assertTrue(all(context.halted for context in machine.contexts))
        self.assertGreater(len(machine.trace), 40)

    def test_scheduler_is_microstep_interleaved(self) -> None:
        source = "\n".join(f".thread {tid}\nLDI {tid + 1}\nHALT" for tid in range(4))
        machine = Machine(assemble(source))
        for _ in range(8):
            machine.tick()
        self.assertEqual([c.microstep for c in machine.contexts], [2, 2, 2, 2])
        for _ in range(4):
            machine.tick()
        self.assertEqual([c.acc for c in machine.contexts], [1, 2, 3, 4])

    def test_atomic_add_is_lossless_across_four_threads(self) -> None:
        blocks = [".data 0x80 0"]
        for tid in range(4):
            blocks.append(f".thread {tid}\nLDI 1")
            blocks.extend(["ATOMADD 0x80", "LDI 1"] * 25)
            blocks.append("HALT")
        machine = Machine(assemble("\n".join(blocks))).run()
        self.assertEqual(machine.memory[0x80], 100)

    def test_wraparound_and_zero_branch(self) -> None:
        source = """
        .data 0x01 1
        .thread 0
        LDI 0
        SUB 0x01
        ADD 0x01
        JZ ok
        LDI 99
        ok: ST 0xf0
        HALT
        .thread 1
        HALT
        .thread 2
        HALT
        .thread 3
        HALT
        """
        machine = Machine(assemble(source)).run()
        self.assertEqual(machine.memory[0xF0], 0)


if __name__ == "__main__":
    unittest.main()
