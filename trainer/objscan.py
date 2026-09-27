"""运行时对象枚举（vtable 扫描）。

对象头部的布局（MSVC 多重继承）：
    [0] 主 vtable 指针
    [4][8][0xC] ... 各基类子对象的 vtable 指针
它们都指向映像空间（.rdata/.text），可用来排除「结构里恰好存着某个
vtable 值的指针」这类假阳性。
"""
import struct

IMAGE_LO = 0x400000
IMAGE_HI = 0xB30000

# 对象 vptr（RTTI 候选里的最后一个 = 最派生类）
OBJ_VT = {
    0x7A2DE0: "HouseClass",
    0x7ACB80: "TechnoClass",
    0x7ADDF8: "UnitClass",
    0x7A3540: "InfantryClass",
    0x79CBBC: "BuildingClass",
    0x79B12C: "AircraftClass",
    0x7AC210: "SuperClass",
}
# 类型对象 vptr
TYPE_VT = {
    0x7A3048: "HouseTypeClass",
    0x7AD080: "TechnoTypeClass",
    0x7AE328: "UnitTypeClass",
    0x7A3A78: "InfantryTypeClass",
    0x79D1F8: "BuildingTypeClass",
    0x79B678: "AircraftTypeClass",
    0x7AC2B8: "SuperWeaponTypeClass",
}
TECHNO_VT = {0x7ACB80, 0x7ADDF8, 0x7A3540, 0x79CBBC, 0x79B12C}
FOOT_VT = {0x7ADDF8, 0x7A3540, 0x79B12C}   # UnitClass/InfantryClass/AircraftClass


def _second_ok(blob, i, base, proc, a):
    """校验 [a+4] 落在映像空间（排除假阳性），尽量直接用已读到的 blob。"""
    j = i + 4
    if j + 4 <= len(blob):
        second = struct.unpack_from("<I", blob, j)[0]
    else:
        second = proc.read_u32(a + 4)
    return second is not None and IMAGE_LO <= second < IMAGE_HI


def iter_objects(proc, vts=None):
    """一次遍历堆，产出 (addr, vtable)。"""
    vts = list(vts or OBJ_VT)
    targets = {struct.pack("<I", v): v for v in vts}
    for base, size, state, protect, typ in proc.iter_regions(0x10000, 0xFFFFFFFF):
        if state != 0x1000 or protect & (0x100 | 0x01):
            continue
        if protect & (0x20 | 0x40 | 0x80) or typ != 0x20000 or size > 0x4000000:
            continue
        blob = proc.read(base, size)
        if not blob:
            continue
        for pat, vt in targets.items():
            i = blob.find(pat)
            while i >= 0:
                a = base + i
                # Heap objects are at least 4-byte aligned; skip unaligned noise.
                if not i & 3 and _second_ok(blob, i, base, proc, a):
                    yield a, vt
                i = blob.find(pat, i + 1)


def collect(proc, vts=None):
    """返回 {vtable: [addr, ...]}。"""
    out = {}
    for a, vt in iter_objects(proc, vts):
        out.setdefault(vt, []).append(a)
    return out
