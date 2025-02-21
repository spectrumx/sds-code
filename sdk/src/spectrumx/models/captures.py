"""Capture model for SpectrumX."""

import sys

if sys.version_info < (3, 11):  # noqa: UP036
    from backports.strenum import StrEnum  # noqa: UP035 # Required backport
else:
    from enum import StrEnum

from pathlib import Path
from typing import Annotated
from typing import Any

from pydantic import UUID4
from pydantic import BaseModel
from pydantic import Field


class CaptureType(StrEnum):
    """Capture types in SDS."""

    DigitalRF = "drf"
    RadioHound = "rh"
    SigMF = "sigmf"


class CaptureOrigin(StrEnum):
    """Capture origins in SDS."""

    System = "system"
    User = "user"


_d_capture_props = "The indexed metadata for the capture"
_d_capture_type = f"The type of capture {', '.join([x.value for x in CaptureType])}"
_d_index_name = "The name of the SDS index associated with the capture"
_d_origin = "The origin of the capture"
_d_top_level_dir = "The top-level directory for the capture files"
_d_uuid = "The unique identifier for the capture"

_d_channel = "The channel associated with the capture. Only for RadioHound type."
_d_scan_group = "The scan group associated with the capture. Only for Digital-RF type."


class Capture(BaseModel):
    """A capture in SDS. A collection of spectrum data files that is indexed."""

    capture_props: Annotated[dict[str, Any], Field(description=_d_capture_props)]
    capture_type: Annotated[CaptureType, Field(description=_d_capture_type)]
    index_name: Annotated[str, Field(max_length=255, description=_d_index_name)]
    origin: Annotated[CaptureOrigin, Field(description=_d_origin)]
    top_level_dir: Annotated[Path, Field(description=_d_top_level_dir)]
    uuid: Annotated[UUID4, Field(description=_d_uuid)]

    # optional fields
    channel: Annotated[
        str | None, Field(max_length=255, description=_d_channel, default=None)
    ]
    scan_group: Annotated[UUID4 | None, Field(description=_d_scan_group, default=None)]

    def __str__(self) -> str:
        return f"<{self.__repr_name__} {self.uuid}>"


__all__ = [
    "Capture",
    "CaptureType",
]
