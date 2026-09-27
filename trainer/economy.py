"""Player-only economy: ore income multiplier, infinite ore, free repair, full refund.

    HouseClass::GiveTiberium(float amount, int type) 0x4E5100, ret 8
        Balance += OreValue * HouseType income * amount (refinery unload
        0x702400/0x702420 and the purifier bonus both pass through it).
    Harvest 0x7014F1: amount = cell->ReduceTiberium(amount) (0x475DB0,
        thiscall, ret 4), ESI = the harvester; then the cargo is filled.
    Repair steps: 0x44BBE2 (building self-repair) and 0x6C27DE (repair
        depot), cost = type->RepairStepCost() (vtable +0xB0), ESI = the object
        being repaired; the house then pays `cost` via 0x4E5280.
    TechnoTypeClass::GetRefund(HouseClass*, bool full) 0x6DAD80, ret 8:
        full=true gives 100% instead of Rules.RefundPercent.

Settings at the block start: +0 income factor (float), +4 infinite ore,
+8 free repair, +C full refund. Each site is installed only while its
feature is active, and every check compares the owner with the player.
"""
import math
import struct

from .addresses import PLAYER_PTR
from .executor import relative_jump
from .hooks import HookSites, assemble
from .operations import X86

INCOME, INFINITE, FREE_REPAIR, FULL_REFUND = 0, 4, 8, 0xC
OWNER = 0x1B4

SITES = {
    "income": (0x4E5100, bytes.fromhex("d9442404d80d002f7a00"), 0x100),
    "harvest": (0x7014F1, bytes.fromhex("e8ba48d7ff"), 0x200),
    "repair_building": (0x44BBE2, bytes.fromhex("ff90b0000000"), 0x300),
    "repair_unit": (0x6C27DE, bytes.fromhex("ff92b0000000"), 0x380),
    "refund": (0x6DAD80, bytes.fromhex("51a148988300"), 0x400),
}
REDUCE_TIBERIUM = 0x475DB0
FEATURE_SITES = {
    "ore_income": ("income",),
    "ore_infinite": ("harvest",),
    "repair_free": ("repair_building", "repair_unit"),
    "sell_full": ("refund",),
}


def _player_check(a, owner_reg_disp, skip):
    """Jump to `skip` unless [owner] is the player; clobbers EDX."""
    a.imm("8b 15", PLAYER_PTR)
    a.emit("85 d2")
    a.jump("0f 84", skip)
    a.emit(owner_reg_disp)  # cmp [reg+OWNER], edx
    a.code += struct.pack("<I", OWNER)
    a.jump("0f 85", skip)


def income_code(base, at):
    """Entry of GiveTiberium: ECX = house, [ESP+4] = amount (float)."""
    a = X86()
    a.emit("52")
    a.imm("8b 15", PLAYER_PTR)
    a.emit("39 d1")  # house == player
    a.jump("0f 85", "original")
    a.emit("d9 44 24 08")  # amount (after push edx)
    a.emit("d8 0d")
    a.code += struct.pack("<I", base + INCOME)
    a.emit("d9 5c 24 08")
    a.label("original")
    a.emit("5a")
    address, original, _ = SITES["income"]
    a.code += original
    code = a.finish()
    return code + relative_jump(at + len(code), address + len(original))


def harvest_code(base, at):
    """Replaces `call ReduceTiberium` (arg pushed, ECX = cell, ESI = harvester)."""
    address, original, _ = SITES["harvest"]
    back = address + len(original)
    a = X86()
    a.emit("83 3d")
    a.code += struct.pack("<I", base + INFINITE) + b"\x00"
    a.jump("0f 84", "reduce")
    _player_check(a, "39 96", "reduce")
    a.emit("58")  # EAX = requested amount; the cell keeps its ore
    a.code += relative_jump(at + len(a.code), back)
    a.label("reduce")
    call_at = at + len(a.code)
    a.code += b"\xe8" + struct.pack("<I", (REDUCE_TIBERIUM - call_at - 5) & 0xFFFFFFFF)
    code = a.finish()
    return code + relative_jump(at + len(code), back)


