"""One-shot garrison orders for infantry selected when the action was invoked."""
import struct

from . import units
from .addresses import BUILDING_VT, FRAME, INFANTRY_VT, SELECTED_COUNT, SELECTED_DATA
from .operations import X86

ENTER_MISSION = 8  # native Capture branch garrisons Occupier infantry
MAX_CELL_DISTANCE = 30  # about one screen of cells around each soldier
# HouseType flag Building.CanOccupy (0x452EE8) requires when an Occupier enters
# a building it does not own: set for civilian houses such as Neutral/Special.
CIVILIAN_FLAG = 0x1A6


MAX_CANDIDATES = 8  # nearest buildings tried per soldier
CANDIDATE = 20  # infantry, infantry id, building, building id, &reserved
SOLDIER = 4 + MAX_CANDIDATES * CANDIDATE
ENTER_CODE = 0x300


def enter_one_code(house):
    """enter_one(candidate*) -> 1 when ordered (cdecl). Revalidates on the game thread.

    Like a player's garrison click, the soldier's current mission does not
    matter; ownership and eligibility are left to native Building.CanOccupy.
    A success bumps the building's shared reservation counter so later
    soldiers in the same batch see the slot as taken.
    """
    a = X86()
    a.emit("56 53 8b 74 24 0c")  # ESI = candidate
    a.imm("a1", units.PLAYER_PTR)
    a.imm("3d", house)  # player must still be the house captured at click time
    a.jump("0f 85", "fail")
    a.emit("8b 0e")  # ECX = infantry
    a.imm("81 39", INFANTRY_VT)
    a.jump("0f 85", "fail")
    a.emit("8b 46 04 39 41 10")  # reject recycled object address
    a.jump("0f 85", "fail")
    a.imm("a1", units.PLAYER_PTR)
    a.emit("39 81 b4 01 00 00")  # infantry.Owner == Player
    a.jump("0f 85", "fail")
    a.emit("83 79 6c 00")
    a.jump("0f 8e", "fail")
    a.emit("80 79 76 00")
    a.jump("0f 85", "fail")
    a.emit("80 79 7d 01")
    a.jump("0f 85", "fail")
    a.emit("8b 91 a8 05 00 00 85 d2")  # InfantryType*
    a.jump("0f 84", "fail")
    a.emit("80 ba 08 0c 00 00 01")  # Type.Occupier
    a.jump("0f 85", "fail")
    a.emit("8b 56 08")  # EDX = building
    a.imm("81 3a", BUILDING_VT)
    a.jump("0f 85", "fail")
    a.emit("8b 46 0c 39 42 10")
    a.jump("0f 85", "fail")
    a.emit("83 7a 6c 00")
    a.jump("0f 8e", "fail")
    a.emit("80 7a 76 00")  # building not limbo
    a.jump("0f 85", "fail")
    a.emit("80 7a 7d 01")  # active, not sold/limbo
    a.jump("0f 85", "fail")
    a.emit("8b 82 b4 01 00 00 85 c0")  # building.Owner
    a.jump("0f 84", "fail")
    a.emit("8b 82 18 04 00 00 85 c0")  # BuildingType*
    a.jump("0f 84", "fail")
    a.emit("80 b8 1e 12 00 00 01")  # CanBeOccupied
    a.jump("0f 85", "fail")
    a.emit("8b 88 20 12 00 00 85 c9")  # MaxNumberOccupants
    a.jump("0f 8e", "fail")
    a.emit("8b 82 64 05 00 00")  # Occupants.Count
    a.emit("8b 5e 10 03 03")  # + reserved (shared counter)
    a.emit("39 c8")  # count + reserved < max
    a.jump("0f 8d", "fail")
    # Native Building.CanOccupy checks ownership, damage, capacity, and unit eligibility.
    a.emit("ff 36 89 d1")
    a.imm("b8", 0x452EB0)
    a.emit("ff d0 84 c0")
    a.jump("0f 84", "fail")
    a.emit("6a 00 ff 76 08 6a 00 6a 08")  # Follow, Destination = Building*, Target, Capture
    a.emit("8b 0e 8b 01 ff 90 20 03 00 00")  # Infantry.ClickedMission
    a.emit("ff 03")  # reserve the slot
    a.emit("b8 01 00 00 00 5b 5e c3")
    a.label("fail")
    a.emit("31 c0 5b 5e c3")
    return a.finish()


