"""Navigation models for file system browsing."""

from dataclasses import dataclass
from enum import StrEnum

# Constants for path parsing
MIN_PATH_PARTS_FOR_UUID = 2


class NavigationType(StrEnum):
    """Types of navigation contexts in the file system."""

    ROOT = "root"
    CAPTURE = "capture"
    DATASET = "dataset"
    UNKNOWN = "unknown"


@dataclass
class NavigationContext:
    """Represents the current navigation context in the file system."""

    type: NavigationType
    capture_uuid: str | None = None
    dataset_uuid: str | None = None
    subpath: str = ""

    @classmethod
    def from_path(cls, path: str) -> "NavigationContext":
        """
        Parse a file system path into a navigation context.

        Args:
            path: The current directory path (e.g., "/", "/captures/uuid",
                  "/datasets/uuid")

        Returns:
            NavigationContext: The parsed navigation context
        """
        if path == "/":
            return cls(type=NavigationType.ROOT)

        # Remove leading/trailing slashes and split
        parts = path.strip("/").split("/")

        if not parts:
            return cls(type=NavigationType.ROOT)

        if parts[0] == "captures" and len(parts) >= MIN_PATH_PARTS_FOR_UUID:
            capture_uuid = parts[1]
            subpath = (
                "/".join(parts[2:]) if len(parts) > MIN_PATH_PARTS_FOR_UUID else ""
            )
            return cls(
                type=NavigationType.CAPTURE, capture_uuid=capture_uuid, subpath=subpath
            )

        if parts[0] == "datasets" and len(parts) >= MIN_PATH_PARTS_FOR_UUID:
            dataset_uuid = parts[1]
            subpath = (
                "/".join(parts[2:]) if len(parts) > MIN_PATH_PARTS_FOR_UUID else ""
            )
            return cls(
                type=NavigationType.DATASET, dataset_uuid=dataset_uuid, subpath=subpath
            )

        return cls(type=NavigationType.UNKNOWN)

    def to_path(self) -> str:
        """
        Convert the navigation context back to a path string.

        Returns:
            str: The path representation of this context
        """
        if self.type == NavigationType.ROOT:
            return "/"

        if self.type == NavigationType.CAPTURE and self.capture_uuid:
            path = f"/captures/{self.capture_uuid}"
            if self.subpath:
                path += f"/{self.subpath}"
            return path

        if self.type == NavigationType.DATASET and self.dataset_uuid:
            path = f"/datasets/{self.dataset_uuid}"
            if self.subpath:
                path += f"/{self.subpath}"
            return path

        return "/"
