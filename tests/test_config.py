from __future__ import annotations

from pathlib import Path

import pytest

from vibejoy.config import (
    Config,
    ConfigError,
    GlobalConfig,
    load_config,
    read_example_config,
    validate_config,
)


@pytest.fixture
def example_config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(read_example_config(), encoding="utf-8")
    return path


def test_example_config_is_valid(example_config_file: Path) -> None:
    config = load_config(example_config_file)
    assert "right" in config.profiles
    assert "left" in config.profiles
    assert "claude_focus" in config.macros


def test_example_config_has_expected_macro(example_config_file: Path) -> None:
    config = load_config(example_config_file)
    macro = config.macros["claude_focus"]
    assert macro.if_app is not None
    assert any(step.startswith("type:") for step in macro.steps)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(tmp_path / "nope.toml")


def test_invalid_toml(tmp_path: Path) -> None:
    path = tmp_path / "broken.toml"
    path.write_text("this = is = not toml", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(path)


def test_unknown_top_level_section(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("[mystery]\nfoo = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown top-level"):
        load_config(path)


def test_unknown_profile_side(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text(
        '[profile.center.buttons]\na = "tap:enter"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown profile"):
        load_config(path)


def test_iine_pro_profile_is_valid(tmp_path: Path) -> None:
    path = tmp_path / "iine_pro.toml"
    path.write_text(
        '[profile.iine_pro.buttons]\na = "tap:enter"\n'
        '[profile.iine_pro.stick]\nup = "repeat:up@120"\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert "iine_pro" in config.profiles


def test_iine_pro_named_sticks_are_valid(tmp_path: Path) -> None:
    path = tmp_path / "iine_pro.toml"
    path.write_text(
        '[profile.iine_pro.l-stick]\nup = "repeat:up@120"\n'
        '[profile.iine_pro.r-stick]\ndown = "repeat:page_down@150"\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.profiles["iine_pro"].sticks["r-stick"]["down"] == "repeat:page_down@150"


def test_bad_action_spec(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text(
        '[profile.right.buttons]\na = "explode:world"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown action verb"):
        load_config(path)


def test_unknown_key_name(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text(
        '[profile.right.buttons]\na = "tap:explode"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(path)


def test_dangling_macro_reference(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text(
        '[profile.right.buttons]\na = "macro:ghost"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="macro 'ghost' is not defined"):
        load_config(path)


def test_bad_stick_direction(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text(
        '[profile.right.stick]\nnorth = "tap:up"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown direction"):
        load_config(path)


def test_validate_global_ranges() -> None:
    cfg = Config(
        global_=GlobalConfig(deadzone=2.0, poll_hz=5000, long_press_ms=-1, stick_mode="weird"),  # type: ignore[arg-type]
        profiles={},
        macros={},
    )
    errors = validate_config(cfg)
    assert any("deadzone" in e for e in errors)
    assert any("poll_hz" in e for e in errors)
    assert any("long_press_ms" in e for e in errors)
    assert any("stick_mode" in e for e in errors)


def test_macro_rejects_nested_macro(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text(
        '[macro.outer]\nsteps = ["macro:inner"]\n[macro.inner]\nsteps = ["tap:enter"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="nested macro"):
        load_config(path)
