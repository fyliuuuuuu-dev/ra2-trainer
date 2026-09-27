"""Opt-in live integration test; close the visible trainer first."""
import json
import os
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from trainer import app as ui, units, addresses
from trainer.mem import Process
from trainer import production, protection, power, executor


def main():
    qt = QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    qt.setStyleSheet(ui.QSS)
    qt.setFont(QFont("Microsoft YaHei UI", 9))
    with tempfile.TemporaryDirectory() as tmp:
        ui.STATE_FILE = str(Path(tmp) / "state.json")
        w = ui.MainWindow()
        w.t_poll.stop()
        assert w.proc and w.can_write()
        for fid in ("fast_build", "instant_build", "unlimited_queue", "invincible", "infinite_power"):
            w.set_patch(fid, True)
            assert w.enabled[fid], (fid, w.log_view.toPlainText().splitlines()[-1])
        w.value_write("repair_amount", "25")
        assert w.repair_amount == 25
        assert not Path(ui.STATE_FILE).exists()  # nothing persists until the save button
        assert w.save_state()
        saved = json.loads(Path(ui.STATE_FILE).read_text(encoding="utf-8"))
        assert saved["_repair_amount"] == 25
        p = w.proc
        candidates = units.player_technos(p, kinds=[0x79CBBC])
        obj, vt = next((a, v) for a, v in candidates if p.read_i32(a + 0x6C) > 200)
        original = p.read_i32(obj + 0x6C)
        typ = units.type_of(p, obj, vt)
        maximum = p.read_i32(typ + 0xA0)
        start = maximum - 100
        try:
            assert p.write_i32(obj + 0x6C, start)
            w._apply_loop(addresses.LOOP_ACTIONS["auto_repair"], force_scan=True)
            result = p.read_i32(obj + 0x6C)
            print("repair", start, "->", result, flush=True)
            assert result == start + 25
        finally:
            if units.valid_techno(p, obj, vt, units.player_house(p)):
                p.write_i32(obj + 0x6C, original)
                p.write_i32(obj + 0x70, original)
        w.show()
        qt.processEvents()
        w.grab().save(str(Path(__file__).resolve().parents[1] / "ui-preview.png"))
        assert len(w.rows) == 57
        assert w.close()
        p = Process("game.exe")
        for va, original in list(production.SITES.values()) + list(protection.SITES.items()) + [
                (power.HOOK, power.ORIGINAL), (executor.HOOK, executor.ORIGINAL)]:
            assert p.read(va, len(original)) == original, hex(va)
        p.close()
        print("PASS: UI controls, combined hooks, repair amount, persistence and close restoration", flush=True)


if __name__ == "__main__":
    main()
