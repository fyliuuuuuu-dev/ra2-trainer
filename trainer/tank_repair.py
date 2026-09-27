"""Repair eligible player ground vehicles at the game's repair-bay cadence.

This runs from UnitClass::AI on the simulation thread.  A private timer table
tracks each live instance by pointer and AbstractUniqueID, so a pause, a full
health interval, or a change of owner never accumulates retroactive repairs.
"""
import math

from .addresses import BUILDING_VT, FRAME, PLAYER_PTR, UNIT_VT
from .executor import relative_jump, release_orphan
from .hooks import entry_jump
from .operations import X86


AI_ENTRY = 0x6FB100
AI_ORIGINAL = bytes.fromhex("83ec20535556")
RULES_PTR = 0x839848
TABLE_SLOTS = 8192
SLOT_BYTES = 16  # unit pointer, AbstractUniqueID, woundedSince, lastSeenFrame
PROBE_LIMIT = 16


def native_repair_settings(proc):
    """Read the same Rules fields used by a normal vehicle repair bay."""
    rules = proc.read_u32(RULES_PTR)
    if not rules:
        raise RuntimeError("游戏规则尚未载入")
    step = proc.read_i32(rules + 0x1334)  # Rules.RepairStep
    rate = proc.read_f64(rules + 0x1350)  # Rules.URepairRate
    if step is None or rate is None or not math.isfinite(rate) or not 0 < rate < 10:
        raise RuntimeError("维修规则值无效")
    # Native repair bay compares elapsed whole frames with URepairRate * 900.
    # Stock RA2: 0.016 * 900 = 14.4, so the first repair is at frame 15.
    period = math.ceil(rate * 900)
    return max(1, step), max(1, period)


