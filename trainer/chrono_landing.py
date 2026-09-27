"""Shorten only player Chrono locomotor landing recovery on RA2 1.006."""
from .addresses import INFANTRY_VT, PLAYER_PTR
from .executor import relative_jump
from .hooks import HookSites
from .operations import X86


LANDING_SITE = 0x6E1095
ORIGINAL = bytes.fromhex("8b4e08c6810502000001")


def landing_code(base):
    """Keep the engine's destination and fade-in flow; reduce its wait to 1."""
    a = X86()
    a.emit("9c 50 51")  # flags, EAX, ECX; ESI is Chrono locomotor
    a.imm("81 3e", 0x7AD1A8)  # exact Chrono locomotor interface
    a.jump("0f 85", "original")
    a.emit("8b 46 08 85 c0")  # Locomotor.Owner (Infantry*)
    a.jump("0f 84", "original")
    a.imm("81 38", INFANTRY_VT)
    a.jump("0f 85", "original")
    a.emit("8b 0d")
    a.code += PLAYER_PTR.to_bytes(4, "little")
    a.emit("85 c9")
    a.jump("0f 84", "original")
    a.emit("39 88 b4 01 00 00")  # Infantry.Owner == Player
    a.jump("0f 85", "original")
    a.emit("83 78 6c 00")  # living
    a.jump("0f 8e", "original")
    a.emit("80 78 7d 01")  # active
    a.jump("0f 85", "original")
    a.emit("83 7e 40 01")  # already 0/1 frames: leave intact
    a.jump("0f 8e", "original")
    a.emit("c7 46 40 01 00 00 00")  # Chrono locomotor timer duration
    a.label("original")
    a.emit("59 58 9d")
    a.emit(ORIGINAL.hex())
    code = a.finish()
    return code + relative_jump(base + len(code), LANDING_SITE + len(ORIGINAL))


class ChronoLandingController:
    def __init__(self, proc):
        self.proc = proc
        self.hooks = HookSites(proc, "时空兵落地", {"landing": (LANDING_SITE, ORIGINAL, 0)},
                               landing_code)

    @property
    def enabled(self):
        return bool(self.hooks.installed)

    def enable(self):
        if not self.proc.is32:
            raise RuntimeError("时空兵落地代码与游戏版本不匹配")
        self.hooks.apply({"landing"})

    def disable(self):
        self.hooks.close()

    close = disable
