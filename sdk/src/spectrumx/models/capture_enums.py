"""Capture type/origin enums (shared by captures and datasets models)."""

from enum import StrEnum


class CaptureType(StrEnum):
    """Capture types in SDS."""

    DigitalRF = "drf"
    RadioHound = "rh"
    SigMF = "sigmf"


class CaptureOrigin(StrEnum):
    """Capture origins in SDS."""

    System = "system"
    User = "user"


__all__ = ["CaptureOrigin", "CaptureType"]