def repair_code(base, table, step, period):
    """UnitClass::AI trampoline; all health checks and writes are in one tick."""
    if not 1 <= step <= 1000000 or not 1 <= period <= 9000:
        raise ValueError("维修规则超出安全范围")
    a = X86()
    a.emit("9c 60")  # save EFLAGS and all registers; original this is [ESP+0x18]
    a.emit("8b 74 24 18")  # ESI = Unit*
    a.imm("81 3e", UNIT_VT)
    a.jump("0f 85", "done")
    a.emit("8b 5e 10")  # immutable AbstractUniqueID
    a.emit("89 f0 c1 e8 04 31 d8")  # hash pointer xor ID
    a.imm("25", TABLE_SLOTS - 1)
    a.emit("c1 e0 04")  # 16-byte slot
    a.imm("8d b8", table)  # EDI = table + hash * 16
    a.imm("b9", PROBE_LIMIT)
    a.label("probe")
    a.emit("8b 07 85 c0")
    a.jump("0f 84", "new_slot")
    a.emit("39 f0")
    a.jump("0f 85", "stale_check")
    a.emit("39 5f 04")
    a.jump("0f 84", "found")
    a.jump("e9", "new_slot")  # same address, new generation
    a.label("stale_check")
    a.imm("a1", FRAME)
    a.emit("2b 47 0c")
    a.emit("83 f8 3c")  # entries absent for >60 frames may be reclaimed
    a.jump("0f 87", "new_slot")
    a.emit("83 c7 10")
    a.imm("81 ff", table + TABLE_SLOTS * SLOT_BYTES)
    a.jump("0f 85", "slot_in_table")
    a.imm("bf", table)  # wrap the last bucket before the next probe
    a.label("slot_in_table")
    a.emit("49")
    a.jump("0f 85", "probe")
    a.jump("e9", "done")  # crowded table: skip, never repair wrong instance
    a.label("new_slot")
    a.emit("89 37 89 5f 04")
    a.imm("a1", FRAME)
    a.emit("89 47 08 89 47 0c")
    a.jump("e9", "done")  # first observed frame never repairs immediately

    a.label("found")
    a.imm("a1", PLAYER_PTR)
    a.emit("85 c0")
    a.jump("0f 84", "reset")
    a.emit("39 86 b4 01 00 00")  # current owner == current player
    a.jump("0f 85", "reset")
    a.emit("80 7e 76 00")  # !InLimbo
    a.jump("0f 85", "reset")
    a.emit("80 7e 7d 01")  # active
    a.jump("0f 85", "reset")
    a.emit("8b 46 6c 85 c0")  # living
    a.jump("0f 8e", "reset")
    a.emit("8b 9e ac 05 00 00 85 db")  # UnitType*
    a.jump("0f 84", "reset")
    a.emit("80 bb d8 0a 00 00 00")  # Type.Repairable
    a.jump("0f 84", "reset")
    a.emit("80 bb da 0a 00 00 00")  # !Type.Naval
    a.jump("0f 85", "reset")
    a.emit("83 bb a4 05 00 00 01")  # Type.SpeedType DWORD: track
    a.jump("0f 84", "land")
    a.emit("83 bb a4 05 00 00 02")  # wheel
    a.jump("0f 85", "reset")
    a.label("land")
    a.emit("8b 93 a0 00 00 00 85 d2")  # Type.Strength (+0xA0 needs disp32)
    a.jump("0f 8e", "reset")
    a.imm("81 fa", 1000000)
    a.jump("0f 87", "reset")  # avoid i32 overflow after adding a repair step
    a.emit("39 d0")  # current HP < max, including above-max safeguard
    a.jump("0f 8d", "reset")

    # While in radio contact with an active repair bay, let the native repair
    # process handle it.  The bay's UnitRepair flag is on BuildingType+0x1349.
    a.emit("8b 96 d0 00 00 00 85 d2")  # contact count
    a.jump("0f 8e", "timing")
    a.emit("83 fa 20")
    a.jump("0f 87", "reset")  # corrupt/outlier count: conservative skip
    a.emit("8b 86 cc 00 00 00 85 c0")  # contact data
    a.jump("0f 84", "reset")
    a.label("contacts")
    a.emit("8b 5c 90 fc 85 db")  # contact[EDX-1]
    a.jump("0f 84", "next_contact")
    a.imm("81 3b", BUILDING_VT)
    a.jump("0f 85", "next_contact")
    a.emit("80 7b 7d 01")  # active
    a.jump("0f 85", "next_contact")
    a.emit("80 7b 76 00")  # !InLimbo
    a.jump("0f 85", "next_contact")
    a.emit("8b 9b 18 04 00 00 85 db")  # BuildingType*
    a.jump("0f 84", "next_contact")
    a.emit("80 bb 49 13 00 00 00")  # Type.UnitRepair
    a.jump("0f 85", "reset")
    a.label("next_contact")
    a.emit("4a")
    a.jump("0f 85", "contacts")

    a.label("timing")
    a.imm("a1", FRAME)
    a.emit("89 c3 2b 5f 0c")  # current - last seen
    a.emit("85 db")
    a.jump("0f 84", "done")  # repeated AI call in the same game frame
    a.emit("83 fb 01")
    a.jump("0f 85", "reset")  # missed frame or frame-counter reset
    a.emit("89 47 0c")
    a.emit("2b 47 08")  # elapsed since this wounded interval began
    a.imm("3d", period)
    a.jump("0f 82", "done")
    a.imm("a1", FRAME)
    a.emit("89 47 08")  # next period starts now; no catch-up bursts
    a.emit("8b 46 6c")
    a.emit("8b 96 ac 05 00 00")  # re-read type and limit on this same tick
    a.emit("8b 92 a0 00 00 00")
    a.emit("89 d3 29 c3")  # max - current; no signed overflow
    a.imm("81 fb", step)
    a.jump("0f 86", "full_health")
    a.imm("05", step)
    a.jump("e9", "store_health")
    a.label("full_health")
    a.emit("89 d0")
    a.label("store_health")
    a.emit("89 46 6c 89 46 70")
    a.jump("e9", "done")
    a.label("reset")
    a.imm("a1", FRAME)
    a.emit("89 47 08 89 47 0c")
    a.label("done")
    a.emit("61 9d")
    a.emit(AI_ORIGINAL.hex())
    code = a.finish()
    return code + relative_jump(base + len(code), AI_ENTRY + len(AI_ORIGINAL))


def _table_of(proc, code_base, step, period):
    """Recover the timer table address baked into an existing trampoline."""
    marker = 0x13579BDF
    probe = repair_code(code_base, marker, step, period)
    at = probe.find(bytes.fromhex("8db8") + marker.to_bytes(4, "little"))
    return proc.read_u32(code_base + at + 2) if at >= 0 else None


