from __future__ import annotations

from pathlib import Path

from vibejoy import runner


def test_run_exits_cleanly_when_no_controller(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[profile.iine_pro.buttons]\na = "tap:enter"\n', encoding="utf-8")
    monkeypatch.setattr(runner, "discover_joycon_readers", lambda **_: [])
    monkeypatch.setattr(runner, "discover_iine_pro_readers", lambda **_: [])

    result = runner.run(str(config), install_signal_handlers=False)

    assert result.exit_code == 0
    assert "no Joy-Con or IINE Pro controller" in result.message
