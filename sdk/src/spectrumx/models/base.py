from pydantic import UUID4
from pydantic import BaseModel


class SDSModel(BaseModel):
    """Base class for most models in SDS."""

    uuid: UUID4 | None = None

    def __repr_name__(self) -> str:
        """Get the name to use in the representation of the model."""
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} uuid={self.uuid}>"