def repair_code(name, base, at):
    """Replaces `call [reg+0xB0]` (RepairStepCost); ESI = object being repaired."""
    address, original, _ = SITES[name]
    back = address + len(original)
    a = X86()
    a.emit("83 3d")
    a.code += struct.pack("<I", base + FREE_REPAIR) + b"\x00"
    a.jump("0f 84", "cost")
    a.emit("52")  # EDX may hold the vtable for the original call
    a.imm("8b 15", PLAYER_PTR)
    a.emit("85 d2")
    a.jump("0f 84", "restore")
    a.emit("39 96")
    a.code += struct.pack("<I", OWNER)
    a.jump("0f 85", "restore")
    a.emit("5a 31 c0")  # free
    a.code += relative_jump(at + len(a.code), back)
    a.label("restore")
    a.emit("5a")
    a.label("cost")
    a.code += original
    code = a.finish()
    return code + relative_jump(at + len(code), back)


def refund_code(base, at):
    """Entry of GetRefund: [ESP+4] = house, [ESP+8] = full-refund flag."""
    address, original, _ = SITES["refund"]
    a = X86()
    a.emit("83 3d")
    a.code += struct.pack("<I", base + FULL_REFUND) + b"\x00"
    a.jump("0f 84", "original")
    a.emit("52")
    a.imm("8b 15", PLAYER_PTR)
    a.emit("85 d2")
    a.jump("0f 84", "restore")
    a.emit("3b 54 24 08")  # house argument == player
    a.jump("0f 85", "restore")
    a.emit("c6 44 24 0c 01")  # full refund
    a.label("restore")
    a.emit("5a")
    a.label("original")
    a.code += original
    code = a.finish()
    return code + relative_jump(at + len(code), address + len(original))


def build_block(base):
    placements = []
    for name, (_address, _original, offset) in SITES.items():
        at = base + offset
        if name == "income":
            code = income_code(base, at)
        elif name == "harvest":
            code = harvest_code(base, at)
        elif name.startswith("repair"):
            code = repair_code(name, base, at)
        else:
            code = refund_code(base, at)
        placements.append((offset, code))
    return assemble(0x1000, placements, "经济")


class EconomyController:
    def __init__(self, proc):
        self.proc = proc
        self.hooks = HookSites(proc, "经济", SITES, build_block)
        self.enabled = set()
        self.income = 1.0

    @property
    def installed(self):
        return self.hooks.installed

    def _settings(self):
        return struct.pack("<fIII", self.income, "ore_infinite" in self.enabled,
                           "repair_free" in self.enabled, "sell_full" in self.enabled)

    def _active(self):
        active = set(self.enabled)
        if self.income != 1.0:
            active.add("ore_income")
        return active

    def _sync(self):
        wanted = {site for fid in self._active() for site in FEATURE_SITES[fid]}
        if wanted:
            self.hooks.prepare()
            settings = self._settings()
            if self.proc.read(self.hooks.base, len(settings)) != settings:
                if not self.proc.write(self.hooks.base, settings):
                    raise OSError("经济设置写入失败")
            self.hooks.apply(wanted)
        else:
            self.hooks.close()
            if self.hooks.base is not None:
                self.proc.write(self.hooks.base, struct.pack("<fIII", 1.0, 0, 0, 0))

    def set(self, fid, on):
        if fid not in ("ore_infinite", "repair_free", "sell_full"):
            raise ValueError(fid)
        previous = set(self.enabled)
        self.enabled = self.enabled | {fid} if on else self.enabled - {fid}
        try:
            self._sync()
        except Exception:
            self.enabled = previous
            raise

    def set_income(self, factor):
        factor = float(factor)
        if not math.isfinite(factor) or not 0.1 <= factor <= 100:
            raise ValueError("采矿收入倍率须在0.1到100之间")
        previous = self.income
        self.income = factor
        try:
            self._sync()
        except Exception:
            self.income = previous
            raise

    def close(self):
        previous = set(self.enabled), self.income
        self.enabled.clear()
        self.income = 1.0
        try:
            self._sync()
        except Exception:
            self.enabled, self.income = previous  # hooks still live: keep reporting them
            raise
