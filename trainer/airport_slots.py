"""Player airport pad multiplier with real native radio-contact capacity.

RA2 1.006 uses Building.Contact slots for parked aircraft and House+218 for
production capacity. Both must change together. The remote code remains
resident at factor 1 so aircraft already parked above slot 3 can depart,
refuel and reuse their original four pad coordinates safely.
"""
import struct

from .addresses import BUILDING_VT, PLAYER_PTR
from .executor import relative_jump
from .hooks import HookSites
from .operations import X86


MAGIC = b"RA2AIRPAD1\0"
BLOCK_SIZE = 0x4000
FACTOR_OFFSET = 0x20
TYPE_HELPER = 0x100
LIMIT_HELPER = 0x180
RADIO_HELPER = 0x200
SITE_OFFSET = 0x500
SITE_STRIDE = 0x180
RECONCILE_OFFSET = 0x3000

# The original sequences cover whole instructions in local RA2 1.006.
SITES = {
    "built": (0x442ADD, "8b8900140000", "life_built"),
    "removed": (0x44214D, "8b9100140000", "life_removed"),
    "transfer_out": (0x444D24, "8b8800140000", "life_transfer_out"),
    "transfer_in": (0x4451BC, "8b8900140000", "life_transfer_in"),
    "dock_coords": (0x4441EB, "8b8e180400003b8100140000", "dock"),
    "receive_new": (0x6369FF, "8b96d0000000", "radio_esi"),
    "has_free": (0x636EA0, "8b91d0000000", "radio_ecx"),
    "can_request": (0x636ED0, "568bb1d0000000", "request"),
    "send_candidate": (0x636AE7, "83390075028bd8", "candidate"),
    "send_full": (0x636AFA, "83fbff7517", "full"),
}


def _call(a, base, target):
    a.imm("e8", target - (base + len(a.code) + 5))


def type_helper_code():
    """ECX=Building; EAX=1 for exactly GAAIRC/AMRADR, else 0."""
    a = X86()
    a.emit("85 c9")
    a.jump("0f 84", "no")
    a.imm("81 39", BUILDING_VT)
    a.jump("0f 85", "no")
    a.emit("8b 81 18 04 00 00 85 c0")
    a.jump("0f 84", "no")
    a.imm("81 78 24", int.from_bytes(b"GAAI", "little"))
    a.jump("0f 85", "second")
    a.emit("66 81 78 28 52 43")
    a.jump("0f 85", "second")
    a.emit("80 78 2a 00")
    a.jump("0f 84", "yes")
    a.label("second")
    a.imm("81 78 24", int.from_bytes(b"AMRA", "little"))
    a.jump("0f 85", "no")
    a.emit("66 81 78 28 44 52")
    a.jump("0f 85", "no")
    a.emit("80 78 2a 00")
    a.jump("0f 85", "no")
    a.label("yes")
    a.emit("b8 01 00 00 00 c3")
    a.label("no")
    a.emit("31 c0 c3")
    return a.finish()


def limit_helper_code(base, type_addr, factor_addr):
    """ECX=Building, EDX=capacity House; EAX=count or -1 if non-airport."""
    a = X86()
    a.emit("52")
    _call(a, base, type_addr)
    a.emit("5a 85 c0")
    a.jump("0f 84", "not_airport")
    a.emit("b8 04 00 00 00")
    a.emit("3b 15")
    a.code += PLAYER_PTR.to_bytes(4, "little")  # cmp edx,[Player]
    a.jump("0f 85", "done")
    a.imm("a1", factor_addr)
    a.emit("c1 e0 02")
    a.label("done")
    a.emit("c3")
    a.label("not_airport")
    a.emit("b8 ff ff ff ff c3")
    return a.finish()


def radio_helper_code(base, limit_addr):
    """ECX=Building; EAX=min(allocated, allowed new slots) or -1."""
    a = X86()
    a.emit("51")
    _call(a, base, base - RADIO_HELPER + TYPE_HELPER)
    a.emit("59 85 c0")
    a.jump("0f 84", "not_airport")
    a.emit("8b 91 b4 01 00 00")  # owner; helper preserves ECX
    _call(a, base, limit_addr)
    a.emit("83 f8 ff")
    a.jump("0f 84", "done")
    a.emit("3b 81 d0 00 00 00")
    a.jump("0f 8e", "done")
    a.emit("8b 81 d0 00 00 00")
    a.label("done")
    a.emit("c3")
    a.label("not_airport")
    a.emit("b8 ff ff ff ff c3")
    return a.finish()


