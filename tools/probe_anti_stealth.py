"""One-session probe of sensor interfaces on a live map cell.

PID and object layout belong to the current skirmish; do not reuse blindly.
"""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer import units
from trainer.anti_stealth import AntiStealthController, SITES
from trainer.executor import MainThreadExecutor
from trainer.mem import Process


def main():
    p = Process(21632)
    ex = MainThreadExecutor(p)
    ctl = AntiStealthController(p)
    buf = p.alloc(0x1000)
    try:
        me = units.player_house(p)
        enemy = units.enemy_houses(p)[0]
        own_idx = p.read_i32(me + 0x30)
        enemy_idx = p.read_i32(enemy + 0x30)
        obj = units.player_technos(p)[0][0]
        x, y, _z = struct.unpack("<iii", p.read(obj + 0x88, 12))
        p.write(buf, struct.pack("<hh", x >> 8, y >> 8))
        cell = ex.call(0x548070, this=0x8324E0, args=(buf,))
        print("cell", hex(cell), "indexes", own_idx, enemy_idx, flush=True)
        def sample(label):
            rows = [[ex.call(site, this=cell, args=(idx,))
                     for idx in (own_idx, enemy_idx)] for site in SITES]
            print(label, rows, flush=True)
            return rows
        before = sample("before")
        ctl.set(True)
        enabled = sample("enabled")
        ctl.set(False)
        after = sample("after")
        print("player_senses", [r[0] for r in enabled],
              "enemy_unchanged", [r[1] for r in before] == [r[1] for r in enabled],
              "restored", before == after, flush=True)
    finally:
        ctl.close()
        ex.close()
        p.free(buf)
        p.close()


if __name__ == "__main__":
    main()
