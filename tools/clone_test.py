"""Clone selected ground units using the same implementation as the UI."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trainer.mem import Process
from trainer.operations import GameOperations
from trainer.patches import PatchManager


def main():
    p = Process("game.exe")
    ops = GameOperations(p)
    try:
        if not PatchManager(p).compatible():
            raise RuntimeError("游戏版本不匹配")
        done, total = ops.clone_selected()
        print(f"复制完成：{done}/{total}")
    finally:
        try:
            ops.close()
        finally:
            p.close()


if __name__ == "__main__":
    main()
