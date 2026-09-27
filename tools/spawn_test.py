"""Spawn one player-owned ground unit through the simulation-thread executor.

Usage: python tools/spawn_test.py MTNK 3
The type keyword matches the internal ID or display name; offset is in cells.
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trainer.mem import Process
from trainer.operations import GameOperations
from trainer.units import player_technos, type_of, player_house
from trainer.patches import PatchManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keyword", nargs="?", default="MTNK")
    parser.add_argument("offset", nargs="?", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= abs(args.offset) <= 10:
        parser.error("offset must be between -10 and 10, excluding zero")
    p = Process("game.exe")
    ops = GameOperations(p)
    try:
        if not PatchManager(p).compatible():
            raise RuntimeError("游戏版本不匹配")
        for a, vt in player_technos(p):
            if vt not in (0x7ADDF8, 0x7A3540):
                continue
            typ = type_of(p, a, vt)
            name = (p.read_cstr(typ + 0x24, 32) or "") + " " + (p.read_cstr(typ + 0x64, 64) or "")
            if args.keyword.lower() not in name.lower():
                continue
            x, y, z = struct.unpack("<iii", p.read(a + 0x88, 12))
            xyz = (((x >> 8) + args.offset) * 256 + 128, ((y >> 8) + args.offset) * 256 + 128, z)
            new = ops.spawn_at(typ, player_house(p), xyz)
            print(f"{name}: " + (f"新对象 0x{new:08X}" if new else "放置失败，已清理对象"))
            return
        print("没有匹配的己方载具/步兵")
    finally:
        try:
            ops.close()
        finally:
            p.close()


if __name__ == "__main__":
    main()
