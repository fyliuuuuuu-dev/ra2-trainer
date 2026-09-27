"""Opt-in skirmish test; close trainer before python -m tools.protection_live_test.

Tests hook routing with isolated buffers, then applies one point of damage to
one healthy owned ground unit and one building, restoring surviving HP.
"""
import struct
from trainer.mem import Process
from trainer.operations import GameOperations
from trainer.protection import ProtectionController, SITES, damage_code
from trainer import units


def main():
    p = Process("game.exe")
    op = GameOperations(p)
    control = ProtectionController(p)
    buf = p.alloc(0x1000)
    me = units.player_house(p)
    other = units.enemy_houses(p)[0]
    try:
        # Execute exactly the generated decision code, replacing its original
        # continuation with a sentinel so negative/foreign cases are harmless.
        entry, original = next(iter(SITES.items()))
        code = damage_code(buf, entry, original)
        code = code[:-len(original)-5] + bytes.fromhex("b8 78563412 c2 1800")
        assert p.patch(buf, code)
        fake, damage = buf + 0x200, buf + 0x500
        for label, owner, amount, forced, expected in (
            ("owned-hit", me, 1, 0, 0),
            ("foreign-hit", other, 1, 0, 0x12345678),
            ("healing", me, -10, 0, 0x12345678),
            ("forced-removal", me, 1, 1, 0x12345678),
            ("zero-damage", me, 0, 0, 0x12345678),
        ):
            assert p.write_u32(fake + 0x1B4, owner)
            assert p.write_i32(damage, amount)
            result = op.executor.call(buf, this=fake, args=(damage, 0, 0, 0, forced, 0))
            assert result == expected, (label, result)
            assert p.read_i32(damage) == (0 if expected == 0 else amount)
            print(label, "PASS", flush=True)

        rules = p.read_u32(0x839848)
        warhead = p.read_u32(rules + 0xCAC)
        assert warhead and p.read_u32(warhead)
        targets = units.player_technos(p, kinds=[0x7ADDF8, 0x79CBBC])
        chosen = []
        for vt in (0x7ADDF8, 0x79CBBC):
            chosen.append(next((a, v) for a, v in targets if v == vt and p.read_i32(a + 0x6C) > 100))
        for obj, vt in chosen:
            before = p.read_i32(obj + 0x6C)
            fn = p.read_u32(vt + 0x158)
            try:
                assert p.write_i32(damage, 1)
                result = op.executor.call(fn, this=obj, args=(damage, 0, warhead, 0, 0, 0))
                after = p.read_i32(obj + 0x6C)
                print(hex(vt), "unprotected", before, after, "result", result, flush=True)
                assert after < before
                control.enable()
                assert p.write_i32(damage, 1)
                op.executor.call(fn, this=obj, args=(damage, 0, warhead, 0, 0, 0))
                protected = p.read_i32(obj + 0x6C)
                print(hex(vt), "protected", protected, "damage", p.read_i32(damage), flush=True)
                # Elite vehicles can self-heal between the two simulation ticks.
                assert protected >= after and p.read_i32(damage) == 0
                control.disable()
                assert p.write_i32(damage, 1)
                op.executor.call(fn, this=obj, args=(damage, 0, warhead, 0, 0, 0))
                assert p.read_i32(obj + 0x6C) < protected
                print(hex(vt), "disabled: damage restored", flush=True)
            finally:
                if units.valid_techno(p, obj, vt, me):
                    p.write_i32(obj + 0x6C, before)
                    p.write_i32(obj + 0x70, before)
    finally:
        control.close()
        op.close()
        p.close()
    p = Process("game.exe")
    for entry, original in SITES.items():
        assert p.read(entry, len(original)) == original
    p.close()
    print("PASS: protection and restoration", flush=True)


if __name__ == "__main__":
    main()