def enter_batch_code(house, count, soldiers, results):
    """Order every soldier in one frame; result = 1-based candidate index or 0."""
    a = X86()
    a.emit("56 53 57 55 31 ed")  # EBP = soldier index
    a.label("soldier")
    a.imm("81 fd", count)
    a.jump("0f 8d", "done")
    a.imm("69 fd", SOLDIER)
    a.imm("81 c7", soldiers)  # EDI = soldier block
    a.emit("31 db")  # EBX = candidate index
    a.label("candidate")
    a.emit("3b 1f")
    a.jump("0f 8d", "next")
    a.emit("8d 04 9b 8d 44 87 04 50")  # &candidates[ebx]
    a.jump("e8", "enter_one")
    a.emit("83 c4 04 85 c0")
    a.jump("0f 84", "try_next")
    a.emit("8d 43 01 89 04 ad")
    a.code += struct.pack("<I", results)
    a.jump("e9", "next")
    a.label("try_next")
    a.emit("43")
    a.jump("e9", "candidate")
    a.label("next")
    a.emit("45")
    a.jump("e9", "soldier")
    a.label("done")
    a.emit("5d 5f 5b 5e c3")
    a.label("enter_one")
    a.code += enter_one_code(house)
    return a.finish()


class AutoEnterController:
    def __init__(self, proc, operations):
        self.proc = proc
        self.operations = operations
        self.issued = {}
        self._validated = False
        self.last_note = ""

    def _validate(self):
        if self._validated:
            return
        if self.proc.read_u32(INFANTRY_VT + 0x320) != 0x6CC2A0:
            raise RuntimeError("步兵进驻接口与游戏版本不匹配")
        if self.proc.read(0x6CC2A0, 10) != bytes.fromhex("81ec880000005356578b"):
            raise RuntimeError("步兵进驻代码与游戏版本不匹配")
        if self.proc.read(0x452EB0, 10) != bytes.fromhex("568bf1578b8e18040000"):
            raise RuntimeError("建筑驻防资格代码与游戏版本不匹配")
        self._validated = True

    def _civilian(self, house, cache):
        """Same test as native CanOccupy: the owner's HouseType civilian flag."""
        if house not in cache:
            typ = self.proc.read_u32(house + 0x34) if house else None
            cache[house] = bool(typ) and bool(self.proc.read_u8(typ + CIVILIAN_FLAG))
        return cache[house]

    def snapshot_selected(self):
        """Freeze exact selection at click time without scanning the heap."""
        house = units.player_house(self.proc)
        if not house:
            return 0, []
        out = []
        for obj in units.selection(self.proc):
            if (self.proc.read_u32(obj) != INFANTRY_VT or
                    self.proc.read_u32(obj + 0x1B4) != house):
                continue
            unique_id = self.proc.read_u32(obj + 0x10)
            if unique_id is not None:
                out.append((obj, unique_id))
        return house, out

    def execute(self, snapshot):
        """Issue one batch; return (ordered, eligible selected infantry)."""
        self._validate()
        captured_house, selected = snapshot
        p = self.proc
        me = units.player_house(p)
        if not me:
            return 0, 0
        if me != captured_house:
            raise RuntimeError("玩家势力已变化，请重新选择步兵执行")
        self.last_note = ""
        civilian = {}
        frame = p.read_u32(FRAME)
        if frame is None:
            raise OSError("无法读取游戏帧")
        buildings = []
        for obj, vt in units.iter_technos(p):
            if vt == BUILDING_VT:
                owner = p.read_u32(obj + 0x1B4)
                if ((owner == me or (owner and self._civilian(owner, civilian)))
                        and units.valid_techno(p, obj, vt)):
                    buildings.append((obj, owner))
        # Keep reservations after deselection while an Enter order is underway.
        # Remove only completed, canceled, dead, or invalid-target assignments.
        retained = {}
        for (obj, unique_id), (target, target_id, issued_at) in self.issued.items():
            if not units.valid_techno(p, obj, INFANTRY_VT, me):
                continue
            if p.read_u32(obj + 0x10) != unique_id:
                continue
            if p.read_u8(obj + 0x76) == 1:  # inside building; native count owns slot
                continue
            if not units.valid_techno(p, target, BUILDING_VT):
                continue
            if p.read_u32(target + 0x10) != target_id:
                continue
            target_owner = p.read_u32(target + 0x1B4)
            if target_owner != me and not (target_owner and self._civilian(target_owner, civilian)):
                continue
            mission, queued = p.read_i32(obj + 0x98), p.read_i32(obj + 0xA0)
            if ((frame - issued_at) & 0xFFFFFFFF) > 300 and mission != ENTER_MISSION and queued != ENTER_MISSION:
                continue
            retained[(obj, unique_id)] = (target, target_id, issued_at)
        self.issued = retained
        choices = []
        for obj, owner in buildings:
            typ = units.type_of(p, obj, BUILDING_VT)
            if not typ or p.read_u8(typ + 0x121E) != 1:
                continue
            capacity = p.read_i32(typ + 0x1220)
            occupied = p.read_i32(obj + 0x564)
            if not capacity or occupied is None or capacity <= occupied:
                continue
            pos = p.read(obj + 0x88, 12)
            if pos:
                x, y, _z = struct.unpack("<iii", pos)
                choices.append((obj, p.read_u32(obj + 0x10), x >> 8, y >> 8, capacity, occupied))
        reservations = {}
        for target, _target_id, _issued_at in self.issued.values():
            reservations[target] = reservations.get(target, 0) + 1
        candidates = []
        for obj, unique_id in selected:
            if (p.read_u32(obj) != INFANTRY_VT or p.read_u32(obj + 0x10) != unique_id or
                    not units.valid_techno(p, obj, INFANTRY_VT, me) or
                    p.read_u8(obj + 0x76) != 0 or p.read_u8(obj + 0x7D) != 1):
                continue
            typ = units.type_of(p, obj, INFANTRY_VT)
            if not typ or p.read_u8(typ + 0xC08) != 1:
                continue
            candidates.append((obj, unique_id))
        sent = pending = refused = 0
        closest = None  # nearest free building beyond range, for the log
        plans = []  # (soldier, id, [(target, target_id), ...])
        for obj, unique_id in candidates:
            if (obj, unique_id) in self.issued:
                pending += 1
                continue
            pos = p.read(obj + 0x88, 12)
            if not pos:
                continue
            x, y, _z = struct.unpack("<iii", pos)
            x >>= 8
            y >>= 8
            free = sorted((max(abs(x - bx), abs(y - by)), target, target_id)
                          for target, target_id, bx, by, capacity, occupied in choices
                          if occupied + reservations.get(target, 0) < capacity
                          and target_id is not None)
            if free and free[0][0] > MAX_CELL_DISTANCE:
                closest = free[0][0] if closest is None else min(closest, free[0][0])
            nearest = [(t, tid) for d, t, tid in free if d <= MAX_CELL_DISTANCE][:MAX_CANDIDATES]
            if nearest:
                plans.append((obj, unique_id, nearest))
        if plans:
            results = self._order_batch(plans, reservations, captured_house)
            for (obj, unique_id, nearest), chosen in zip(plans, results):
                if chosen:
                    target, target_id = nearest[chosen - 1]
                    self.issued[(obj, unique_id)] = (target, target_id, frame)
                    sent += 1
                else:
                    refused += 1
        if sent < len(candidates):
            self.last_note = self._explain(len(choices), closest, pending, refused)
        return sent, len(candidates)

    def _order_batch(self, plans, reservations, house):
        """One game-frame command for all soldiers; returns chosen candidate per soldier."""
        targets = sorted({t for _obj, _id, nearest in plans for t, _tid in nearest})
        n = len(plans)
        counters_at = ENTER_CODE
        soldiers_at = counters_at + 4 * len(targets)
        results_at = soldiers_at + SOLDIER * n

        def build(block):
            counter = {t: block + counters_at + 4 * i for i, t in enumerate(targets)}
            code = enter_batch_code(house, n, block + soldiers_at, block + results_at)
            if len(code) > ENTER_CODE:
                raise ValueError("进驻命令过长")
            data = code.ljust(ENTER_CODE, b"\xcc")
            data += b"".join(struct.pack("<I", reservations.get(t, 0)) for t in targets)
            for obj, unique_id, nearest in plans:
                entry = struct.pack("<I", len(nearest))
                entry += b"".join(struct.pack("<IIIII", obj, unique_id, t, tid, counter[t])
                                  for t, tid in nearest)
                data += entry.ljust(SOLDIER, b"\0")
            return data + bytes(4 * n)

        raw = self.operations.run_block(results_at + 4 * n, build, results_at, 4 * n)
        return list(struct.unpack(f"<{n}I", raw))

    @staticmethod
    def _explain(free_buildings, closest, pending, refused):
        notes = []
        if not free_buildings:
            notes.append("地图上没有有空位的己方或平民可驻防建筑")
        elif closest is not None:
            notes.append(f"最近的有空位建筑在 {closest} 格外，超出 {MAX_CELL_DISTANCE} 格范围")
        if refused:
            notes.append(f"{refused} 名步兵被游戏拒绝进驻（建筑可能已被其他玩家占领、"
                         "正在受损/被控制，或步兵正在乘车）")
        if pending:
            notes.append(f"{pending} 名步兵已在前往建筑的途中")
        return "；".join(notes)

    def close(self):
        self.issued.clear()
