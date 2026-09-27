"""运行时对象枚举：按 vtable 在堆上找实例，并解析 HouseClass 的向量字段。

用法：
    python tools/objects.py                 # 统计各类实例数
    python tools/objects.py --houses        # 解析各势力的 Buildings/Units 等向量
    python tools/objects.py --player        # 只列玩家势力的单位
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "trainer"))

VT = {
    0x7A2DE0: "HouseClass",
    0x7ACB80: "TechnoClass",
    0x7ADDF8: "UnitClass",
    0x7A3540: "InfantryClass",
    0x79CBBC: "BuildingClass",
    0x79B12C: "AircraftClass",
    0x7AC210: "SuperClass",
}
TECHNO_VTS = {0x7ACB80, 0x7ADDF8, 0x7A3540, 0x79CBBC, 0x79B12C}
PLAYER_PTR = 0xA35DB4
HOUSE_ARRAY = 0xA3229C


def scan_all(proc):
    """一次遍历堆，返回 {vtable: [addr,...]}。"""
    found = {vt: [] for vt in VT}
    targets = {struct.pack("<I", vt): vt for vt in VT}
    for base, size, state, protect, typ in proc.iter_regions(0x10000, 0xFFFFFFFF):
        if state != 0x1000 or protect & (0x100 | 0x01):
            continue
        if protect & (0x20 | 0x40 | 0x80):
            continue
        if typ != 0x20000 or size > 0x4000000:
            continue
        blob = proc.read(base, size)
        if not blob:
            continue
        for pat, vt in targets.items():
            i = blob.find(pat)
            while i >= 0:
                found[vt].append(base + i)
                i = blob.find(pat, i + 1)
    return found


def read_house_vectors(proc, h, upto=0x600):
    """扫描 HouseClass 里所有 DynamicVectorClass 槽位（Items@+0, Count@+0xC）。"""
    out = []
    for off in range(0, upto, 4):
        items = proc.read_u32(h + off)
        if not items or items < 0x10000 or items > 0x7FFFFFFF:
            continue
        cnt = proc.read_i32(h + off + 0xC)
        if cnt is None or cnt <= 0 or cnt > 2000:
            continue
        blob = proc.read(items, min(cnt, 64) * 4)
        if not blob or len(blob) < 4:
            continue
        kinds = {}
        ok = 0
        for k in range(len(blob) // 4):
            p = struct.unpack_from("<I", blob, k * 4)[0]
            vt = proc.read_u32(p) if p > 0x10000 else None
            name = VT.get(vt, "?")
            if vt is not None and vt in TECHNO_VTS:
                ok += 1
            kinds[name] = kinds.get(name, 0) + 1
        if ok and ok >= max(1, (cnt if cnt <= 8 else 8) * 0.6):
            out.append((off, items, cnt, kinds))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--houses", action="store_true")
    ap.add_argument("--player", action="store_true")
    ap.add_argument("--limit", type=int, default=8)
    a = ap.parse_args()

    from mem import Process
    proc = Process(a.pid if a.pid else "game.exe")
    print("attached pid=%d" % proc.pid)

    res = scan_all(proc)
    print("\n== 实例统计 ==")
    for vt, lst in res.items():
        if lst:
            print(f"  {VT[vt]:14} {len(lst):5}  e.g. {[hex(x) for x in lst[:3]]}")

    player = proc.read_u32(PLAYER_PTR)
    houses = res[0x7A2DE0]
    print(f"\n玩家 HouseClass = {hex(player) if player else None}")
    print(f"HouseClass::Array = {hex(HOUSE_ARRAY)} items={hex(proc.read_u32(HOUSE_ARRAY) or 0)} "
          f"count={proc.read_i32(HOUSE_ARRAY + 0xC)}")

    if a.houses:
        for h in houses:
            typ = proc.read_u32(h + 0x34)
            print(f"\n-- house 0x{h:08X} Type=0x{typ:08X} credits={proc.read_i32(h+0x24C)}")
            for off, items, cnt, kinds in read_house_vectors(proc, h):
                kind = ",".join(f"{k}x{v}" for k, v in sorted(kinds.items()))
                print(f"    vector +0x{off:<4X} items=0x{items:08X} count={cnt:<4} [{kind}]")

    if a.player:
        print("\n== 玩家向量明细 ==")
        for off, items, cnt, kinds in read_house_vectors(proc, player):
            print(f"  vector +0x{off:X} count={cnt} {kinds}")
            blob = proc.read(items, cnt * 4)
            for k in range(min(cnt, a.limit)):
                p = struct.unpack_from("<I", blob, k * 4)[0]
                vt = proc.read_u32(p)
                print(f"      [{k}] 0x{p:08X} {VT.get(vt, hex(vt) if vt else '?')} "
                      f"health={proc.read_i32(p + 0x80) if vt in TECHNO_VTS else '-'}")
    proc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
