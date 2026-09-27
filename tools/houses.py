"""运行时定位 HouseClass / 选中单位等关键对象。

原理：
  1. 静态已知 HouseClass 主 vtable = 0x7A2DE0（见 tools/rtti.py）
  2. 对象 +0 处保存该 vtable，因此扫描堆内存中等于 vtable 的 DWORD 即可拿到实例地址
  3. 用已知的候选资金字段（+0x24C / +0x124）与屏幕上显示的金额比对，确认偏移
  4. 再用 find_pointers_to 反查 .data 中指向该实例的全局指针 -> HouseClass::Player

用法（游戏需已进入遭遇战）：
  python tools/houses.py            # 自动附加 game.exe 并打印报告
  python tools/houses.py --value 10000   # 附加已知资金值，辅助确认偏移
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "trainer"))
from mem import Process  # noqa: E402

VT_HOUSECLASS = 0x7A2DE0
VT_UNITCLASS = 0x7ADDF8
VT_TECHNOCLASS = 0x7ACB80
VT_SUPERCLASS = 0x7AC210

CANDIDATE_MONEY = [0x24C, 0x124, 0x118, 0x120, 0x250]
# 参考：YR 1.001 的 CurrentPlayer(0x1EC) / PlayerControl(0x1ED)，RA2 仅作参考
FLAG_OFFS = [0x1EC, 0x1ED, 0x1F4, 0x1F5]

DATA_LO, DATA_HI = 0x7C9000, 0xB2D000


def scan_vtables(proc, vtables, heap_only=True):
    """Return {vtable: [object_addr, ...]} for committed *heap* regions.

    必须排除映像区/可执行页：.text 里 `mov [reg], 0x7A2DE0` 这类指令的立即数
    会被误判为对象，产生假阳性。
    """
    found = {vt: [] for vt in vtables}
    import struct
    targets = {struct.pack("<I", vt): vt for vt in vtables}
    for base, size, state, protect, typ in proc.iter_regions(0x10000, 0xFFFFFFFF):
        if state != 0x1000 or protect & (0x100 | 0x01):     # 只要已提交、非 guard/noaccess
            continue
        if protect & (0x20 | 0x40 | 0x80):                  # 跳过可执行页
            continue
        if heap_only and typ != 0x20000:                    # 只要 MEM_PRIVATE（堆）
            continue
        if size > 0x4000000:
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


def find_array(proc, houses, data_lo=DATA_LO, data_hi=DATA_HI):
    """定位 HouseClass::Array：动态数组指针指向一串 house 指针。"""
    import struct
    # 1) 找到所有指向这些 house 的位置（全可写区）
    owners = {}
    for h in houses:
        for p in proc.find_pointers_to(h):   # 全可写内存（Items 数组在堆上）
            owners.setdefault(p, []).append(h)
    # 2) 找到"4 个连续 house 指针"的块（即 Items 数组）
    blocks = []
    hs = set(houses)
    for p in sorted(owners):
        blob = proc.read(p, 4 * len(houses))
        if not blob:
            continue
        vals = struct.unpack("<%dI" % len(houses), blob)
        if hs.issuperset(vals) and len(set(vals)) == len(houses):
            blocks.append((p, vals))
    # 3) 反查指向该块的全局（Items@+0, Count@+0xC）
    out = []
    for blk, vals in blocks:
        for g in proc.find_pointers_to(blk, data_lo, data_hi):
            cnt = proc.read_i32(g + 0xC)
            if cnt == len(houses):
                out.append((g, blk, cnt, vals))
    return out


def dump_house(proc, h, path, size=0x16100):
    blob = proc.read(h, size)
    if not blob:
        return False
    with open(path, "wb") as f:
        f.write(blob)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--value", type=int, default=None, help="当前资金值（用于确认偏移）")
    ap.add_argument("--no-pointer", action="store_true", help="跳过全局指针反查（更快）")
    ap.add_argument("--array", action="store_true", help="定位 HouseClass::Array")
    ap.add_argument("--dump", default=None, help="把玩家 HouseClass 结构导出到该目录")
    ap.add_argument("--set-credits", type=int, default=None, help="直接把玩家资金改成该值（测试用）")
    a = ap.parse_args()

    pids = Process.find_pids(["game.exe", "gamemd.exe"])
    if not pids:
        print("game.exe 未运行")
        return 1
    pid, name = pids[0]
    print(f"attached pid={pid} ({name})")
    proc = Process(pid)

    res = scan_vtables(proc, [VT_HOUSECLASS, VT_UNITCLASS, VT_SUPERCLASS])
    houses = res[VT_HOUSECLASS]
    print(f"HouseClass 实例数: {len(houses)}")
    if not houses:
        print("未发现任何 HouseClass 实例（是否已进入遭遇战？）")
        proc.close()
        return 0

    house_globals = {}
    for i, h in enumerate(houses):
        typ = proc.read_u32(h + 0x34)
        vals = {off: proc.read_i32(h + off) for off in CANDIDATE_MONEY}
        flags = {off: proc.read_u8(h + off) for off in FLAG_OFFS}
        hdr = f"\n[{i}] house=0x{h:08X}"
        if typ:
            hdr += f" Type=0x{typ:X}"
        print(hdr)
        print("    资金候选: " + ", ".join(f"+{o:X}={vals[o]}" for o in CANDIDATE_MONEY))
        if a.value is not None:
            # 扫描整段结构，找出所有等于已知资金值的字段
            hits = []
            blob = proc.read(h + 0x30, 0x600)
            if blob:
                for off in range(0, len(blob) - 3, 4):
                    if struct.unpack_from("<i", blob, off)[0] == a.value:
                        hits.append(0x30 + off)
            if hits:
                print(f"    >>> 等于 {a.value} 的偏移: " + ", ".join(f"+{o:X}" for o in hits))
            else:
                print(f"    >>> 结构前 0x600 字节内没有 {a.value}")
        print("    标志位: " + ", ".join(f"+{o:X}={flags[o]}" for o in FLAG_OFFS))

        if not a.no_pointer:
            ptrs = [p for p in proc.find_pointers_to(h, DATA_LO, DATA_HI)]
            house_globals[h] = ptrs
            if ptrs:
                print("    指向它的全局: " + ", ".join(f"0x{p:X}" for p in ptrs[:8]))

    # ---- 玩家势力：唯一在 .data 中有全局指针指向的那个 ----
    player = None
    for h, g in house_globals.items():
        if g:
            player = h
            break
    if player is None and houses:
        player = houses[0]
    print(f"\n玩家 HouseClass = 0x{player:08X}" if player else "\n未找到玩家势力")
    if player:
        pg = house_globals.get(player, [])
        print("  HouseClass::Player 全局指针 = " +
              (", ".join(f"0x{x:X}" for x in pg) if pg else "未找到"))
        print(f"  Credits (当前资金)      = +0x24C -> {proc.read_i32(player + 0x24C)}")
        print(f"  StartingCredits (初始)  = +0x124 -> {proc.read_i32(player + 0x124)}")

    if a.set_credits is not None and player:
        ok = proc.write_i32(player + 0x24C, a.set_credits)
        print(f"写入资金 {a.set_credits} -> {'成功' if ok else '失败'}，"
              f"回读={proc.read_i32(player + 0x24C)}")

    if a.dump and player:
        path = os.path.join(a.dump, "house_player.bin")
        print("导出结构 ->", path, "ok" if dump_house(proc, player, path) else "失败")

    if a.array:
        print("\n== HouseClass::Array ==")
        for g, blk, cnt, vals in find_array(proc, houses):
            print(f"  Array@0x{g:X}  Items@0x{blk:X}  Count={cnt}  "
                  f"members={[hex(v) for v in vals]}")

    units = res[VT_UNITCLASS]
    supers = res[VT_SUPERCLASS]
    print(f"\nUnitClass 实例数: {len(units)}   SuperClass 实例数: {len(supers)}")
    proc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
