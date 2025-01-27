"""Dataset model for SpectrumX."""

from pydantic import UUID4
from pydantic import BaseModel


class Dataset(BaseModel):
    """A dataset in SDS."""

    uuid: UUID4 | None = None


__all__ = [
    "Dataset",
]