def _finish_site(a, base, address, original):
    code = a.finish()
    return code + relative_jump(base + len(code), address + len(original))


def site_code(name, base, type_addr, limit_addr, radio_addr):
    address, raw, kind = SITES[name]
    original = bytes.fromhex(raw)
    a = X86()
    if kind.startswith("life_"):
        a.code += original
        a.emit("9c 60")
        # Saved PUSHAD slots: EDI0,ESI4,EBP8,EBX10,EDX14,ECX18,EAX1C.
        building_slot = 0x08 if kind == "life_built" else 0x04
        house_slot = 0x10 if kind == "life_transfer_out" else 0x1C
        output_slot = 0x14 if kind == "life_removed" else 0x18
        a.emit(f"8b 4c 24 {building_slot:02x}")
        a.emit(f"8b 54 24 {house_slot:02x}")
        _call(a, base, limit_addr)
        a.emit("83 f8 ff")
        a.jump("0f 84", "restore")
        a.emit(f"8b 74 24 {building_slot:02x}")
        if kind in ("life_built", "life_transfer_in"):
            a.emit("89 c3")  # EBX=required contact slots
            a.emit("39 9e d0 00 00 00")  # cmp [building+D0],EBX
            a.jump("0f 8d", "grown")
            a.emit("53 89 f1")
            _call(a, base, 0x636F40)
            a.label("grown")
            a.emit("89 d8")
        a.emit("3b 86 d0 00 00 00")  # cap at actual allocated contacts
        a.jump("0f 8e", "capacity_known")
        a.emit("8b 86 d0 00 00 00")
        a.label("capacity_known")
        a.emit(f"89 44 24 {output_slot:02x}")
        a.label("restore")
        a.emit("61 9d")
        return _finish_site(a, base, address, original)
    if kind == "dock":
        a.emit("9c 60 8b 4c 24 04")  # ESI=Building
        _call(a, base, type_addr)
        a.emit("85 c0")
        a.jump("0f 84", "restore")
        a.emit("83 7c 24 1c 04")  # original nonnegative slot >=4
        a.jump("0f 8c", "restore")
        a.emit("83 64 24 1c 03")  # saved EAX slot %= 4
        a.label("restore")
        a.emit("61 9d")
        a.code += original  # mov ECX Type; cmp slot,[Type+1400]
        return _finish_site(a, base, address, original)
    if kind.startswith("radio_"):
        a.code += original
        a.emit("9c 60")
        source_slot = 0x04 if kind == "radio_esi" else 0x18
        a.emit(f"8b 4c 24 {source_slot:02x}")
        _call(a, base, radio_addr)
        a.emit("83 f8 ff")
        a.jump("0f 84", "restore")
        a.emit("89 44 24 14")  # EDX limit
        a.label("restore")
        a.emit("61 9d")
        return _finish_site(a, base, address, original)
    if kind == "request":
        a.emit("9c 60 8b 4c 24 18")  # original ECX Building
        _call(a, base, radio_addr)
        a.emit("83 f8 ff")
        a.jump("0f 84", "original")
        a.emit("89 c3")  # EBX=allowed new slots
        a.emit("8b 74 24 18")  # ESI Building
        a.emit("8b be cc 00 00 00")  # EDI slots data
        a.emit("8b 8e d0 00 00 00")  # ECX allocated count
        a.emit("8b 54 24 28")  # EDX requested object (original [esp+4])
        a.emit("85 d2")
        a.jump("0f 84", "find_empty")
        a.emit("31 c0")
        a.label("find_existing")
        a.emit("39 c8")
        a.jump("0f 8d", "find_empty")
        a.emit("39 14 87")  # cmp [EDI+EAX*4],EDX
        a.jump("0f 84", "yes")
        a.emit("40")
        a.jump("e9", "find_existing")
        a.label("find_empty")
        a.emit("31 c0")
        a.label("empty_loop")
        a.emit("39 d8")  # compare index with allowed cap
        a.jump("0f 8d", "no")
        a.emit("83 3c 87 00")
        a.jump("0f 84", "yes")
        a.emit("40")
        a.jump("e9", "empty_loop")
        a.label("yes")
        a.emit("61 9d b0 01 c2 04 00")
        a.label("no")
        a.emit("61 9d 30 c0 c2 04 00")
        a.label("original")
        a.emit("61 9d")
        a.code += original
        return _finish_site(a, base, address, original)
    if kind == "candidate":
        a.emit("9c 60 8b 4c 24 04")  # ESI Building
        _call(a, base, radio_addr)
        a.emit("83 f8 ff")
        a.jump("0f 84", "native")
        a.emit("39 44 24 1c")  # cmp [saved EAX index],EAX limit
        a.jump("0f 8d", "skip")
        a.label("native")
        a.emit("61 9d 83 39 00")  # cmp dword [ECX],0
        a.jump("0f 85", "resume")
        a.emit("89 c3")  # mov EBX,EAX
        a.jump("e9", "resume")
        a.label("skip")
        a.emit("61 9d")
        a.label("resume")
        code = a.finish()
        return code + relative_jump(base + len(code), 0x636AEE)
    raise ValueError(name)


