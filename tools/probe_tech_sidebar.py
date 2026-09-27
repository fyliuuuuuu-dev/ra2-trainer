"""One-session regression: TechLevel=255 must stay hidden in every switch mode.

This installs live hooks. Close any GUI trainer before running it again.
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer import units
from trainer.build_unlock import BuildUnlockController
from trainer.executor import MainThreadExecutor
from trainer.mem import Process
from tools.sidebar_snapshot import ARRAYS, snapshot


def all_types(proc):
    result = {}
    for kind, array in ARRAYS.items():
        data, length = proc.read_u32(array), proc.read_i32(array + 0xC)
        if not data or length is None or not 0 <= length <= 1000:
            raise RuntimeError(f"invalid type vector {hex(array)}")
        for index in range(length):
            typ = proc.read_u32(data + index * 4)
            if typ:
                result[(kind, index)] = (typ, proc.read_cstr(typ + 0x24, 32),
                                         proc.read_i32(typ + 0x55C))
    return result


def main():
    proc = Process("game.exe")
    ex = MainThreadExecutor(proc)
    ctl = BuildUnlockController(proc)
    types = all_types(proc)
    player = units.player_house(proc)
    watched = {"NATMPL", "GAPLUG", "GAFIRE", "GAPOWRUP", "GACTWR",
               "NAWAST", "DeathDummy", "VISC_SML", "VISC_LRG", "APACHE",
               "NAREFN", "MTNK"}
    baseline = None
    try:
        for label, tech, unlock in (
                ("baseline", False, False),
                ("tech", True, False),
                ("restored1", False, False),
                ("unlock", False, True),
                ("restored2", False, False),
                ("both", True, True),
                ("unlock_only", False, True),
                ("restored3", False, False)):
            ctl.set("tech_all", tech)
            ctl.set("unlock_build", unlock)
            if ctl.base is not None:
                ctl.refresh_sidebar(ex)
                time.sleep(0.25)
            rows = snapshot(proc)
            current = {(r["kind"], r["index"]) for r in rows if r["kind"] in ARRAYS}
            if baseline is None:
                baseline = current
            extra = [types[k][1] for k in sorted(current - baseline) if k in types]
            missing = [types[k][1] for k in sorted(baseline - current) if k in types]
            forbidden = [types[k][1] for k in sorted(current)
                         if k in types and types[k][2] == 255]
            canbuild = {}
            for _key, (typ, name, _level) in types.items():
                if name in watched and name not in canbuild:
                    canbuild[name] = ex.call(0x4E3660, this=player,
                                             args=(typ, 0, 0))
            print(label, "counts", len(current), "added", extra[:30],
                  "removed", missing[:30], "level255_visible", forbidden[:30],
                  "canbuild", canbuild, flush=True)
    finally:
        ctl.close()
        if ctl.base is not None:
            ctl.refresh_sidebar(ex)
        ex.close()
        proc.close()


if __name__ == "__main__":
    main()
