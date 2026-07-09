"""Tests for the capture enums."""

import pytest
from spectrumx.models.capture_enums import CaptureOrigin
from spectrumx.models.capture_enums import CaptureType


class TestCaptureType:
    """Tests for CaptureType enum."""

    def test_digital_rf(self) -> None:
        """CaptureType.DigitalRF == 'drf'."""
        assert CaptureType.DigitalRF == "drf"

    def test_radio_hound(self) -> None:
        """CaptureType.RadioHound == 'rh'."""
        assert CaptureType.RadioHound == "rh"

    def test_sigmf(self) -> None:
        """CaptureType.SigMF == 'sigmf'."""
        assert CaptureType.SigMF == "sigmf"

    @pytest.mark.parametrize(
        "member", list(CaptureType), ids=[m.name for m in CaptureType]
    )
    def test_value_round_trips_through_constructor(self, member: CaptureType) -> None:
        """Serialization round-trip: ``CaptureType(member.value) is member``."""
        assert CaptureType(member.value) is member

    def test_invalid_value_raises_value_error(self) -> None:
        """Error path: an unknown serialization value raises ValueError."""
        with pytest.raises(ValueError, match="is not a valid CaptureType"):
            CaptureType("invalid")  # type: ignore[arg-type]


class TestCaptureOrigin:
    """Tests for CaptureOrigin enum."""

    def test_system(self) -> None:
        """CaptureOrigin.System == 'system'."""
        assert CaptureOrigin.System == "system"

    def test_user(self) -> None:
        """CaptureOrigin.User == 'user'."""
        assert CaptureOrigin.User == "user"

    @pytest.mark.parametrize(
        "member", list(CaptureOrigin), ids=[m.name for m in CaptureOrigin]
    )
    def test_value_round_trips_through_constructor(self, member: CaptureOrigin) -> None:
        """Serialization round-trip: ``CaptureOrigin(member.value) is member``."""
        assert CaptureOrigin(member.value) is member

    def test_invalid_value_raises_value_error(self) -> None:
        """Error path: an unknown serialization value raises ValueError."""
        with pytest.raises(ValueError, match="is not a valid CaptureOrigin"):
            CaptureOrigin("invalid")  # type: ignore[arg-type]
