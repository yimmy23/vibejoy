"""IINE-NS Pro pocket controller HID reader.

良值 IINE-NS 版本口袋手柄 Pro can expose a Microsoft-compatible HID report
when switched into its PC/XInput-compatible mode. VibeJoy treats that
compatibility transport as the IINE controller profile and only relies on the
observed HID report layout.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import hid

from .events import ButtonEvent, Direction, Event, Side, StickEvent
from .joycon import (
    DEFAULT_DEADZONE,
    DEFAULT_STICK_MODE,
    StickCalibration,
    StickMode,
    apply_circular_deadzone,
    quantize_direction,
)

logger = logging.getLogger(__name__)

IINE_COMPAT_VID = 0x045E
IINE_COMPAT_PID = 0x02FD

_INPUT_REPORT = 0x01
_READ_SIZE = 64
_TRIGGER_THRESHOLD = 64
_STICK_HALF_RANGE = 32767
_SNAPBACK_FRAMES = 2
_CALIBRATION_SAMPLES = 10
_CALIBRATION_INTERVAL_S = 0.015
_MAX_READ_ERRORS = 20

_BUTTON_BITS: dict[tuple[int, int], str] = {
    (14, 0x01): "a",
    (14, 0x02): "b",
    # The IINE controller reports X as 0x08 in this compatibility mode.
    (14, 0x08): "x",
    (14, 0x10): "y",
    (14, 0x40): "lb",
    (14, 0x80): "rb",
    # Report ID 1 carries the hardware screenshot/share key as consumer
    # usage 0x224 in the final payload byte.
    (16, 0x01): "capture",
}

_HAT_DIRECTIONS: dict[int, tuple[str, ...]] = {
    1: ("up",),
    2: ("up", "right"),
    3: ("right",),
    4: ("down", "right"),
    5: ("down",),
    6: ("down", "left"),
    7: ("left",),
    8: ("up", "left"),
}


@dataclass
class _StickState:
    prev_direction: Direction | None = None
    center_frames: int = 0


@dataclass
class _ReaderState:
    prev_buttons: set[str] = field(default_factory=set)
    left_stick: _StickState = field(default_factory=_StickState)
    right_stick: _StickState = field(default_factory=_StickState)
    read_errors: int = 0
    last_report: bytes | None = None


class IineProControllerReader:
    """Polls a Bluetooth 良值 IINE-NS 版本口袋手柄 Pro compatible device."""

    def __init__(
        self,
        device: hid.device,
        *,
        deadzone: float = DEFAULT_DEADZONE,
        stick_mode: StickMode = DEFAULT_STICK_MODE,
    ) -> None:
        if not 0.0 <= deadzone < 1.0:
            raise ValueError(f"deadzone must be in [0, 1), got {deadzone}")
        self._device = device
        self._device.set_nonblocking(True)
        self._deadzone = deadzone
        self._stick_mode = stick_mode
        self._state = _ReaderState()
        self._calibration: StickCalibration | None = None
        self._right_calibration: StickCalibration | None = None

    @property
    def side(self) -> Side:
        return "iine_pro"

    @property
    def calibration(self) -> StickCalibration | None:
        return self._calibration

    def calibrate(
        self,
        *,
        samples: int = _CALIBRATION_SAMPLES,
        interval_s: float = _CALIBRATION_INTERVAL_S,
    ) -> StickCalibration:
        reports: list[bytes] = []
        deadline = time.monotonic() + max(0.5, samples * interval_s * 4)
        while len(reports) < samples and time.monotonic() < deadline:
            report = self._read_latest_report()
            if report is not None:
                reports.append(report)
            time.sleep(interval_s)

        left_cal = _calibrate_stick(reports, _decode_left_stick)
        right_cal = _calibrate_stick(reports, _decode_right_stick)
        self._calibration = left_cal
        self._right_calibration = right_cal
        logger.info(
            "iine_pro stick baseline: left=(%d,%d) right=(%d,%d)",
            left_cal.baseline_x,
            left_cal.baseline_y,
            right_cal.baseline_x,
            right_cal.baseline_y,
        )
        return left_cal

    @property
    def right_calibration(self) -> StickCalibration | None:
        return self._right_calibration

    @property
    def calibrations(self) -> dict[str, StickCalibration]:
        out: dict[str, StickCalibration] = {}
        if self._calibration is not None:
            out["l-stick"] = self._calibration
        if self._right_calibration is not None:
            out["r-stick"] = self._right_calibration
        return out

    def poll(self) -> Iterator[Event]:
        report = self._read_latest_report()
        if report is None:
            return
        yield from self._diff_buttons(report)
        yield from self._diff_stick(
            report,
            stick_name="l-stick",
            decode=_decode_left_stick,
            calibration=self._calibration,
            state=self._state.left_stick,
        )
        yield from self._diff_stick(
            report,
            stick_name="r-stick",
            decode=_decode_right_stick,
            calibration=self._right_calibration,
            state=self._state.right_stick,
        )

    def close(self) -> None:
        try:
            self._device.close()
        except Exception:  # pragma: no cover
            logger.debug("iine_pro controller close failed", exc_info=True)

    def _read_latest_report(self) -> bytes | None:
        latest: bytes | None = None
        while True:
            try:
                data = self._device.read(_READ_SIZE)
            except OSError as e:
                self._state.read_errors += 1
                if self._state.read_errors == 1 or self._state.read_errors % 5 == 0:
                    logger.warning(
                        "iine_pro controller read failed (%d/%d): %s",
                        self._state.read_errors,
                        _MAX_READ_ERRORS,
                        e,
                    )
                if self._state.read_errors >= _MAX_READ_ERRORS:
                    raise OSError(
                        "iine_pro controller read failed repeatedly; reopening HID handle"
                    ) from e
                return None
            if not data:
                break
            report = bytes(data)
            if len(report) >= 17 and report[0] == _INPUT_REPORT:
                latest = report
        if latest is not None:
            self._state.read_errors = 0
            self._state.last_report = latest
        return latest

    def _diff_buttons(self, report: bytes) -> Iterator[ButtonEvent]:
        current = _active_buttons(report)
        pressed = current - self._state.prev_buttons
        released = self._state.prev_buttons - current

        for btn in sorted(pressed):
            yield ButtonEvent(side="iine_pro", button=btn, pressed=True)
        for btn in sorted(released):
            yield ButtonEvent(side="iine_pro", button=btn, pressed=False)

        self._state.prev_buttons = current

    def _diff_stick(
        self,
        report: bytes,
        *,
        stick_name: str,
        decode: Callable[[bytes], tuple[int, int]],
        calibration: StickCalibration | None,
        state: _StickState,
    ) -> Iterator[StickEvent]:
        if calibration is None:
            return

        raw_x, raw_y = decode(report)
        nx, ny = calibration.normalize(raw_x, raw_y)
        fx, fy = apply_circular_deadzone(nx, ny, self._deadzone)
        direction = quantize_direction(fx, fy, self._stick_mode)

        if direction is None and state.prev_direction is not None:
            state.center_frames += 1
            if state.center_frames < _SNAPBACK_FRAMES:
                return
            yield StickEvent(side="iine_pro", direction=None, stick=stick_name)
            state.prev_direction = None
            state.center_frames = 0
            return

        if direction is not None and direction != state.prev_direction:
            state.center_frames = 0
            yield StickEvent(side="iine_pro", direction=direction, stick=stick_name)
            state.prev_direction = direction


def _calibrate_stick(
    reports: list[bytes],
    decode: Callable[[bytes], tuple[int, int]],
) -> StickCalibration:
    if reports:
        xs: list[int] = []
        ys: list[int] = []
        for report in reports:
            x, y = decode(report)
            xs.append(x)
            ys.append(y)
        baseline_x = sum(xs) // len(xs)
        baseline_y = sum(ys) // len(ys)
    else:
        baseline_x = 0x8000
        baseline_y = 0x8000

    return StickCalibration(
        baseline_x=baseline_x,
        baseline_y=baseline_y,
        half_range_x=_STICK_HALF_RANGE,
        half_range_y=_STICK_HALF_RANGE,
    )


def discover_readers(
    *,
    deadzone: float = DEFAULT_DEADZONE,
    stick_mode: StickMode = DEFAULT_STICK_MODE,
) -> list[IineProControllerReader]:
    if not hid.enumerate(IINE_COMPAT_VID, IINE_COMPAT_PID):
        return []

    try:
        dev = hid.device()
        dev.open(IINE_COMPAT_VID, IINE_COMPAT_PID)
        logger.info("opened IINE Pro controller")
        return [IineProControllerReader(dev, deadzone=deadzone, stick_mode=stick_mode)]
    except OSError as e:
        logger.error("failed to open IINE Pro controller: %s", e)
        return []


def _active_buttons(report: bytes) -> set[str]:
    buttons: set[str] = set()
    for (byte_index, mask), name in _BUTTON_BITS.items():
        if report[byte_index] & mask:
            buttons.add(name)

    hat = report[13]
    for name in _HAT_DIRECTIONS.get(hat, ()):
        buttons.add(name)

    left_trigger = int.from_bytes(report[9:11], "little")
    right_trigger = int.from_bytes(report[11:13], "little")
    if left_trigger > _TRIGGER_THRESHOLD:
        buttons.add("lt")
    if right_trigger > _TRIGGER_THRESHOLD:
        buttons.add("rt")

    return buttons


def _decode_left_stick(report: bytes) -> tuple[int, int]:
    return (
        int.from_bytes(report[1:3], "little"),
        int.from_bytes(report[3:5], "little"),
    )


def _decode_right_stick(report: bytes) -> tuple[int, int]:
    return (
        int.from_bytes(report[5:7], "little"),
        int.from_bytes(report[7:9], "little"),
    )
