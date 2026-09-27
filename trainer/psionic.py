"""Player-only immunity to mind control (Yuri).

Mind control goes through CaptureManagerClass (ECX = the controller's
manager, controller at +0x2C):
    0x467F80 CanCapture(target)  -- targeting (called from 0x6C988E)
    0x467FF0 Capture(target)     -- warhead hit (called from 0x462335)
and TechnoClass::ReceiveDamage 0x6CDC40 ignores a MindControl warhead
(+0x164) hitting an immune object (ESI = the damaged object). All three read TechnoType.ImmuneToPsionics
(+0xAFD); the hooks make the player's own objects read as immune there, so
Yuri neither picks them as targets nor captures them. Objects already under
another house's control are not released.
"""
import struct

from .addresses import PLAYER_PTR
from .executor import relative_jump
from .hooks import HookSites, assemble
from .operations import X86

OWNER = 0x1B4
# name: (address, original, stub offset, target register ModRM for cmp [reg+disp32], edx)
SITES = {
    "can_capture": (0x467FBA, bytes.fromhex("8a88fd0a0000"), 0x100, "39 96"),  # target ESI
    "capture": (0x468049, bytes.fromhex("3898fd0a0000"), 0x200, "39 97"),  # target EDI
    "evaluate": (0x6CDEE1, bytes.fromhex("8a88fd0a0000"), 0x300, "39 96"),  # target ESI
}


def load_code(name, at):
    """`mov cl,[eax+0xAFD]`, then CL=1 when the target belongs to the player."""
    address, original, _offset, owner_cmp = SITES[name]
    back = address + len(original)
    a = X86()
    a.code += original
    a.emit("84 c9")
    a.jump("0f 85", "back")
    a.emit("52")
    a.imm("8b 15", PLAYER_PTR)
    a.emit("85 d2")
    a.jump("0f 84", "restore")
    a.emit(owner_cmp)
    a.code += struct.pack("<I", OWNER)
    a.jump("0f 85", "restore")
    a.emit("b1 01")
    a.label("restore")
    a.emit("5a")
    a.label("back")
    code = a.finish()
    return code + relative_jump(at + len(code), back)


def compare_code(at):
    """`cmp [eax+0xAFD], bl` (BL = 0): leave ZF clear when the target is the player's."""
    address, original, _offset, owner_cmp = SITES["capture"]
    back = address + len(original)
    a = X86()
    a.code += original
    a.jump("0f 85", "back")  # natively immune
    a.emit("52")
    a.imm("8b 15", PLAYER_PTR)
    a.emit("85 d2")
    a.jump("0f 84", "native")
    a.emit(owner_cmp)
    a.code += struct.pack("<I", OWNER)
    a.jump("0f 85", "native")
    a.emit("5a 85 e4")  # player's: ZF = 0, same as an immune type
    a.jump("e9", "back")
    a.label("native")
    a.emit("5a")
    a.code += original  # restore the original flags
    a.label("back")
    code = a.finish()
    return code + relative_jump(at + len(code), back)


def build_block(base):
    placements = []
    for name, (_address, _original, offset, _cmp) in SITES.items():
        at = base + offset
        code = compare_code(at) if name == "capture" else load_code(name, at)
        placements.append((offset, code))
    return assemble(0x1000, placements, "反心灵控制")


class PsionicShieldController:
    def __init__(self, proc):
        self.hooks = HookSites(proc, "反心灵控制", {
            name: (address, original, offset)
            for name, (address, original, offset, _cmp) in SITES.items()}, build_block)

    @property
    def installed(self):
        return self.hooks.installed

    def set(self, on):
        self.hooks.apply(SITES if on else ())

    def close(self):
        self.hooks.close()
