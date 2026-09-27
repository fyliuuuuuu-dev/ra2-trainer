"""Runtime probe CLI: inspect/verify trainer addresses against a running game.exe."""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "trainer"))
from mem import Process  # noqa: E402

GAME_NAMES = ["game.exe", "gamemd.exe"]

# verified RA2 1.006 signatures (file bytes) for sanity checks
SIGS = {
    "money_no_decrease @0x4E53A9": (0x4E53A9, "2bc7", "eb 58"),
    "reveal_map @0x4F2FF8": (0x4F2FF8, "744a", "90 90"),
    "build_anywhere1 @0x49BC1C": (0x49BC1C, "0f84c4010000", "90" * 6),
    "build_anywhere2 @0x49BC2A": (0x49BC2A, "0f84b6010000", "90" * 6),
    "radar1 @0x4F2F1A": (0x4F2F1A, "7449", "90 90"),
    "radar2 @0x632F39": (0x632F39, "755d", "90 90"),
}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info")
    p = sub.add_parser("read"); p.add_argument("va"); p.add_argument("--n", type=int, default=4); p.add_argument("--fmt", default="i32")
    p = sub.add_parser("write"); p.add_argument("va"); p.add_argument("value"); p.add_argument("--fmt", default="i32")
    p = sub.add_parser("scan"); p.add_argument("value", type=int); p.add_argument("--limit", type=int, default=40)
    p = sub.add_parser("ptr"); p.add_argument("va")
    p = sub.add_parser("sig")

    a = ap.parse_args()

    pids = Process.find_pids(GAME_NAMES)
    if not pids:
        print("no game.exe / gamemd.exe running")
        return 1
    pid, name = pids[0]
    print(f"attached pid={pid} ({name})")
    proc = Process(pid)

    if a.cmd == "info":
        print("module_base(pe)=0x%X" % proc.module_base)
        real = proc.remote_module_base(name)
        print("module_base(remote)=%s" % (hex(real) if real else "n/a"))
        for k, (va, f, patched) in SIGS.items():
            cur = proc.read(va, len(bytes.fromhex(f))).hex()
            state = "PATCHED" if cur == patched.replace(" ", "") else ("original" if cur == f else "unknown:" + cur)
            print(f"  {k:34} -> {state}")

    elif a.cmd == "read":
        fmt = a.fmt
        if fmt == "i32":
            print(proc.read_i32(int(a.va, 0)))
        elif fmt == "u32":
            print(proc.read_u32(int(a.va, 0)))
        elif fmt == "f32":
            print(proc.read_f32(int(a.va, 0)))
        else:
            print(proc.read(int(a.va, 0), a.n).hex())

    elif a.cmd == "write":
        va = int(a.va, 0)
        if a.fmt == "i32":
            ok = proc.write_i32(va, int(a.value, 0))
        elif a.fmt == "f32":
            ok = proc.write_f32(va, float(a.value))
        else:
            ok = proc.write(va, bytes.fromhex(a.value))
        print("ok" if ok else "FAILED")

    elif a.cmd == "scan":
        hits = proc.scan_i32(a.value)
        print(f"{len(hits)} hits")
        for h in hits[: a.limit]:
            print("  0x%08X" % h)

    elif a.cmd == "ptr":
        va = int(a.va, 0)
        hits = proc.find_pointers_to(va)
        print(f"{len(hits)} pointers to 0x{va:X}")
        for h in hits[:60]:
            print("  0x%08X" % h)

    elif a.cmd == "sig":
        for k, (va, f, patched) in SIGS.items():
            cur = proc.read(va, len(bytes.fromhex(f))).hex()
            ok = cur == f
            print(f"  {k:34} -> {'MATCH' if ok else 'DIFF'} ({cur})")

    proc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
