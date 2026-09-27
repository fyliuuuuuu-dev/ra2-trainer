"""Unlimited player power applied inside the game's power recalculation.

The old per-frame drain clamp ran after dependent systems had already cached
the low-power state. Apply supply before those systems update, and explicitly
refresh radar on enable/disable. The AI retains its normal power economy.
"""
import struct

from .addresses import HOUSE_VT, PLAYER_PTR
from .executor import relative_jump
from .hooks import HookSites
from .units import player_house

HOOK = 0x4F2DDB
ORIGINAL = bytes.fromhex("8bcee85eccf5ff")


def build_power_hook(base):
    code = bytearray(b"\x9c\x50\xa1" + struct.pack("<I", PLAYER_PTR))
    code += b"\x39\xc6\x75\x0a"
    code += b"\xc7\x86\xd0\x52\x00\x00" + struct.pack("<I", 1000000)
    code += b"\x58\x9d\x8b\xce"
    at = base + len(code)
    code += b"\xe8" + struct.pack("<I", (0x44FA40 - at - 5) & 0xFFFFFFFF)
    code += relative_jump(base + len(code), HOOK + len(ORIGINAL))
    return bytes(code)


class PowerController:
    def __init__(self, proc, executor):
        self.proc, self.executor = proc, executor
        self.hooks = HookSites(proc, "电力重算", {"power": (HOOK, ORIGINAL, 0)},
                               build_power_hook)
        # Radar/power refresh waits for a game frame; the window runs it as a
        # background job (flush_refresh) instead of blocking the UI thread.
        self.pending_refresh = None

    @property
    def base(self):
        return self.hooks.base

    @property
    def installed(self):
        return bool(self.hooks.installed)

    def refresh(self):
        house = player_house(self.proc)
        if house and self.proc.read_u32(house) == HOUSE_VT:
            self.executor.call(0x4F2CC0, this=house)
            self.executor.call(0x4F2E50, this=house)

    def enable(self):
        if self.installed:
            return
        if self.proc.read(0x4E44F0, 14) != bytes.fromhex("8b86d452000085c00f9ec24a23c2"):
            raise RuntimeError("旧版无限电力仍在运行，请先关闭旧修改器")
        self.hooks.apply({"power"})
        self.pending_refresh = "已开启"

    def disable(self):
        if not self.installed:
            return
        gone = self.proc.read(HOOK, len(ORIGINAL)) is None
        self.hooks.close()
        self.pending_refresh = None if gone else "已关闭"

    def _refresh_after(self, state):
        # The hook state is already final here; say so instead of looking failed.
        try:
            self.refresh()
        except Exception as exc:
            raise RuntimeError(f"无限电力{state}，但电力和雷达状态刷新未完成（游戏暂停时会超时）：{exc}") from exc

    def flush_refresh(self):
        state, self.pending_refresh = self.pending_refresh, None
        if state:
            self._refresh_after(state)

    def close(self):
        self.disable()
        self.flush_refresh()
