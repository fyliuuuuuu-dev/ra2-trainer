"""One-session airport capacity check while the GUI trainer is closed.

Run interactively. Enter ``status`` after game actions and ``quit`` to restore
factor 1 and remove the temporary main-thread command hook. Resident airport
guards remain to protect any aircraft already using high contact slots.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer.airport_slots import AirportSlotsController
from trainer.executor import MainThreadExecutor
from trainer.mem import Process


AIRPORT = 0x1003D3E0  # this save only: AMRADR, UID 1032457
AIRPORT_UID = 1032457


def snapshot(proc, controller):
    house = proc.read_u32(0xA35DB4)
    if (not house or proc.read_u32(AIRPORT) != 0x79CBBC or
            proc.read_u32(AIRPORT + 0x10) != AIRPORT_UID or
            proc.read_u32(AIRPORT + 0x1B4) != house):
        raise RuntimeError("本局机场身份已变化，停止读取")
    data, size = proc.read_u32(AIRPORT + 0xCC), proc.read_i32(AIRPORT + 0xD0)
    if not data or size is None or not 0 <= size <= 64:
        raise RuntimeError("机场联系表异常")
    contacts = []
    for index in range(size):
        obj = proc.read_u32(data + index * 4) or 0
        if obj:
            contacts.append((index, hex(obj), proc.read_u32(obj + 0x10),
                             proc.read_i32(obj + 0x6C)))
    print("factor", controller.factor, "house_pads", proc.read_i32(house + 0x218),
          "radio_slots", size, "contacts", contacts, flush=True)


def main():
    proc = Process(21632)
    executor = MainThreadExecutor(proc)
    controller = AirportSlotsController(proc, executor)
    try:
        snapshot(proc, controller)
        controller.set_factor(2)
        snapshot(proc, controller)
        print("输入 status 查看；输入 1/2/3 切倍率；输入 quit 收尾", flush=True)
        for line in sys.stdin:
            command = line.strip().lower()
            try:
                if command == "quit":
                    break
                if command in {"1", "2", "3"}:
                    controller.set_factor(int(command))
                if command in {"status", "1", "2", "3"}:
                    snapshot(proc, controller)
            except Exception as exc:
                print("命令失败", repr(exc), flush=True)
    finally:
        try:
            controller.close()
            snapshot(proc, controller)
        finally:
            executor.close()
            proc.close()


if __name__ == "__main__":
    main()
