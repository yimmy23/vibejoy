from __future__ import annotations

from vibejoy.iine_pro_controller import _active_buttons, _decode_left_stick, _decode_right_stick


def _report(*, hat: int = 0, buttons: int = 0, extra_buttons: int = 0) -> bytes:
    data = bytearray.fromhex("0100800080008000800000000000000000")
    data[13] = hat
    data[14] = buttons
    data[16] = extra_buttons
    return bytes(data)


def test_decode_captured_buttons() -> None:
    assert _active_buttons(_report(buttons=0x01)) == {"a"}
    assert _active_buttons(_report(buttons=0x02)) == {"b"}
    assert _active_buttons(_report(buttons=0x08)) == {"x"}
    assert _active_buttons(_report(buttons=0x10)) == {"y"}
    assert _active_buttons(_report(buttons=0x40)) == {"lb"}
    assert _active_buttons(_report(buttons=0x80)) == {"rb"}
    assert _active_buttons(_report(extra_buttons=0x01)) == {"capture"}


def test_decode_captured_dpad_hat() -> None:
    assert _active_buttons(_report(hat=1)) == {"up"}
    assert _active_buttons(_report(hat=5)) == {"down"}
    assert _active_buttons(_report(hat=7)) == {"left"}
    assert _active_buttons(_report(hat=3)) == {"right"}


def test_decode_left_stick_center() -> None:
    assert _decode_left_stick(_report()) == (0x8000, 0x8000)


def test_decode_right_stick_center() -> None:
    assert _decode_right_stick(_report()) == (0x8000, 0x8000)


def test_decode_right_stick_motion() -> None:
    data = bytearray(_report())
    data[5:7] = (0x9000).to_bytes(2, "little")
    data[7:9] = (0x7000).to_bytes(2, "little")
    assert _decode_right_stick(bytes(data)) == (0x9000, 0x7000)
