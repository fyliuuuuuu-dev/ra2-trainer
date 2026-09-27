"""One-session validation of technology prerequisites and airport exclusivity.

Requires the GUI trainer to be closed. Does not start production or change the
saved user configuration; all hooks are removed in finally.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer import units
from trainer.build_unlock import BuildUnlockController
from trainer.executor import MainThreadExecutor
from trainer.mem import Process
from tools.probe_tech_sidebar import all_types
from tools.sidebar_snapshot import snapshot


WATCH = {"GAAIRC", "AMRADR", "APOC", "NAPOWR", "NATECH", "E2", "HTNK",
         "DESO", "TTNK", "SNIPE", "GAPLUG", "BEAG", "ORCA"}


def main():
    p = Process(21632)
    ex = MainThreadExecutor(p)
    ctl = BuildUnlockController(p)
    try:
        types = {name: typ for typ, name, _level in all_types(p).values() if name in WATCH}
        me = units.player_house(p)
        enemy = units.enemy_houses(p)[0]
        baseline = None
        for label, tech, unlock in (("baseline", False, False),
                                    ("tech", True, False),
                                    ("both", True, True),
                                    ("unlock_only", False, True),
                                    ("restored", False, False)):
            ctl.set("tech_all", tech)
            ctl.set("unlock_build", unlock)
            if ctl.base:
                ctl.refresh_sidebar(ex)
                time.sleep(0.3)
            shown = {r.get("name") for r in snapshot(p)} & WATCH
            answer = {name: (ex.call(0x4E3660, this=me, args=(typ, 0, 0)),
                             ex.call(0x4E3660, this=enemy, args=(typ, 0, 0)))
                      for name, typ in types.items()}
            if baseline is None:
                baseline = (shown, answer)
            print(label, "shared_prereq", "prerequisites" in ctl.installed,
                  "shown", sorted(shown), "canbuild", answer,
                  "restored", (shown, answer) == baseline, flush=True)
    finally:
        ctl.close()
        if ctl.base:
            ctl.refresh_sidebar(ex)
        ex.close()
        p.close()


if __name__ == "__main__":
    main()
