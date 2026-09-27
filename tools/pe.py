"""Minimal PE reader + x86 disassembler helpers for game.exe analysis."""
import struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32


class Section:
    def __init__(self, name, va, vsz, raw, rsz):
        self.name, self.va, self.vsz, self.raw, self.rsz = name, va, vsz, raw, rsz

    @property
    def end(self):
        return self.va + max(self.vsz, self.rsz)


class PE:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.data = f.read()
        d = self.data
        e = struct.unpack_from("<I", d, 0x3C)[0]
        assert d[e:e + 4] == b"PE\0\0"
        nsec = struct.unpack_from("<H", d, e + 6)[0]
        optsz = struct.unpack_from("<H", d, e + 20)[0]
        opt = e + 24
        self.imagebase = struct.unpack_from("<I", d, opt + 28)[0]
        secoff = opt + optsz
        self.sections = []
        for i in range(nsec):
            o = secoff + i * 40
            name = d[o:o + 8].rstrip(b"\0").decode("latin1")
            vsz, va, rsz, raw = struct.unpack_from("<IIII", d, o + 8)
            self.sections.append(Section(name, va, vsz, raw, rsz))
        self.md = Cs(CS_ARCH_X86, CS_MODE_32)
        self.md.detail = False

    # ---- address translation ----
    def rva(self, va):
        return va - self.imagebase

    def fileoff(self, va):
        r = self.rva(va)
        for s in self.sections:
            if s.va <= r < s.va + s.rsz:
                return s.raw + (r - s.va)
        return None

    def read(self, va, n):
        o = self.fileoff(va)
        if o is None:
            return None
        return self.data[o:o + n]

    def u32(self, va):
        b = self.read(va, 4)
        return None if b is None or len(b) < 4 else struct.unpack("<I", b)[0]

    def u8(self, va):
        b = self.read(va, 1)
        return None if b is None or len(b) < 1 else b[0]

    def contains(self, va):
        return self.fileoff(va) is not None

    # ---- disassembly ----
    def dis(self, va, size=0x80, count=0):
        b = self.read(va, size)
        if not b:
            return []
        out = []
        for i in self.md.disasm(b, va):
            out.append((i.address, i.mnemonic, i.op_str))
            if count and len(out) >= count:
                break
        return out

    def dump(self, va, size=0x80, count=0):
        return "\n".join(f"0x{a:08X}:\t{m}\t{o}" for a, m, o in self.dis(va, size, count))

    # ---- byte signature check ----
    def sig(self, va, hexstr):
        exp = bytes.fromhex(hexstr.replace(" ", ""))
        got = self.read(va, len(exp))
        return got == exp

    # ---- strings + xrefs ----
    def ascii_strings(self, lo=None, hi=None, minlen=5):
        out = []
        for s in self.sections:
            start, size = s.raw, s.rsz
            blob = self.data[start:start + size]
            i = 0
            n = len(blob)
            while i < n:
                if 0x20 <= blob[i] <= 0x7E:
                    j = i
                    while j < n and 0x20 <= blob[j] <= 0x7E:
                        j += 1
                    if j - i >= minlen:
                        va = self.imagebase + s.va + i
                        if lo is None or lo <= va <= hi:
                            out.append((va, blob[i:j].decode("latin1")))
                    i = j
                else:
                    i += 1
        return out

    def find_str(self, text, start_va=0):
        """Return VA of first ascii occurrence of text in any section."""
        pat = text.encode("latin1")
        for s in self.sections:
            blob = self.data[s.raw:s.raw + s.rsz]
            i = 0
            while True:
                i = blob.find(pat, i)
                if i < 0:
                    break
                va = self.imagebase + s.va + i
                if va >= start_va:
                    return va
                i += 1
        return None

    def xrefs(self, va, sect_filter=None):
        """Find immediate 32-bit references to va (push/mov/cmp/lea reg, imm)."""
        hits = []
        for s in self.sections:
            if s.name not in (".text",):
                continue
            blob = self.data[s.raw:s.raw + s.rsz]
            pat = struct.pack("<I", va)
            i = 0
            while True:
                i = blob.find(pat, i)
                if i < 0:
                    break
                hits.append(self.imagebase + s.va + i)
                i += 1
        return hits

    def xrefs_disasm(self, va, ctx=8):
        """Xrefs with a bit of surrounding disassembly text."""
        out = []
        for x in self.xrefs(va):
            line = self.dis(x - ctx, ctx + 6, 6)
            out.append((x, line))
        return out
