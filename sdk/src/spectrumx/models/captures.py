"""Capture model for SpectrumX."""

import sys
from datetime import datetime

from spectrumx.models.base import SDSModel

# python 3.10 backport
if sys.version_info < (3, 11):  # noqa: UP036
    from backports.strenum import StrEnum  # noqa: UP035 # Required backport
else:
    from enum import StrEnum

from pathlib import Path
from pathlib import PurePosixPath
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


_d_capture_created_at = "The time the capture was created"
_d_capture_props = "The indexed metadata for the capture (backward compatibility)"
_d_channels_metadata = "The channels metadata for DRF captures"
_d_capture_type = f"The type of capture {', '.join([x.value for x in CaptureType])}"
_d_index_name = "The name of the SDS index associated with the capture"
_d_origin = "The origin of the capture"
_d_top_level_dir = "The top-level directory for the capture files"
_d_uuid = "The unique identifier for the capture"
_d_capture_files = "Files associated to this capture"

_d_channel = "The channel (or channels) associated with the capture"
_d_scan_group = "The scan group associated with the capture (for RadioHound captures)"


class CaptureFile(BaseModel):
    uuid: Annotated[
        UUID4, Field(description="The unique identifier for the capture file")
    ]
    name: Annotated[
        str, Field(max_length=255, description="The name of the capture file")
    ]
    directory: Annotated[
        Path, Field(description="The directory where the capture file is stored")
    ]


class Capture(SDSModel):
    """A capture in SDS. A collection of spectrum data files that is indexed."""

    capture_props: Annotated[dict[str, Any], Field(description=_d_capture_props)]
    channels_metadata: Annotated[
        list[dict[str, Any]], Field(description=_d_channels_metadata)
    ]
    capture_type: Annotated[CaptureType, Field(description=_d_capture_type)]
    index_name: Annotated[str, Field(max_length=255, description=_d_index_name)]
    origin: Annotated[CaptureOrigin, Field(description=_d_origin)]
    top_level_dir: Annotated[PurePosixPath, Field(description=_d_top_level_dir)]
    files: Annotated[list[CaptureFile], Field(description=_d_capture_files)]

    # optional fields
    created_at: Annotated[
        datetime | None, Field(description=_d_capture_created_at, default=None)
    ]
    channel: Annotated[str | None, Field(description=_d_channel, default=None)]
    scan_group: Annotated[UUID4 | None, Field(description=_d_scan_group, default=None)]

    @property
    def channels(self) -> list[str]:
        """Get list of channel names for this capture."""
        if not self.channel:
            return []
        try:
            import json

            return json.loads(self.channel)
        except (json.JSONDecodeError, TypeError):
            # Fallback for legacy single-channel format
            return [self.channel] if self.channel else []

    @channels.setter
    def channels(self, value: list[str]) -> None:
        """Set the channels as a JSON array."""
        import json

        self.channel = json.dumps(value)

    @property
    def primary_channel(self) -> str | None:
        """Get the first channel name (for backward compatibility)."""
        channels = self.channels
        return channels[0] if channels else None

    def __str__(self) -> str:
        """Get the string representation of the capture."""
        return (
            f"Capture(uuid={self.uuid}, "
            f"type={self.capture_type}, "
            f"files={len(self.files)}, "
            f"created_at={self.created_at})"
        )

    def __repr__(self) -> str:
        # break up the line to avoid exceeding line length limits
        return (
            f"<{self.__class__.__name__} {self.uuid} "
            f"files={len(self.files)} created_at={self.created_at}>"
        )


__all__ = [
    "Capture",
    "CaptureType",
]
