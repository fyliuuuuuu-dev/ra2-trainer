"""Exercise blocked-cell fallback with two real RA2 1.006 player units.

Adds one tank and one infantry unit near a player power plant. Run only in a
live skirmish: python tools/clone_live_test.py --run
"""
import argparse
import struct
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer import units
from trainer.mem import Process
from trainer.operations import GameOperations
from trainer.patches import PatchManager


def xyz_of(proc, obj):
    raw = proc.read(obj + 0x88, 12)
    return struct.unpack("<iii", raw) if raw else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="create two real units")
    args = parser.parse_args()
    if not args.run:
        parser.error("pass --run to add the two test units")
    proc = Process("game.exe")
    operation = GameOperations(proc)
    try:
        if not PatchManager(proc).compatible():
            raise RuntimeError("game.exe is not the verified RA2 1.006 build")
        player = units.player_house(proc)
        source = {}
        building = None
        for obj, vt in units.player_technos(proc):
            typ = units.type_of(proc, obj, vt)
            name = proc.read_cstr(typ + 0x24, 32) if typ else None
            if name in ("SREF", "E1") and name not in source and units.valid_techno(proc, obj, vt, player):
                source[name] = (obj, vt)
            if name == "GAPOWR" and building is None:
                building = (obj, vt)
        if len(source) != 2 or building is None:
            raise RuntimeError("test requires player SREF, E1 and GAPOWR")
        target = xyz_of(proc, building[0])
        if target is None:
            raise RuntimeError("building has no position")
        chosen = [source["SREF"], source["E1"]]
        created = []
        actual_spawn = operation.spawn_clone_at

        def recording_spawn(typ, house, xyz):
            new = actual_spawn(typ, house, xyz)
            if new:
                created.append((new, typ, xyz))
            return new

        operation.world_at_screen = lambda _screen: target
        operation.spawn_clone_at = recording_spawn
        with patch.object(units, "selected_technos", return_value=chosen):
            done, total = operation.clone_selected((0, 0, 1, 1))
        time.sleep(0.3)
        placements = []
        for obj, typ, request in created:
            final = xyz_of(proc, obj)
            placements.append((obj, typ, request, final,
                               proc.read_u32(obj), proc.read_i32(obj + 0x6C)))
        print("building", hex(building[0]), "cell", tuple(v >> 8 for v in target[:2]))
        print("result", done, total)
        for obj, typ, request, final, vt, hp in placements:
            print("clone", hex(obj), "typ", hex(typ), "request", request,
                  "final", final, "cell", tuple(v >> 8 for v in final[:2]),
                  "vtable", hex(vt or 0), "hp", hp)
        final_cells = {tuple(v >> 8 for v in item[3][:2]) for item in placements}
        assert done == total == 2 and len(placements) == len(final_cells) == 2
        assert tuple(v >> 8 for v in target[:2]) not in final_cells
        assert all(item[4] in (0x7ADDF8, 0x7A3540) and item[5] > 0
                   for item in placements)
    finally:
        operation.close()
        proc.close()


if __name__ == "__main__":
    main()
