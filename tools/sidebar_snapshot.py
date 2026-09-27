"""Read the current RA2 1.006 production sidebar without modifying the game.

Run before and after toggling technology/build restrictions to compare items.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer.mem import Process

SIDEBAR = 0x8324E0
ARRAYS = {7: 0xA35CDC, 16: 0xA40354, 40: 0xA35D4C, 3: 0xA3D27C}
KINDS = {7: "建筑", 16: "步兵", 40: "载具", 3: "飞机"}


def snapshot(proc):
    result = []
    for strip in range(4):
        base = SIDEBAR + 0x1540 + strip * 0xE64
        count = proc.read_i32(base + 0x50)
        if count is None or not 0 <= count <= 75:
            raise RuntimeError(f"sidebar strip {strip} has an invalid count: {count}")
        for slot in range(count):
            item = base + 0x54 + slot * 0x30
            index, kind = proc.read_i32(item), proc.read_i32(item + 4)
            row = dict(strip=strip, slot=slot, kind=kind, index=index)
            array_address = ARRAYS.get(kind)
            if array_address is not None:
                data = proc.read_u32(array_address)
                length = proc.read_i32(array_address + 0xC)
                if data and length is not None and 0 <= index < length <= 1000:
                    typ = proc.read_u32(data + index * 4)
                    if typ:
                        row["name"] = proc.read_cstr(typ + 0x24, 32)
                        row["category"] = KINDS[kind]
            result.append(row)
    return result


def main():
    proc = Process("game.exe")
    try:
        print(json.dumps(snapshot(proc), ensure_ascii=False, indent=2))
    finally:
        proc.close()


if __name__ == "__main__":
    main()
