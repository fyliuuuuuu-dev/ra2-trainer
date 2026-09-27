"""Player-only amphibious movement for stock RA2 1.006.

All adjustments are local to the moving Foot object. Shared Type and Rules
data remain unchanged. A detached trainer leaves DRAIN mode behind, allowing
already-waterborne units to return over beaches to native land.
"""
import struct

from .addresses import INFANTRY_VT, PLAYER_PTR, UNIT_VT
from .executor import relative_jump
from .hooks import HookSites
from .operations import X86


MAGIC = b"RA2WATER2\0"
LEGACY_MAGIC = b"RA2WATER1\0"  # first ten sites only; upgraded in place
MODE_OFFSET = 0x20
HELPER_OFFSET = 0x100
SITE_OFFSET = 0x400
SITE_STRIDE = 0x200
BLOCK_SIZE = 0x3000
MODE_OFF, MODE_ON, MODE_DRAIN = 0, 1, 2
MATRIX = 0x850EA0
CELL_ARRAY_PTR = 0x832618

# Full instructions from the local RA2 1.006 game.exe.
SITES = {
    "path_zone": (0x42A220, "8b7c24488b74243c", "zone_edi_esi"),
    "path_region": (0x42AAD4, "57508d442418", "zone_eax_edi"),
    "foot_region": (0x4C2EFF, "8b9800050000", "zone_ebx_esi"),
    "clicked_zone": (0x4C653C, "8bb800050000", "zone_edi_esi"),
    "destination_zone": (0x4CCB27, "8ba800050000", "zone_ebp_esi"),
    "special_nearby": (0x4C6741, "8b80a4050000", "speed_eax_esi"),
    "move_nearby": (0x4C6861, "8b80a4050000", "speed_eax_esi"),
    "infantry_enter": (0x50390C, "d9048da00e8500", "factor_ecx_ebp"),
    "infantry_level": (0x503974, "d90495a00e8500", "factor_edx_ebp"),
    "unit_enter": (0x703928, "d9048da00e8500", "factor_ecx_ebp"),
    # Attacking: TechnoClass::NearbyLocation 0x6CF130 finds the firing position
    # with the object's SpeedType/MovementZone; target evaluation compares the
    # shooter's zone (0x6C6530 -> 0x6C5570) and candidate cells (0x6C6130).
    "near_speed": (0x6CF141, "8b98a4050000", "speed_ebx_esi"),
    "near_zone": (0x6CF1DB, "8bb800050000", "zone_edi_esi"),
    "shooter_zone": (0x6C65EE, "8b8000050000", "type_eax_edi"),
    "target_zone": (0x6C571F, "8b8000050000", "type_eax_edi"),
    "candidate_zone": (0x6C6170, "8b8000050000", "type_eax_esi"),
}
LEGACY_SITE_COUNT = 10