def full_site_code(base, radio_addr, factor_addr):
    """Preserve native 4-slot kick behavior, block kick when expanded/shrunk."""
    address, raw, _kind = SITES["send_full"]
    a = X86()
    a.emit("9c 60 8b 4c 24 04")  # ESI Building
    _call(a, base, radio_addr)
    a.emit("83 f8 ff")
    a.jump("0f 84", "native")
    a.emit("8b 54 24 04")
    a.emit("83 ba d0 00 00 00 04")
    a.jump("0f 8f", "bounded")
    a.imm("83 3d", factor_addr)
    a.emit("01")  # cmp factor,1
    a.jump("0f 8e", "native")
    a.emit("8b 8a b4 01 00 00")  # Building.Owner
    a.emit("3b 0d")
    a.code += PLAYER_PTR.to_bytes(4, "little")
    a.jump("0f 85", "native")
    a.label("bounded")
    a.emit("83 7c 24 10 ff")  # saved EBX candidate==-1?
    a.jump("0f 85", "native")
    a.emit("61 9d")
    a.code += relative_jump(base + len(a.code), 0x636B49)
    a.label("native")
    a.emit("61 9d 83 fb ff")
    a.jump("0f 85", "native_has_slot")
    a.code += relative_jump(base + len(a.code), 0x636AFF)
    a.label("native_has_slot")
    a.code += relative_jump(base + len(a.code), 0x636B16)
    return a.finish()


def block_bytes(base):
    blob = bytearray(BLOCK_SIZE)
    blob[:len(MAGIC)] = MAGIC
    struct.pack_into("<I", blob, FACTOR_OFFSET, 1)
    helpers = ((TYPE_HELPER, type_helper_code()),
               (LIMIT_HELPER, limit_helper_code(base + LIMIT_HELPER,
                                                base + TYPE_HELPER,
                                                base + FACTOR_OFFSET)),
               (RADIO_HELPER, radio_helper_code(base + RADIO_HELPER,
                                                base + LIMIT_HELPER)))
    for off, code in helpers:
        if len(code) > 0x80:
            raise ValueError("机场辅助代码过长")
        blob[off:off + len(code)] = code
    for i, name in enumerate(SITES):
        off = SITE_OFFSET + i * SITE_STRIDE
        at = base + off
        code = (full_site_code(at, base + RADIO_HELPER, base + FACTOR_OFFSET)
                if name == "send_full" else
                site_code(name, at, base + TYPE_HELPER,
                          base + LIMIT_HELPER, base + RADIO_HELPER))
        if len(code) > SITE_STRIDE:
            raise ValueError(f"机场代码过长：{name}")
        blob[off:off + len(code)] = code
    return bytes(blob)


