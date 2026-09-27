"""Player-only ground/air targeting hooks for stock RA2 1.006."""
from .addresses import PLAYER_PTR
from .executor import relative_jump
from .hooks import HookSites, assemble
from .operations import X86


SITES = {
    "fire_air": (0x6C950A, bytes.fromhex("8a8174020000")),
    "fire_ground": (0x6C95B3, bytes.fromhex("8a8175020000")),
    "bullet_air": (0x461D95, bytes.fromhex("8a8874020000")),
    "auto_target": (0x733A60, bytes.fromhex("8b89a0000000")),
}
TARGET_CALLERS = (0x442676, 0x4426A6, 0x5052D0, 0x5052F6,
                  0x706A6A, 0x706A93, 0x706AB9)


def target_code(name, base):
    address, original = SITES[name]
    a = X86()
    a.emit("9c 52 50")  # EFLAGS, EDX, EAX
    a.imm("a1", PLAYER_PTR)
    a.emit("85 c0")
    a.jump("0f 84", "original")
    a.emit("85 f6")  # ESI = shooter (or Bullet)
    a.jump("0f 84", "original")
    if name == "auto_target":
        for caller in TARGET_CALLERS:
            a.emit("81 7c 24 0c")
            a.code += caller.to_bytes(4, "little")
            a.jump("0f 84", "caller_ok")
        a.jump("e9", "original")
        a.label("caller_ok")
    if name == "bullet_air":
        a.emit("8b 96 9c 00 00 00 85 d2")  # bullet source can be null
        a.jump("0f 84", "original")
        a.emit("39 82 b4 01 00 00")
    else:
        a.emit("39 86 b4 01 00 00")
    a.jump("0f 85", "original")
    a.emit("58 5a 9d")
    if name == "bullet_air":
        a.emit("b1 01")  # force CL; preserve EAX from the original path
    elif name == "auto_target":
        a.emit("b8 bc 00 00 00 c3")  # AA|AG target mask, only known shooter callers
    else:
        a.emit("b0 01")  # force AL
    if name != "auto_target":
        at = base + len(a.code)
        a.code += relative_jump(at, address + len(original))
    a.label("original")
    a.emit("58 5a 9d")
    a.code += original
    code = a.finish()
    return code + relative_jump(base + len(code), address + len(original))


def build_block(base):
    return assemble(0x1000, [((i + 1) * 0x200, target_code(name, base + (i + 1) * 0x200))
                             for i, name in enumerate(SITES)], "全目标攻击")


class AllTargetController:
    def __init__(self, proc):
        self.hooks = HookSites(proc, "全目标攻击", {
            name: (address, original, (i + 1) * 0x200)
            for i, (name, (address, original)) in enumerate(SITES.items())}, build_block)

    @property
    def installed(self):
        return self.hooks.installed

    def set(self, on):
        self.hooks.apply(SITES if on else ())

    def close(self):
        self.hooks.close()
