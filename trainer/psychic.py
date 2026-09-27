"""Map-wide psychic detection: show enemy units' action lines like a Psychic Sensor.

Each render frame the tactical view walks TechnoClass::Array (0x6A4F95). For
objects the player does not control it calls 0x4386F0, which returns true
only when the owner is not allied with the player and the object or its
target lies inside an active player building's PsychicDetectionRadius
(BuildingType+0x1390); then 0x4CAB90 draws the target/destination lines.

The hook answers true for every non-allied vehicle, infantry or aircraft, so
the native line drawing runs as if a sensor covered the whole map. Allies,
buildings (0x4CAB90 reads foot-only fields) and a missing player keep the
original function.
"""
from .addresses import AIRCRAFT_VT, INFANTRY_VT, PLAYER_PTR, TECHNO_FIELD, UNIT_VT
from .executor import relative_jump
from .hooks import HookSites, assemble
from .operations import X86

DETECT_ENTRY = 0x4386F0
DETECT_ORIGINAL = bytes.fromhex("558bec83e4f8")  # push ebp; mov ebp,esp; and esp,-8
IS_ALLIED = 0x4E5540  # HouseClass::IsAlliedWith(HouseClass*), thiscall, ret 4
CODE_OFFSET = 0x100


def detect_code(base):
    """Runs at the function entry: ECX = TechnoClass*, return address on the stack."""
    a = X86()
    a.imm("a1", PLAYER_PTR)
    a.emit("85 c0")
    a.jump("0f 84", "original")
    a.emit("8b 11")  # EDX = vtable
    for vt in (UNIT_VT, INFANTRY_VT):
        a.imm("81 fa", vt)
        a.jump("0f 84", "foot")
    a.imm("81 fa", AIRCRAFT_VT)
    a.jump("0f 85", "original")
    a.label("foot")
    a.emit("8b 91")
    a.code += TECHNO_FIELD["Owner"].to_bytes(4, "little")  # EDX = owner
    a.emit("85 d2")
    a.jump("0f 84", "original")
    a.emit("39 c2")
    a.jump("0f 84", "original")  # the player's own units never reach here
    a.emit("51 52 89 c1")  # keep this; push owner; ECX = player
    a.imm("b8", IS_ALLIED)
    a.emit("ff d0 59")  # player->IsAlliedWith(owner); restore this
    a.emit("84 c0")
    a.jump("0f 85", "original")  # allies: native answer (false)
    a.emit("b0 01 c3")  # detected
    a.label("original")
    a.code += DETECT_ORIGINAL
    code = a.finish()
    at = base + CODE_OFFSET
    return code + relative_jump(at + len(code), DETECT_ENTRY + len(DETECT_ORIGINAL))


def build_block(base):
    return assemble(0x1000, [(CODE_OFFSET, detect_code(base))], "心灵探测")


class PsychicScanController:
    def __init__(self, proc):
        self.hooks = HookSites(proc, "心灵探测",
                               {"detect": (DETECT_ENTRY, DETECT_ORIGINAL, CODE_OFFSET)},
                               build_block)

    @property
    def installed(self):
        return self.hooks.installed

    def set(self, on):
        self.hooks.apply({"detect"} if on else ())

    def close(self):
        self.hooks.close()