def qualifier_code(base, mode_address):
    """ECX=Foot*, EAX=amphibious zone or -1; clobbers ECX/EDX."""
    a = X86()
    a.emit("53 56 57 89 ce")  # EBX/ESI/EDI; ESI=Foot
    a.emit("85 f6")
    a.jump("0f 84", "reject")
    a.imm("81 3e", INFANTRY_VT)
    a.jump("0f 84", "infantry")
    a.imm("81 3e", UNIT_VT)
    a.jump("0f 85", "reject")
    a.emit("8b be ac 05 00 00")  # Unit.Type
    a.jump("e9", "class_ok")
    a.label("infantry")
    a.emit("8b be a8 05 00 00")  # Infantry.Type
    a.label("class_ok")
    a.imm("a1", PLAYER_PTR)
    a.emit("85 c0")
    a.jump("0f 84", "reject")
    a.emit("39 86 b4 01 00 00")  # current player owns this instance
    a.jump("0f 85", "reject")
    a.emit("83 7e 6c 00")  # Health > 0
    a.jump("0f 8e", "reject")
    a.emit("80 7e 7d 01")  # active
    a.jump("0f 85", "reject")
    a.emit("80 7e 76 00")  # not limbo
    a.jump("0f 85", "reject")
    a.emit("85 ff")
    a.jump("0f 84", "reject")
    a.emit("80 bf da 0a 00 00 00")  # Type.Naval
    a.jump("0f 85", "reject")
    a.emit("8b 9f a4 05 00 00 83 fb 02")  # SpeedType 0..2 only
    a.jump("0f 87", "reject")
    a.emit("83 3c 9d e8 0e 85 00 00")  # Water[2*9+speed] originally zero
    a.jump("0f 85", "reject")
    a.imm("80 3d", mode_address)
    a.emit("01")
    a.jump("0f 84", "zone")
    a.imm("80 3d", mode_address)
    a.emit("02")
    a.jump("0f 85", "reject")
    # DRAIN: only a unit still in Water or Beach retains amphibious routing.
    a.emit("80 7e 79 00")  # not on a bridge
    a.jump("0f 85", "reject")
    a.emit("8b 86 88 00 00 00 c1 f8 08 3d ff 01 00 00")
    a.jump("0f 87", "reject")  # also catches negative after SAR
    a.emit("8b 96 8c 00 00 00 c1 fa 08 81 fa ff 01 00 00")
    a.jump("0f 87", "reject")
    a.emit("c1 e2 09 01 c2 c1 e2 02")
    a.imm("8b 1d", CELL_ARRAY_PTR)
    a.emit("85 db")
    a.jump("0f 84", "reject")
    a.emit("8b 04 13 85 c0")
    a.jump("0f 84", "reject")
    a.emit("3d f8 f9 a6 00")  # Map.GetCell sentinel
    a.jump("0f 84", "reject")
    a.emit("8b 80 ec 00 00 00 83 f8 02")
    a.jump("0f 84", "zone")
    a.emit("83 f8 06")
    a.jump("0f 85", "reject")
    a.label("zone")
    a.emit("8b 87 00 05 00 00")  # original MovementZone
    a.emit("83 f8 00")
    a.jump("0f 84", "amph5")
    a.emit("83 f8 07")
    a.jump("0f 84", "amph5")
    a.emit("83 f8 01")
    a.jump("0f 84", "amph4")
    a.emit("83 f8 02")
    a.jump("0f 84", "amph3")
    a.emit("83 f8 08")
    a.jump("0f 84", "amph3")
    a.jump("e9", "reject")
    a.label("amph5")
    a.emit("b8 05 00 00 00")
    a.jump("e9", "done")
    a.label("amph4")
    a.emit("b8 04 00 00 00")
    a.jump("e9", "done")
    a.label("amph3")
    a.emit("b8 03 00 00 00")
    a.jump("e9", "done")
    a.label("reject")
    a.emit("b8 ff ff ff ff")
    a.label("done")
    a.emit("5f 5e 5b c3")
    return a.finish()


def site_code(name, base, helper_address, one_address):
    address, original_hex, kind = SITES[name]
    original = bytes.fromhex(original_hex)
    a = X86()
    if kind.startswith("factor_"):
        a.emit("9c 60")
        saved_index = 0x18 if "ecx" in kind else 0x14
        saved_owner = 0x08  # EBP in PUSHAD frame
        a.emit(f"8b 44 24 {saved_index:02x}")
        a.emit("83 f8 12")
        a.jump("0f 82", "original")
        a.emit("83 f8 14")
        a.jump("0f 86", "land_ok")
        a.emit("83 f8 36")
        a.jump("0f 82", "original")
        a.emit("83 f8 38")
        a.jump("0f 87", "original")
        a.label("land_ok")
        a.emit("83 3c 85 a0 0e 85 00 00")  # actual factor zero
        a.jump("0f 85", "original")
        a.emit(f"8b 4c 24 {saved_owner:02x}")
        a.imm("e8", helper_address - (base + len(a.code) + 5))
        a.emit("83 f8 ff")
        a.jump("0f 84", "original")
        a.emit("61 9d")
        a.imm("d9 05", one_address)  # exactly one x87 stack value
        a.jump("e9", "resume")
        a.label("original")
        a.emit("61 9d")
        a.code += original
        a.label("resume")
    else:
        if kind != "zone_eax_edi":
            a.code += original
        a.emit("9c 60")
        source_slot = 0 if kind.endswith("_edi") else 4  # EDI or ESI
        a.emit(f"8b 4c 24 {source_slot:02x}")
        a.imm("e8", helper_address - (base + len(a.code) + 5))
        a.emit("83 f8 ff")
        a.jump("0f 84", "restore")
        output_slot = {"zone_edi_esi": 0, "zone_eax_edi": 0x1C,
                       "zone_ebx_esi": 0x10, "zone_ebp_esi": 0x08,
                       "speed_eax_esi": 0x1C, "speed_ebx_esi": 0x10,
                       "type_eax_edi": 0x1C, "type_eax_esi": 0x1C}[kind]
        if kind.startswith("speed_"):
            a.emit("b8 06 00 00 00")
        a.emit(f"89 44 24 {output_slot:02x}")
        a.label("restore")
        a.emit("61 9d")
        if kind == "zone_eax_edi":
            a.code += original
    code = a.finish()
    return code + relative_jump(base + len(code), address + len(original))