def reconcile_code(base, expected_house, new_factor, type_addr, factor_addr):
    """One game tick: grow first, then recompute all native Helipad pads."""
    if not 1 <= new_factor <= 16:
        raise ValueError("机场机位倍率须为1～16")
    target = new_factor * 4
    a = X86()
    a.emit("53 55 56 57 83 ec 08")  # callee-saved GPRs, chosen/status locals
    a.imm("c7 04 24", new_factor)  # chosen factor
    a.emit("c7 44 24 04 01 00 00 00")  # success flag
    a.imm("a1", PLAYER_PTR)
    a.imm("3d", expected_house)
    a.jump("0f 85", "hard_fail")
    a.emit("85 c0")
    a.jump("0f 84", "hard_fail")
    a.emit("89 c7 8b 77 6c 8b 9f 78 00 00 00")  # Player Buildings
    a.emit("81 fb 00 04 00 00")  # count <=1024
    a.jump("0f 87", "hard_fail")
    a.emit("85 db")
    a.jump("0f 84", "grow_loop")
    a.emit("85 f6")
    a.jump("0f 84", "hard_fail")
    a.label("grow_loop")
    a.emit("85 db")
    a.jump("0f 8e", "recount_start")
    a.emit("8b 0e 83 c6 04 4b 85 c9")
    a.jump("0f 84", "grow_loop")
    a.imm("81 39", BUILDING_VT)
    a.jump("0f 85", "grow_loop")
    a.emit("39 b9 b4 01 00 00")  # Owner == player
    a.jump("0f 85", "grow_loop")
    a.emit("80 b9 b4 05 00 00 00")  # already counted in House pads
    a.jump("0f 84", "grow_loop")
    a.emit("51")
    _call(a, base, type_addr)
    a.emit("59 85 c0")
    a.jump("0f 84", "grow_loop")
    a.imm("81 b9 d0 00 00 00", target)
    a.jump("0f 8d", "grow_loop")
    a.emit("51")
    a.imm("68", target)
    a.emit("8b 4c 24 04")
    _call(a, base, 0x636F40)
    a.emit("59")  # original Building*
    a.imm("81 b9 d0 00 00 00", target)
    a.jump("0f 8d", "grow_loop")
    # Some earlier grows may have succeeded. Recount the old-factor capacity
    # from the final allocated lengths so later death/transfer subtraction
    # remains exact even on this partial allocation failure.
    a.imm("a1", factor_addr)
    a.emit("89 04 24 c7 44 24 04 00 00 00 00")
    a.label("recount_start")
    a.emit("8b 77 6c 8b 9f 78 00 00 00 31 d2")  # EDX total pads
    a.label("recount_loop")
    a.emit("85 db")
    a.jump("0f 8e", "commit")
    a.emit("8b 0e 83 c6 04 4b 85 c9")
    a.jump("0f 84", "recount_loop")
    a.imm("81 39", BUILDING_VT)
    a.jump("0f 85", "recount_loop")
    a.emit("39 b9 b4 01 00 00")
    a.jump("0f 85", "recount_loop")
    a.emit("80 b9 b4 05 00 00 00")
    a.jump("0f 84", "recount_loop")
    a.emit("8b a9 18 04 00 00 85 ed")  # EBP=Type
    a.jump("0f 84", "recount_loop")
    a.emit("80 bd 65 13 00 00 00")  # Type.Helipad
    a.jump("0f 84", "recount_loop")
    a.emit("51")
    _call(a, base, type_addr)
    a.emit("59 85 c0")
    a.jump("0f 84", "other_pad")
    a.emit("8b 04 24 c1 e0 02")  # chosen factor * 4
    a.emit("3b 81 d0 00 00 00")
    a.jump("0f 8e", "add_pad")
    a.emit("8b 81 d0 00 00 00")  # cap to actual contact allocation
    a.jump("e9", "add_pad")
    a.label("other_pad")
    a.emit("8b 85 00 14 00 00")  # other Helipad Type.NumberOfDocks
    a.label("add_pad")
    a.emit("01 c2")
    a.jump("e9", "recount_loop")
    a.label("commit")
    a.emit("89 97 18 02 00 00")  # House+218 PadAircraft
    a.emit("83 7c 24 04 00")
    a.jump("0f 84", "return_status")
    a.emit("8b 04 24")
    a.imm("a3", factor_addr)
    a.label("return_status")
    a.emit("8b 44 24 04")
    a.jump("e9", "end")
    a.label("hard_fail")
    a.emit("31 c0")
    a.label("end")
    a.emit("83 c4 08 5f 5e 5d 5b c3")
    return a.finish()


