"""Opt-in live regression: python -m tools.production_live_test.

Close the trainer first. Runs stock Update on an isolated unregistered factory
buffer, using zero owed balance; no products are spawned or queues changed.
"""
import struct

from trainer.mem import Process
from trainer.operations import GameOperations, X86
from trainer.production import ProductionController, SITES
from trainer.units import player_house, enemy_houses, player_technos, type_of


def main():
    p = Process("game.exe")
    op = GameOperations(p)
    control = ProductionController(p)
    buf = p.alloc(0x4000)
    house = player_house(p)
    other = enemy_houses(p)[0]

    def update(label, owner, expected, *, elapsed=10, suspended=False, balance=0):
        data = bytearray(0x100)
        for off, value in ((0x24, 10), (0x30, 100), (0x34, 100), (0x38, 1),
                           (0x54, 1), (0x5C, balance), (0x64, -1), (0x68, owner)):
            struct.pack_into("<I", data, off, value & 0xFFFFFFFF)
        data[0x6C] = int(suspended)
        assert p.write(buf, bytes(data))
        a = X86()
        a.imm("a1", 0xA40D2C)
        a.imm("2d", elapsed)
        a.imm("a3", buf + 0x28)
        a.imm("b9", buf)
        a.imm("b8", 0x4B9300)
        a.emit("ff d0")
        a.imm("a1", buf + 0x24)
        a.emit("c3")
        result = op.run(a.finish())
        print(label, result, "balance", p.read_u32(buf + 0x5C), flush=True)
        assert result == expected, (label, result, expected)

    try:
        update("normal", house, 10)
        control.set("fast_build", True)
        update("fast", house, 11)
        update("fast-other-house", other, 10)
        update("fast-early", house, 10, elapsed=0)
        update("manual-pause", house, 10, suspended=True)
        control.set("instant_build", True)
        update("instant", house, 54, elapsed=0)
        update("instant-other-house", other, 10, elapsed=0)
        update("instant-insufficient-funds", house, 53, elapsed=0, balance=2000000000)
        update("instant-manual-pause", house, 10, suspended=True)
        control.set("instant_build", False)
        update("back-to-fast", house, 11)
        control.set("fast_build", False)
        update("back-to-normal", house, 10)
        tank, vt = player_technos(p, kinds=[0x7ADDF8])[0]
        typ = type_of(p, tank, vt)
        limit = p.read_u32(p.read_u32(0x839848) + 0xE8)
        assert 0 < limit < 999

        def queue(label, owner, count, expected):
            data = bytearray(0x100)
            for off, value in ((0x34, 1), (0x40, buf + 0x1000), (0x44, 1000),
                               (0x4C, count), (0x68, owner)):
                struct.pack_into("<I", data, off, value)
            assert p.write(buf, bytes(data))
            assert p.write(buf + 0x1000, struct.pack("<I", typ) * 1000)
            op.executor.call(0x4B9440, this=buf, args=(typ, owner, 0))
            actual = p.read_u32(buf + 0x4C)
            print(label, count, "->", actual, flush=True)
            assert actual == expected

        queue("queue-normal-limit", house, limit, limit)
        control.set("unlimited_queue", True)
        queue("queue-expanded", house, limit, limit + 1)
        queue("queue-cap", house, 999, 999)
        queue("queue-other-house", other, limit, limit)
        control.set("unlimited_queue", False)
        queue("queue-disabled", house, limit, limit)
    finally:
        control.close()
        op.close()
        # Never free a possibly still-running command's argument buffer.
        p.close()
    p = Process("game.exe")
    for va, original in SITES.values():
        assert p.read(va, len(original)) == original
    p.close()
    print("PASS: production behavior and all hook bytes restored", flush=True)


if __name__ == "__main__":
    main()