def block_bytes(base):
    blob = bytearray(BLOCK_SIZE)
    blob[:len(MAGIC)] = MAGIC
    blob[MODE_OFFSET] = MODE_OFF
    struct.pack_into("<f", blob, 0x28, 1.0)
    helper = qualifier_code(base + HELPER_OFFSET, base + MODE_OFFSET)
    if len(helper) > SITE_OFFSET - HELPER_OFFSET:
        raise ValueError("水面行走资格代码过长")
    blob[HELPER_OFFSET:HELPER_OFFSET + len(helper)] = helper
    for i, name in enumerate(SITES):
        off = SITE_OFFSET + i * SITE_STRIDE
        code = site_code(name, base + off, base + HELPER_OFFSET, base + 0x28)
        if len(code) > SITE_STRIDE:
            raise ValueError(f"水面行走补丁过长：{name}")
        blob[off:off + len(code)] = code
    return bytes(blob)


class WaterWalkController:
    def __init__(self, proc):
        self.proc = proc
        # Resident by design (DRAIN lets waterborne units return): adopt, never release.
        self.hooks = HookSites(proc, "水面行走", {
            name: (address, bytes.fromhex(raw), SITE_OFFSET + i * SITE_STRIDE)
            for i, (name, (address, raw, _kind)) in enumerate(SITES.items())},
            block_bytes, size=BLOCK_SIZE, release=False)
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
        legacy = base is None
        if legacy:
            base = self.hooks.locate(LEGACY_MAGIC)
        if base is None:
            return
        block = self.proc.read(base, BLOCK_SIZE)
        expected = block_bytes(base)
        # A version-1 block holds the same helper and first ten stubs; the
        # new stubs go into its unused tail before the new sites are enabled.
        end = SITE_OFFSET + LEGACY_SITE_COUNT * SITE_STRIDE if legacy else BLOCK_SIZE
        start = len(MAGIC) if legacy else 0
        if not block or len(block) != BLOCK_SIZE or (
                block[start:MODE_OFFSET] != expected[start:MODE_OFFSET] or
                block[MODE_OFFSET + 1:end] != expected[MODE_OFFSET + 1:end] or
                any(block[end:])):
            raise RuntimeError("水面行走控制块版本不匹配，未接管")
        if block[MODE_OFFSET] not in (MODE_ON, MODE_DRAIN):
            raise RuntimeError("水面行走控制块状态异常")
        names = list(SITES)[:LEGACY_SITE_COUNT] if legacy else None
        self.hooks.adopt(base, names)
        if legacy:
            if not (self.proc.patch(base + end, expected[end:]) and
                    self.proc.patch(base, MAGIC)):
                raise OSError("水面行走控制块升级失败")
        # Attach starts from a safe disabled state. Saved true is reapplied by
        # MainWindow; a stale ON left by an abnormal previous exit cannot lie
        # behind an off-looking toggle.
        if block[MODE_OFFSET] == MODE_ON:
            self.disable()

    @property
    def enabled(self):
        return self.base is not None and self.proc.read(self.base + MODE_OFFSET, 1) == bytes([MODE_ON])

    def _prepare(self):
        self.hooks.prepare()

    def enable(self):
        def switch_on():
            # Called on every periodic reapply; rewrite only when the mode changed.
            if self.proc.read(self.base + MODE_OFFSET, 1) == bytes([MODE_ON]):
                return
            if not self.proc.patch(self.base + MODE_OFFSET, bytes([MODE_ON])):
                raise OSError("无法启用水面行走控制块")
        self.hooks.apply(SITES, after=switch_on)

    def disable(self):
        if self.base is None:
            return
        # The autonomous hook now applies only to units still on water/beach.
        # It may remain resident if this trainer exits before those units land.
        if self.installed:
            if not self.proc.patch(self.base + MODE_OFFSET, bytes([MODE_DRAIN])):
                raise OSError("无法关闭水面行走控制块")

    close = disable