class TankRepairController:
    def __init__(self, proc):
        self.proc = proc
        self.code_base = None
        self.table = None
        self.settings = None
        self.replacement = None
        self.retired = []  # detached blocks not yet confirmed idle

    @property
    def enabled(self):
        return self.replacement is not None

    def _expected_orphan(self, target):
        step, period = native_repair_settings(self.proc)
        table = _table_of(self.proc, target, step, period)
        return repair_code(target, table, step, period) if table else None

    def _free_idle(self):
        # The trampoline has no CALL, so once no thread is inside a detached
        # block nothing can return into it; the block and its table are free.
        keep = []
        for code_base, table in self.retired:
            try:
                idle = self.proc.code_idle(code_base, 0x1000)
            except Exception:
                idle = False
            if idle:
                self.proc.free(code_base)
                self.proc.free(table)
            else:
                keep.append((code_base, table))
        self.retired = keep

    def _block(self, step, period):
        """Return (code_base, table) ready for a fresh enable."""
        if self.code_base is not None:
            if self.settings == (step, period) and self.proc.code_idle(self.code_base, 0x1000):
                # Reuse: clear timers so a pause never turns into a repair burst.
                if not self.proc.write(self.table, bytes(TABLE_SLOTS * SLOT_BYTES)):
                    raise OSError("自动维修计时表初始化失败")
                return self.code_base, self.table
            self.retired.append((self.code_base, self.table))
            self.code_base = self.table = self.settings = None
        self._free_idle()
        code_base = self.proc.alloc(0x1000)
        table = self.proc.alloc(TABLE_SLOTS * SLOT_BYTES)
        if not code_base or not table:
            if code_base:
                self.proc.free(code_base)
            if table:
                self.proc.free(table)
            raise OSError("无法分配自动维修计时表")
        try:
            code = repair_code(code_base, table, step, period)
            if len(code) > 0x1000:
                raise ValueError("自动维修补丁过长")
            if not self.proc.write(table, bytes(TABLE_SLOTS * SLOT_BYTES)):
                raise OSError("自动维修计时表初始化失败")
            if not self.proc.patch(code_base, code):
                raise OSError("自动维修补丁写入失败")
        except Exception:
            self.proc.free(code_base)  # never reachable: the entry is untouched
            self.proc.free(table)
            raise
        self.code_base, self.table, self.settings = code_base, table, (step, period)
        return code_base, table

    def enable(self):
        if self.enabled:
            if self.proc.read(AI_ENTRY, len(AI_ORIGINAL)) != self.replacement:
                raise RuntimeError("自动维修入口已被外部修改")
            return
        if not self.proc.is32:
            raise RuntimeError("自动维修代码与游戏版本不匹配")
        if self.code_base is None:
            release_orphan(self.proc, AI_ENTRY, AI_ORIGINAL, self._expected_orphan)
        if self.proc.read(AI_ENTRY, len(AI_ORIGINAL)) != AI_ORIGINAL:
            raise RuntimeError("自动维修代码与游戏版本不匹配")
        step, period = native_repair_settings(self.proc)
        code_base, _table = self._block(step, period)
        replacement = entry_jump(AI_ENTRY, code_base, len(AI_ORIGINAL))
        # patch_quiescent restores the entry itself when its write fails, so
        # the block stays owned and reusable either way.
        self.proc.patch_quiescent(AI_ENTRY, AI_ORIGINAL, replacement)
        self.replacement = replacement

    def disable(self):
        if not self.enabled:
            return
        current = self.proc.read(AI_ENTRY, len(AI_ORIGINAL))
        if current == self.replacement:
            self.proc.patch_quiescent(AI_ENTRY, self.replacement, AI_ORIGINAL)
        elif current not in (AI_ORIGINAL, None):
            raise RuntimeError("自动维修入口已被外部修改，未覆盖")
        self.replacement = None

    def close(self):
        self.disable()
        if self.code_base is not None:
            self.retired.append((self.code_base, self.table))
            self.code_base = self.table = self.settings = None
        self._free_idle()
