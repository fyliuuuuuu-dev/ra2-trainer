"""Block ordinary positive damage to player-owned technos.

Engine-forced damage (IgnoreDefenses), healing, sale/removal and other houses
keep their original behavior. Every entry is signature-checked before install.
"""
from .addresses import PLAYER_PTR
from .executor import relative_jump
from .hooks import HookSites, assemble
from .operations import X86

SITES = {
    0x6FCA30: bytes.fromhex("83ec285355"),  # vehicle
    0x4FFB70: bytes.fromhex("83ec3c5355"),  # infantry
    0x43EE70: bytes.fromhex("81ec8c000000"),  # building
    0x415E70: bytes.fromhex("8b44241883ec18"),  # aircraft
}


def damage_code(base, entry, original):
    a = X86()
    a.emit("9c 50")
    a.imm("a1", PLAYER_PTR)
    a.emit("85 c0")
    a.jump("0f 84", "original")
    a.emit("39 81 b4 01 00 00")
    a.jump("0f 85", "original")
    a.emit("80 7c 24 1c 00")  # arg 5, shifted by pushfd/push eax
    a.jump("0f 85", "original")
    a.emit("8b 44 24 0c 85 c0")  # int* damage
    a.jump("0f 84", "original")
    a.emit("83 38 00")
    a.jump("0f 8e", "original")
    a.emit("c7 00 00 00 00 00 58 9d 31 c0 c2 18 00")
    a.label("original")
    a.emit("58 9d")
    a.emit(original.hex())
    code = a.finish()
    return code + relative_jump(base + len(code), entry + len(original))


def build_block(base):
    return assemble(0x1000, [(i * 0x100, damage_code(base + i * 0x100, entry, original))
                             for i, (entry, original) in enumerate(SITES.items())], "防护")


class ProtectionController:
    def __init__(self, proc):
        self.hooks = HookSites(proc, "防护", {
            entry: (entry, original, i * 0x100)
            for i, (entry, original) in enumerate(SITES.items())}, build_block)

    @property
    def owned(self):
        return self.hooks.installed

    @property
    def installed(self):
        return len(self.hooks.installed) == len(SITES)

    def enable(self):
        self.hooks.apply(SITES)

    def disable(self):
        self.hooks.close()

    close = disable
