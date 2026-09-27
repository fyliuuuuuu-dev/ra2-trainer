"""One-session live probe; requires addresses from the current skirmish.

Do not reuse saved addresses in a later game. The controller chooses its own
eligible destination; the building argument is only the expected test site.
"""
import sys
import time
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer import units
from trainer.auto_enter import AutoEnterController
from trainer.mem import Process
from trainer.operations import GameOperations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("soldier", type=lambda s: int(s, 0))
    parser.add_argument("building", type=lambda s: int(s, 0))
    args = parser.parse_args()
    p = Process(21632)
    ops = GameOperations(p)
    c = AutoEnterController(p, ops)
    soldier, building = args.soldier, args.building
    before = p.read_i32(building + 0x564)
    try:
        if not units.valid_techno(p, soldier, 0x7A3540, units.player_house(p)):
            raise RuntimeError("test infantry is no longer valid")
        if p.read_i32(soldier + 0x98) != 5 or p.read_u8(soldier + 0x76) != 0:
            raise RuntimeError("test infantry is no longer idle on map")
        fn = p.read_u32(0x7A3540 + 0x140)
        if fn != 0x6C91C0:
            raise RuntimeError("native selection method changed")
        selected = ops.executor.call(fn, this=soldier)
        print("native_select_result", selected, "selected_flag", p.read_u8(soldier + 0x77),
              "native_selected_count", p.read_i32(0xA40C70), flush=True)
        if p.read_u8(soldier + 0x77) != 1:
            raise RuntimeError("native select did not select infantry")
        key = soldier, p.read_u32(soldier + 0x10)
        issued = c.execute(c.snapshot_selected())
        actual_target = c.issued.get(key, (building, 0, 0))[0]
        before = p.read_i32(actual_target + 0x564)
        print("issued", issued, "mission", p.read_i32(soldier + 0x98),
              "queued", p.read_i32(soldier + 0xA0), "target", c.issued.get(key),
              "occupants_before", before, flush=True)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            occupants = p.read_i32(actual_target + 0x564)
            limbo = p.read_u8(soldier + 0x76)
            if occupants is not None and occupants > before and limbo == 1:
                print("entered", occupants, "limbo", limbo,
                      "mission", p.read_i32(soldier + 0x98), flush=True)
                break
            time.sleep(0.2)
        else:
            print("not_entered", p.read_i32(actual_target + 0x564),
                  p.read_u8(soldier + 0x76), p.read_i32(soldier + 0x98), flush=True)
    finally:
        c.close()
        if p.read_u32(soldier) == 0x7A3540 and p.read_u8(soldier + 0x77) == 1:
            unselect = p.read_u32(0x7A3540 + 0x144)
            ops.executor.call(unselect, this=soldier)
        ops.close()
        p.close()


if __name__ == "__main__":
    main()
