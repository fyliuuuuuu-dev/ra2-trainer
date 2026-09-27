"""One-session test for the dedicated MTNK created in the earlier AA test.

Run only with the trainer GUI closed and this exact test unit validated.  The
script restores the unit's original health/veterancy and all hooks in finally.
"""
import struct
import time

from trainer.mem import Process
from trainer.operations import GameOperations, X86
from trainer.tank_repair import TankRepairController, AI_ENTRY, AI_ORIGINAL, FRAME, UNIT_VT
from trainer.addresses import PLAYER_PTR


PID = 21632
TEST_UNIT = 0x155A4FC0
TEST_ID = 1077668


def set_test_state(operations, hp, veterancy):
    a = X86()
    a.imm("b9", TEST_UNIT)
    a.imm("81 39", UNIT_VT)
    a.jump("0f 85", "fail")
    a.imm("81 79 10", TEST_ID)
    a.jump("0f 85", "fail")
    a.imm("a1", PLAYER_PTR)
    a.emit("39 81 b4 01 00 00")
    a.jump("0f 85", "fail")
    a.emit("80 79 76 00")
    a.jump("0f 85", "fail")
    a.emit("80 79 7d 01")
    a.jump("0f 85", "fail")
    a.emit("c7 81 1c 01 00 00")
    a.code += struct.pack("<f", veterancy)
    a.emit("c7 41 6c")
    a.code += struct.pack("<I", hp)
    a.emit("c7 41 70")
    a.code += struct.pack("<I", hp)
    a.emit("b8 01 00 00 00 c3")
    a.label("fail")
    a.emit("31 c0 c3")
    if operations.run(a.finish()) != 1:
        raise RuntimeError("测试坦克身份已改变，拒绝写入")


def sample(proc, duration=4.0, stop_changes=None):
    transitions = []
    first = None
    end = time.monotonic() + duration
    while time.monotonic() < end:
        before = proc.read_u32(FRAME)
        hp = proc.read_i32(TEST_UNIT + 0x6C)
        after = proc.read_u32(FRAME)
        if before == after and before is not None and hp is not None:
            current = (before, hp)
            if first is None:
                first = current
            if not transitions or hp != transitions[-1][1]:
                transitions.append(current)
                print("frame,health", *current, flush=True)
                if stop_changes and len(transitions) >= stop_changes:
                    break
        time.sleep(0.002)
    return first, transitions


def main():
    proc = Process(PID)
    operations = GameOperations(proc)
    controller = TankRepairController(proc)
    restored = False
    prepared = False
    try:
        if proc.read(AI_ENTRY, len(AI_ORIGINAL)) != AI_ORIGINAL:
            raise RuntimeError("原版Unit.AI入口不匹配；不能独占测试")
        typ = proc.read_u32(TEST_UNIT + 0x5AC)
        owner = proc.read_u32(TEST_UNIT + 0x1B4)
        if (proc.read_u32(TEST_UNIT) != UNIT_VT or
            proc.read_u32(TEST_UNIT + 0x10) != TEST_ID or
            owner != proc.read_u32(PLAYER_PTR) or not typ or
            proc.read(typ + 0x24, 5) != b"MTNK\x00" or
            proc.read_i32(TEST_UNIT + 0x6C) != 300 or
            proc.read_f32(TEST_UNIT + 0x11C) != 2.0):
            raise RuntimeError("独立测试坦克身份/原始状态不符；拒绝测试")
        original_hp, original_vet = 300, 2.0
        print("baseline", "frame", proc.read_u32(FRAME), "hp", original_hp,
              "vet", original_vet, "id", TEST_ID, flush=True)
        set_test_state(operations, 180, 0.0)
        prepared = True
        controller.enable()
        first, transitions = sample(proc, stop_changes=5)
        print("on_transitions", transitions, flush=True)
        controller.disable()
        off_start, off_values = sample(proc, duration=0.8)
        print("off_start", off_start, "off_transitions", off_values, flush=True)
        controller.enable()
        restart_start, restart_values = sample(proc, duration=0.6, stop_changes=3)
        print("restart_start", restart_start, "restart_transitions", restart_values, flush=True)
    finally:
        try:
            controller.disable()
        finally:
            try:
                if (prepared and proc.read_u32(TEST_UNIT) == UNIT_VT and
                        proc.read_u32(TEST_UNIT + 0x10) == TEST_ID):
                    set_test_state(operations, 300, 2.0)
                    restored = True
            finally:
                operations.close()
                print("cleanup", "tank_restored", restored,
                      "entry", (proc.read(AI_ENTRY, len(AI_ORIGINAL)) or b"").hex(), flush=True)
                proc.close()


if __name__ == "__main__":
    main()
