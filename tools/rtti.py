"""Locate MSVC RTTI vtables in a 32-bit PE."""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from pe import PE  # noqa: E402


def _allxrefs(pe, va):
    """Find dword references in every section (RTTI lives in .rdata)."""
    hits = []
    for s in pe.sections:
        blob = pe.data[s.raw:s.raw + s.rsz]
        pat = struct.pack("<I", va)
        i = 0
        while True:
            i = blob.find(pat, i)
            if i < 0:
                break
            hits.append(pe.imagebase + s.va + i)
            i += 1
    return hits


def find_vtable(pe, class_name, text_lo=0x401000, text_hi=0x7995CD):
    name_va = pe.find_str(".?AV%s@@" % class_name)
    if name_va is None:
        return None
    td = name_va - 8  # TypeDescriptor name at +8
    cols = []
    for x in _allxrefs(pe, td):  # dword == TD
        col = x - 0xC
        if pe.u32(col + 0xC) == td:
            cols.append(col)
    out = []
    for col in cols:
        sig = pe.u32(col)
        for y in _allxrefs(pe, col):
            vt = y + 4
            fn = pe.u32(vt)
            if fn and text_lo <= fn <= text_hi:
                out.append((vt, sig, [pe.u32(vt + 4 * i) for i in range(8)]))
    return {"td": td, "cols": cols, "vtables": out}


if __name__ == "__main__":
    pe = PE(sys.argv[1] if len(sys.argv) > 1 else
            "game.exe")  # 通过命令行参数传入游戏 exe 路径
    for cls in (sys.argv[2:] or ["HouseClass", "TechnoClass", "UnitClass", "SuperClass"]):
        r = find_vtable(pe, cls)
        if not r:
            print(f"{cls}: not found")
            continue
        print(f"{cls}: TD=0x{r['td']:X} COL={[hex(c) for c in r['cols']]}")
        for vt, sig, fns in r["vtables"]:
            print("   vtable=0x%X sig=%d fns=%s" % (vt, sig, [hex(f) for f in fns]))
