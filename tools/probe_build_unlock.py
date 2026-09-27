"""One-session live verification of player-scoped build hooks.

PID and addresses are from this skirmish; do not reuse in another game.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer.mem import Process
from trainer.executor import MainThreadExecutor
from trainer.build_unlock import BuildUnlockController
from trainer import units


def main():
    proc = Process(21632)
    ex = MainThreadExecutor(proc)
    ctl = BuildUnlockController(proc)
    try:
        me = units.player_house(proc)
        others = units.enemy_houses(proc)
        types = []
        seen = set()
        for obj, vt in units.iter_technos(proc):
            typ = units.type_of(proc, obj, vt)
            if typ and typ not in seen and proc.read_i32(typ + 0x55C) != -1:
                seen.add(typ)
                types.append(typ)
            if len(types) >= 35:
                break
        print("houses", hex(me), [hex(x) for x in others], "types", len(types), flush=True)
        houses = [me] + others[:1]
        def sample(label):
            rows = []
            for house in houses:
                values = []
                for typ in types:
                    ans = ex.call(0x4E3660, house, (typ, 0, 0), timeout=3)
                    values.append(ans)
                rows.append(values)
            print(label, rows, flush=True)
            return rows
        before = sample("before")
        ctl.set("tech_all", True)
        tech = sample("tech")
        ctl.set("unlock_build", True)
        both = sample("both")
        ctl.set("tech_all", False)
        unlock = sample("unlock")
        ctl.set("unlock_build", False)
        after = sample("after")
        print("restored", before == after, "tech_changed_player", before[0] != tech[0],
              "unlock_changed_player", tech[0] != both[0],
              "ai_unchanged", all(row[1] == before[1] for row in (tech, both, unlock, after)),
              flush=True)
        print("type_addrs", [hex(x) for x in types], flush=True)
    finally:
        ctl.close()
        ex.close()
        proc.close()


if __name__ == "__main__":
    main()
