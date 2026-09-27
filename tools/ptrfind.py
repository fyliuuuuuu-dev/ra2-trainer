"""查找指向某个对象地址的指针（用于定位「当前选中」等全局）。

用法：
    python tools/ptrfind.py 0x15411B88 dump     # 记录现在的所有指针位置
    python tools/ptrfind.py 0x15411B88 diff     # 对比，列出新出现/消失的位置
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from trainer.mem import Process  # noqa: E402

SNAP = os.path.join(os.environ.get("TEMP", "."), "ptrfind.json")


def scan(proc, target):
    pat = struct.pack("<I", target)
    out = []
    for base, size, state, protect, typ in proc.iter_regions(0x10000, 0xFFFFFFFF):
        if state != 0x1000 or protect & (0x100 | 0x01):
            continue
        if protect & (0x20 | 0x40 | 0x80) or size > 0x8000000:
            continue
        blob = proc.read(base, size)
        if not blob:
            continue
        i = blob.find(pat)
        while i >= 0:
            out.append({"at": base + i, "region": base, "type": typ})
            i = blob.find(pat, i + 4)
    return out


def main():
    target = int(sys.argv[1], 0)
    mode = sys.argv[2] if len(sys.argv) > 2 else "dump"
    p = Process("game.exe")
    res = scan(p, target)
    print(f"目标 0x{target:08X}: 共 {len(res)} 处指针")
    if mode == "dump":
        json.dump(res, open(SNAP, "w"))
        for r in res[:40]:
            print(f"  @0x{r['at']:08X} (区块 0x{r['region']:08X}, type={r['type']:#x})")
        print("已保存 ->", SNAP)
    else:
        old = json.load(open(SNAP))
        olds = {r["at"] for r in old}
        news = {r["at"] for r in res}
        print("== 新增（选中时出现） ==")
        for r in res:
            if r["at"] not in olds:
                print(f"  @0x{r['at']:08X} (区块 0x{r['region']:08X}, type={r['type']:#x})")
        print("== 消失（选中时不再指向它） ==")
        for r in old:
            if r["at"] not in news:
                print(f"  @0x{r['at']:08X} (区块 0x{r['region']:08X})")
    p.close()


if __name__ == "__main__":
    main()
