"""Capture model for SpectrumX."""

from enum import StrEnum

from pydantic import UUID4
from pydantic import BaseModel


class CaptureType(StrEnum):
    """Capture types in SDS."""

    DigitalRF = "drf"
    RadioHound = "rh"
    SigMF = "sigmf"


class Capture(BaseModel):
    """A capture in SDS."""

    uuid: UUID4 | None = None


__all__ = [
    "Capture",
    "CaptureType",
]
