"""选中单位机制探针。

用法：
    python tools/selwatch.py dump     # 记录当前快照（选之前）
    #   -> 在游戏里选中 1~几个己方单位
    python tools/selwatch.py diff     # 对比，找出「选中」相关字段/全局

原理：
  1. 记录 .data 里所有指向己方技术类对象的全局指针；
  2. 记录每个己方对象 0x10..0x300 的原始字节；
  对比时变化的全局/字节即为选中标记。
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from trainer.mem import Process          # noqa: E402
from trainer.units import player_technos  # noqa: E402
from trainer import objscan as O          # noqa: E402

SNAP = os.path.join(os.environ.get("TEMP", "."), "sel_snapshot.json")
DATA_LO, DATA_HI = 0x7C9000, 0xB2D000
B0, B1 = 0x10, 0x300


def dump():
    p = Process("game.exe")
    targets = player_technos(p)
    addrs = {a for a, _ in targets}
    print("己方技术类对象:", len(addrs))
    blob = p.read(DATA_LO, DATA_HI - DATA_LO) or b""
    globals_ = {}
    for i in range(0, len(blob) - 3, 4):
        v = struct.unpack_from("<I", blob, i)[0]
        if v in addrs:
            globals_[hex(DATA_LO + i)] = hex(v)
    print(".data 中指向这些对象的全局:", len(globals_))
    bytes_ = {}
    for a in addrs:
        b = p.read(a + B0, B1 - B0)
        if b:
            bytes_[hex(a)] = b.hex()
    json.dump({"globals": globals_, "bytes": bytes_}, open(SNAP, "w"))
    print("已保存 ->", SNAP)
    p.close()


def diff():
    old = json.load(open(SNAP))
    p = Process("game.exe")
    print("== 全局指针变化（只列指向技术类对象的） ==")
    blob = p.read(DATA_LO, DATA_HI - DATA_LO) or b""
    now = {}
    for i in range(0, len(blob) - 3, 4):
        now[hex(DATA_LO + i)] = struct.unpack_from("<I", blob, i)[0]
    for k, v in old["globals"].items():
        nv = now.get(k)
        if nv is not None and hex(nv) != v:
            tv = p.read_u32(nv) if nv and 0x10000 < nv < 0x7FFFFFFF else None
            print(f"  {k}: {v} -> 0x{nv:08X} {O.OBJ_VT.get(tv, '')}")

    print("== 单字节 0<->1 翻转（按偏移汇总） ==")
    from collections import defaultdict
    by_off = defaultdict(list)
    for a_hex, hexstr in old["bytes"].items():
        a = int(a_hex, 16)
        b = p.read(a + B0, B1 - B0)
        if not b:
            continue
        old_b = bytes.fromhex(hexstr)
        vt = p.read_u32(a)
        for i, (x, y) in enumerate(zip(old_b, b)):
            if (x, y) in ((0, 1), (1, 0)):
                by_off[B0 + i].append((a, O.OBJ_VT.get(vt, hex(vt or 0)), x, y))
    for off in sorted(by_off):
        items = by_off[off]
        mark = "  <<<<<" if len(items) <= 2 else ""
        print(f"  +0x{off:03X}: {len(items)} 个{mark}")
        if len(items) <= 4:
            for a, cls, x, y in items:
                print(f"        0x{a:08X} [{cls}] {x} -> {y}")
    p.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "diff":
        diff()
    else:
        dump()
