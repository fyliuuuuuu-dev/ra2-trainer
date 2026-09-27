"""Player-only cloak and disguise sensing for stock RA2 1.006."""
from .addresses import PLAYER_PTR
from .executor import relative_jump
from .hooks import HookSites, assemble
from .operations import X86


SITES = {
    0x47C2E0: bytes.fromhex("8b54240433c0"),  # Cell.Sensors_InclHouse
    0x47C300: bytes.fromhex("8b54240433c0"),  # Cell.DisguiseSensors_InclHouse
}


def sensor_code(base, entry, original):
    a = X86()
    a.emit("9c 50")  # save flags and EAX; ECX is the cell
    a.imm("a1", PLAYER_PTR)
    a.emit("85 c0")
    a.jump("0f 84", "original")
    a.emit("8b 40 30")  # player's House.ArrayIndex
    a.emit("3b 44 24 0c")  # index argument, with saved EAX and EFLAGS
    a.jump("0f 85", "original")
    a.emit("58 9d b8 01 00 00 00 c2 04 00")
    a.label("original")
    a.emit("58 9d")
    a.code += original
    code = a.finish()
    return code + relative_jump(base + len(code), entry + len(original))


def build_block(base):
    return assemble(0x1000, [((i + 1) * 0x100, sensor_code(base + (i + 1) * 0x100, address, original))
                             for i, (address, original) in enumerate(SITES.items())], "反隐身")


class AntiStealthController:
    def __init__(self, proc):
        self.hooks = HookSites(proc, "反隐身", {
            address: (address, original, (i + 1) * 0x100)
            for i, (address, original) in enumerate(SITES.items())}, build_block)

    @property
    def installed(self):
        return self.hooks.installed

    def set(self, on):
        self.hooks.apply(SITES if on else ())

    def close(self):
        self.hooks.close()
