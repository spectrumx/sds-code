from pydantic import UUID4
from pydantic import BaseModel


class SDSModel(BaseModel):
    """Base class for most models in SDS."""

    uuid: UUID4 | None = None
