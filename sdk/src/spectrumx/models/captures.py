"""Capture model for SpectrumX."""

from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Annotated
from typing import Any

from pydantic import UUID4
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator

from spectrumx.models.base import SDSModel
from spectrumx.models.capture_enums import CaptureOrigin
from spectrumx.models.capture_enums import CaptureType
from spectrumx.models.datasets import Dataset
from spectrumx.models.user import User
from spectrumx.models.user import UserSharePermission

_d_capture_created_at = "The time the capture was created"
_d_capture_props = "The indexed metadata for the capture"
_d_capture_type = f"The type of capture {', '.join([x.value for x in CaptureType])}"
_d_index_name = "The name of the SDS index associated with the capture"
_d_name = "The name of the capture"
_d_origin = "The origin of the capture"
_d_top_level_dir = "The top-level directory for the capture files"
_d_uuid = "The unique identifier for the capture"
_d_capture_files = "Files associated to this capture"
_d_owner = "The owner of the capture"
_d_share_permissions = "The share permissions for the capture"
_d_channel = "The channel associated with the capture. Only for RadioHound type."
_d_scan_group = "The scan group associated with the capture. Only for Digital-RF type."
_d_is_shared = "Whether the capture is shared"
_d_is_shared_with_me = "Whether the capture is shared with the current user"
_d_datasets = "Datasets this capture is associated with"
_d_capture_start_iso_utc = (
    "Indexed capture start from OpenSearch as ISO 8601 UTC (when available)"
)
_d_capture_end_iso_utc = "Indexed capture end from OpenSearch as ISO 8601 UTC"
_d_capture_start_display = (
    "Indexed capture start formatted for display (server/local timezone)"
)
_d_capture_end_display = (
    "Indexed capture end formatted for display (server/local timezone)"
)


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

    model_config = ConfigDict(extra="ignore")

    # TODO ownership: include ownership and access level information

    capture_props: Annotated[
        dict[str, Any],
        Field(description=_d_capture_props, default_factory=dict),
    ]
    capture_type: Annotated[CaptureType, Field(description=_d_capture_type)]
    index_name: Annotated[str, Field(max_length=255, description=_d_index_name)]
    origin: Annotated[CaptureOrigin, Field(description=_d_origin)]
    top_level_dir: Annotated[PurePosixPath, Field(description=_d_top_level_dir)]
    files: Annotated[
        list[CaptureFile],
        Field(description=_d_capture_files, default_factory=list),
    ]
    datasets: Annotated[
        list[Dataset], Field(description=_d_datasets, default_factory=list)
    ]
    owner: Annotated[User, Field(description=_d_owner)]
    share_permissions: Annotated[
        list[UserSharePermission],
        Field(description=_d_share_permissions, default_factory=list),
    ]
    is_shared: Annotated[bool, Field(description=_d_is_shared, default=False)]
    is_shared_with_me: Annotated[
        bool, Field(description=_d_is_shared_with_me, default=False)
    ]

    # optional fields
    created_at: Annotated[
        datetime | None, Field(description=_d_capture_created_at, default=None)
    ]
    name: Annotated[
        str | None, Field(max_length=255, description=_d_name, default=None)
    ]
    channel: Annotated[
        str | None, Field(max_length=255, description=_d_channel, default=None)
    ]
    scan_group: Annotated[UUID4 | None, Field(description=_d_scan_group, default=None)]
    capture_start_iso_utc: Annotated[
        str | None,
        Field(description=_d_capture_start_iso_utc, default=None),
    ]
    capture_end_iso_utc: Annotated[
        str | None,
        Field(description=_d_capture_end_iso_utc, default=None),
    ]
    capture_start_display: Annotated[
        str | None,
        Field(description=_d_capture_start_display, default=None),
    ]
    capture_end_display: Annotated[
        str | None,
        Field(description=_d_capture_end_display, default=None),
    ]

    @field_validator("capture_props", mode="before")
    @classmethod
    def _default_capture_props(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        return value

    @field_validator("files", mode="before")
    @classmethod
    def _default_files(cls, value: Any) -> list[CaptureFile] | list[dict[str, Any]]:
        if value is None:
            return []
        return value

    def __str__(self) -> str:
        """Get the string representation of the capture."""
        if self.name:
            return (
                f"Capture(uuid={self.uuid}, "
                f"files={len(self.files)}, "
                f"name={self.name}, "
                f"type={self.capture_type}, "
                "created_at="
                f"{self.created_at.isoformat() if self.created_at else None}, "
            )
        return (
            f"Capture(uuid={self.uuid}, "
            f"type={self.capture_type}, "
            f"files={len(self.files)}, "
            f"created_at={self.created_at.isoformat() if self.created_at else None})"
        )

    def __repr_name__(self) -> str:
        """Get the name of the capture for display."""
        return self.name or self.capture_type.value

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} {self.uuid} "
            f"files={len(self.files)}, "
            f"created_at={self.created_at}>"
        )


__all__ = [
    "Capture",
    "CaptureOrigin",
    "CaptureType",
]
