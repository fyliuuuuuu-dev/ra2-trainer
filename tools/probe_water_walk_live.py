"""One-session native movement probe. Requires exclusive game-writer access.

PID and Type pointers are validated before use and belong to the current
skirmish only. Spawned active test units are left intact because this project
does not have a verified active-object deletion operation.
"""
import argparse
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer import units
from trainer.mem import Process
from trainer.operations import GameOperations, X86
from trainer.water_walk import WaterWalkController


def coords(p, obj):
    raw = p.read(obj + 0x88, 12)
    return struct.unpack("<iii", raw) if raw else None


def cell(p, ops, x, y):
    buf = p.alloc(16)
    try:
        p.write(buf, struct.pack("<hh", x, y))
        result = ops.executor.call(0x548070, this=0x8324E0, args=(buf,))
        if result in (0, 0xA6F9F8):
            raise RuntimeError(f"invalid cell {x},{y}")
        return result
    finally:
        p.free(buf)


def issue_move(ops, obj, target_cell):
    a = X86()
    a.emit("6a 00")
    a.imm("68", target_cell)
    a.emit("6a 00 6a 02")
    a.imm("b9", obj)
    a.emit("8b 01 ff 90 20 03 00 00 c3")
    return ops.run(a.finish())


def observe(p, obj, seconds=8):
    series = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        xyz = coords(p, obj)
        if not xyz:
            raise RuntimeError("test object disappeared")
        frame = p.read_u32(0xA40D2C)
        point = (frame, xyz[0] >> 8, xyz[1] >> 8, p.read_i32(obj + 0x98))
        if not series or point[1:] != series[-1][1:]:
            series.append(point)
        time.sleep(0.2)
    print("movement", series, flush=True)
    return series[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--unit", choices=("E1", "MTNK"), default="E1")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Pass --execute only after the old GUI has exited.")
    p = Process(21632)
    ops = GameOperations(p)
    ctl = WaterWalkController(p)
    obj = 0
    try:
        typ = {"E1": 0x123DF590, "MTNK": 0x1252A9B8}[args.unit]
        if p.read_cstr(typ + 0x24, 24) != args.unit:
            raise RuntimeError("Type pointer no longer names the expected unit")
        if ctl.enabled:
            raise RuntimeError("water-walk is still ON before this isolated probe")
        terrain = []
        for x in (68, 69, 70, 71, 72, 73):
            c = cell(p, ops, x, 83)
            land = p.read_i32(c + 0xEC)
            occupation = p.read_u32(c + 0x124) & 0xFF
            terrain.append((x, land, occupation))
        print("shore", terrain, flush=True)
        start_x = 72 if args.unit == "E1" else 73
        if [v[1] for v in terrain] != [2, 2, 6, 7, 7, 7] or any(
                v[2] for v in terrain if v[0] != 72 or start_x == 72):
            raise RuntimeError("shoreline no longer meets test conditions")
        house = units.player_house(p)
        obj = ops.spawn_clone_at(typ, house, (start_x * 256 + 128, 83 * 256 + 128, 832))
        if not obj:
            raise RuntimeError("safe test spawn failed")
        print("created", args.unit, hex(obj), "uid", p.read_u32(obj + 0x10),
              "coords", coords(p, obj), flush=True)
        water = cell(p, ops, 68, 83)
        land = cell(p, ops, start_x, 83)
        print("native_move", issue_move(ops, obj, water), flush=True)
        observe(p, obj, 6)
        ctl.enable()
        print("water_mode", p.read(ctl.base + 0x20, 1), flush=True)
        print("enabled_move", issue_move(ops, obj, water), flush=True)
        in_water = observe(p, obj, 12)
        ctl.disable()
        print("drain_mode", p.read(ctl.base + 0x20, 1), flush=True)
        if in_water[1] <= 69:
            print("return_move", issue_move(ops, obj, land), flush=True)
            observe(p, obj, 12)
    finally:
        ctl.disable()
        ops.close()
        p.close()
        if obj:
            print("dedicated_test_unit_retained", hex(obj), flush=True)


if __name__ == "__main__":
    main()
