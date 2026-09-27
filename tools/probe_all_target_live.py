"""One-session live probe using isolated units and native RA2 orders.

PID and type addresses below belong to the current skirmish; do not reuse in
another game without validating them again.
"""
import struct
import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer import units
from trainer.all_target import AllTargetController
from trainer.mem import Process
from trainer.operations import GameOperations, X86


def issue(ops, actor, mission, target=0, destination=0):
    a = X86()
    a.emit("6a 00")
    a.imm("68", destination)
    a.imm("68", target)
    a.imm("68", mission)
    a.imm("b9", actor)
    a.emit("8b 01 ff 90 20 03 00 00 c3")
    return ops.run(a.finish())


def spawn_near(ops, p, typ, house, x, y, z=832):
    for radius in range(0, 5):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                obj = ops.spawn_clone_at(typ, house,
                                         ((x + dx) * 256 + 128,
                                          (y + dy) * 256 + 128, z))
                if obj:
                    return obj
    raise RuntimeError(f"no safe cell near {x},{y}")


def xyz(p, obj):
    raw = p.read(obj + 0x88, 12)
    return struct.unpack("<iii", raw) if raw else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--infantry", action="store_true", help="use isolated E1 infantry")
    parser.add_argument("--isolated-tank", action="store_true", help="use tank away from the first E1")
    args = parser.parse_args()
    p = Process(21632)
    ops = GameOperations(p)
    ctl = AllTargetController(p)
    me = units.player_house(p)
    enemy = units.enemy_houses(p)[0]
    target = tank = 0
    try:
        jet_type = 0x123E2780
        shooter_type = 0x123DF590 if args.infantry else 0x1252A9B8
        shooter_name = "E1" if args.infantry else "MTNK"
        if p.read_cstr(jet_type + 0x24, 24) != "JUMPJET" or p.read_cstr(shooter_type + 0x24, 24) != shooter_name:
            raise RuntimeError("test type identities changed")
        enemy_type = p.read_u32(enemy + 0x34)
        if not enemy_type or p.read_cstr(enemy_type + 0x24, 24) != "French":
            raise RuntimeError("the designated opponent is not the verified French enemy")
        x, y = ((80, 100) if args.infantry else
                (80, 110) if args.isolated_tank else (100, 100))
        tank = spawn_near(ops, p, shooter_type, me, x + 3, y + 1)
        target = spawn_near(ops, p, jet_type, me, x, y)
        print("created", hex(target), xyz(p, target), hex(tank), xyz(p, tank), flush=True)
        cellbuf = p.alloc(0x1000)
        try:
            tx, ty, _tz = xyz(p, target)
            p.write(cellbuf, struct.pack("<hh", (tx >> 8) + 2, (ty >> 8) + 1))
            cell = ops.executor.call(0x548070, this=0x8324E0, args=(cellbuf,))
            if cell in (0, 0xA6F9F8):
                raise RuntimeError("cannot get move destination")
            issue(ops, target, 2, destination=cell)
        finally:
            p.free(cellbuf)
        vt = p.read_u32(target)
        in_air_fn = p.read_u32(vt + 0x54)
        if in_air_fn != 0x4CCE70:
            raise RuntimeError("infantry IsInAir virtual changed")
        deadline = time.monotonic() + 10
        airborne = False
        while time.monotonic() < deadline:
            airborne = bool(ops.executor.call(in_air_fn, this=target) & 0xFF)
            if airborne:
                break
            time.sleep(0.2)
        print("airborne", airborne, "target_xyz", xyz(p, target),
              "mission", p.read_i32(target + 0x98), flush=True)
        if not airborne:
            return
        ctl.set(True)
        original_hp = p.read_i32(target + 0x6C)
        if not ops.transfer(target, vt, enemy):
            raise RuntimeError("target ownership transfer failed")
        print("enemy_target", hex(p.read_u32(target + 0x1B4)), "hp", original_hp, flush=True)
        issue(ops, tank, 1, target=target)
        values = []
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            hp = p.read_i32(target + 0x6C)
            air_now = bool(ops.executor.call(in_air_fn, this=target) & 0xFF)
            values.append((hp, air_now))
            if hp is None or (hp < original_hp and air_now):
                break
            time.sleep(0.2)
        print(shooter_name + "_hit", values[-1] if values else None,
              "initial", original_hp, "samples", len(values),
              "tank_mission", p.read_i32(tank + 0x98),
              "tank_xyz", xyz(p, tank), "target_xyz", xyz(p, target), flush=True)
    finally:
        if target and p.read_u32(target) == 0x7A3540 and p.read_i32(target + 0x6C) and p.read_i32(target + 0x6C) > 0:
            if p.read_u32(target + 0x1B4) == enemy:
                try:
                    ops.transfer(target, 0x7A3540, me)
                    print("target_returned_to_player", flush=True)
                except Exception as exc:
                    print("target_return_failed", exc, flush=True)
        ctl.close()
        ops.close()
        p.close()


if __name__ == "__main__":
    main()
