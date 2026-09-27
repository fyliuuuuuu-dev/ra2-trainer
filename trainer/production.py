"""Player-only production hooks for the stock RA2 1.006 executable.

Leave charging, suspension and delivery to FactoryClass::Update. Speed changes
only the timer result; instant mode advances to the final payable step.
"""
from .addresses import FRAME, PLAYER_PTR
from .executor import relative_jump
from .hooks import HookSites, assemble
from .operations import X86

SITES = {
    "speed": (0x4B9342, bytes.fromhex("8d7e288bcfe864abf9ff")),
    "queue": (0x4B94AE, bytes.fromhex("3b81e8000000")),
}
FEATURES = {"fast_build", "instant_build", "unlimited_queue"}


def speed_code(base, mode):
    a = X86()
    a.imm("a1", PLAYER_PTR)
    a.emit("39 46 68")
    a.jump("0f 85", "original")
    a.imm("a1", mode)
    a.emit("83 f8 02")
    a.jump("0f 84", "instant")
    a.emit("83 f8 01")
    a.jump("0f 85", "original")
    a.emit("83 7e 28 ff")  # paused timer must retain original semantics
    a.jump("0f 84", "original")
    a.emit("8b 46 30 85 c0")
    a.jump("0f 8e", "original")
    a.emit("31 d2 b9 0a 00 00 00 f7 f1 85 c0")  # max(1, delay / 10)
    a.jump("0f 85", "delay")
    a.emit("40")
    a.label("delay")
    a.emit("8b 56 28")
    a.imm("8b 0d", FRAME)
    a.emit("29 d1 29 c8 85 c0")
    a.jump("0f 8f", "ready")
    a.emit("31 c0")
    a.jump("e9", "ready")
    a.label("instant")
    # Stock progress step is 1, but preserve its final-step equation explicitly.
    a.emit("b8 36 00 00 00 2b 46 38 89 46 24 31 c0")
    a.label("ready")
    a.emit("8d 7e 28")
    a.jump("e9", "end")
    a.label("original")
    a.emit("8d 7e 28 8b cf")
    at = base + len(a.code)
    a.imm("e8", 0x453EB0 - at - 5)
    a.label("end")
    code = a.finish()
    return code + relative_jump(base + len(code), 0x4B934C)


def queue_code(base):
    a = X86()
    a.emit("52")
    a.imm("8b 15", PLAYER_PTR)
    a.emit("39 56 68 5a")
    a.jump("0f 85", "original")
    # Bounded at 999 to avoid unbounded queue allocations during long clicks.
    a.imm("3d", 999)
    a.jump("e9", "end")
    a.label("original")
    a.emit(SITES["queue"][1].hex())
    a.label("end")
    code = a.finish()
    return code + relative_jump(base + len(code), 0x4B94B4)


OFFSETS = {"speed": 0x100, "queue": 0x400}  # the speed mode word is at +0


def build_block(base):
    return assemble(0x1000, [(0x100, speed_code(base + 0x100, base)),
                             (0x400, queue_code(base + 0x400))], "建造")


class ProductionController:
    def __init__(self, proc):
        self.proc = proc
        self.enabled = set()
        self.hooks = HookSites(proc, "建造", {
            name: (va, original, OFFSETS[name]) for name, (va, original) in SITES.items()},
            build_block)

    @property
    def base(self):
        return self.hooks.base

    @property
    def installed(self):
        return self.hooks.installed

    def set(self, fid, on):
        if fid not in FEATURES:
            raise ValueError(fid)
        if on:
            self.hooks.prepare()
        desired = self.enabled | {fid} if on else self.enabled - {fid}
        if fid == "unlimited_queue":
            self.hooks.switch("queue", on)
        else:
            mode = 2 if "instant_build" in desired else int("fast_build" in desired)
            previous = self.proc.read_u32(self.base) if self.base is not None else 0
            if self.base is not None and not self.proc.write_u32(self.base, mode):
                raise OSError("无法设置建造速度")
            try:
                self.hooks.switch("speed", bool(mode))
            except Exception:
                if self.base is not None:
                    self.proc.write_u32(self.base, previous)
                raise
        self.enabled = desired

    def close(self):
        self.hooks.close()
        self.enabled.clear()