class AirportSlotsController:
    def __init__(self, proc, executor):
        self.proc = proc
        self.executor = executor
        # Resident by design: an old block is adopted, never released.
        self.hooks = HookSites(proc, "机场机位", {
            name: (address, bytes.fromhex(raw), SITE_OFFSET + i * SITE_STRIDE)
            for i, (name, (address, raw, _kind)) in enumerate(SITES.items())},
            block_bytes, size=BLOCK_SIZE, release=False)
        self.factor = 1
        self._adopt()

    @property
    def base(self):
        return self.hooks.base

    @property
    def installed(self):
        return self.hooks.installed

    def _expected(self, name, base):
        return self.hooks.replacement(name, base)

    def _adopt(self):
        base = self.hooks.locate(MAGIC)
        if base is None:
            return
        static = self.proc.read(base, RECONCILE_OFFSET)
        expected = block_bytes(base)[:RECONCILE_OFFSET]
        if not static or len(static) != RECONCILE_OFFSET or (
                static[:FACTOR_OFFSET] != expected[:FACTOR_OFFSET] or
                static[FACTOR_OFFSET + 4:] != expected[FACTOR_OFFSET + 4:]):
            raise RuntimeError("机场机位旧控制块版本不匹配，未接管")
        factor = struct.unpack_from("<I", static, FACTOR_OFFSET)[0]
        if not 1 <= factor <= 16:
            raise RuntimeError("机场机位旧控制块倍率异常")
        self.hooks.adopt(base)
        self.factor = factor

    def _prepare(self):
        self.hooks.prepare()

    def _install(self):
        self.hooks.apply(SITES)

    def set_factor(self, factor):
        if type(factor) is not int or not 1 <= factor <= 16:
            raise ValueError("机场机位倍率须为1～16的整数")
        if factor == 1 and self.base is None:
            return 1
        self._install()
        for name, (address, original, _kind) in SITES.items():
            if self.proc.read(address, len(original) // 2) != self.installed[name]:
                raise RuntimeError("机场机位入口已被外部修改")
        remote_factor = self.proc.read_u32(self.base + FACTOR_OFFSET)
        if remote_factor is None or not 1 <= remote_factor <= 16:
            raise RuntimeError("机场机位控制块倍率异常")
        self.factor = remote_factor
        if factor == remote_factor:
            return factor
        house = self.proc.read_u32(PLAYER_PTR)
        if not house:
            raise RuntimeError("当前玩家尚未载入")
        self.executor.install()
        if self.proc.read_u32(self.executor.base) not in (0, 3):
            raise RuntimeError("上一条游戏主线程命令尚未结束，未重写机场容量命令")
        code = reconcile_code(self.base + RECONCILE_OFFSET, house, factor,
                              self.base + TYPE_HELPER,
                              self.base + FACTOR_OFFSET)
        if len(code) > BLOCK_SIZE - RECONCILE_OFFSET or not self.proc.patch(
                self.base + RECONCILE_OFFSET, code):
            raise OSError("无法写入机场机位容量调整命令")
        result = self.executor.call(self.base + RECONCILE_OFFSET, timeout=5.0)
        self.factor = self.proc.read_u32(self.base + FACTOR_OFFSET) or remote_factor
        if result != 1 or self.factor != factor:
            raise RuntimeError("机场机位扩槽未完成；原倍率保持，已重新核算机位容量")
        return self.factor

    def close(self):
        if self.base is None:
            return
        if not self.proc.read_u32(PLAYER_PTR):
            # Menu or finished match: no house capacity to reconcile, and the
            # main-thread executor would time out. Factor 1 is native behavior
            # for the next match.
            if not self.proc.patch(self.base + FACTOR_OFFSET, struct.pack("<I", 1)):
                raise OSError("无法恢复机场机位倍率")
            self.factor = 1
            return
        self.set_factor(1)
        # Keep byte-verified resident hooks: high-slot aircraft may still be
        # parked when the trainer exits. Factor 1 denies new expanded slots.
