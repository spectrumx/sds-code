from typing import Annotated
from enum import StrEnum

from pydantic import Field
from pydantic import UUID4

from spectrumx.models.base import SDSModel


_d_name = "The name of the user"
_d_email = "The email of the user"
_d_item_type = "The type of the item being shared"
_d_item_uuid = "The UUID of the item being shared"
_d_shared_with = "The user who is being shared with"
_d_permission = "The permission level of the user share permission"


class ItemType(StrEnum):
    """The type of the item being shared."""

    DATASET = "dataset"
    CAPTURE = "capture"


class PermissionLevel(StrEnum):
    """The permission level of a user share permission."""

    CO_OWNER = "co-owner"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"

    @classmethod
    def _missing_(cls, value: object) -> "PermissionLevel":
        return cls.VIEWER


class User(SDSModel):
    """A user in SDS."""

    name: Annotated[str, Field(description=_d_name)]
    email: Annotated[str, Field(description=_d_email)]


class UserSharePermission(SDSModel):
    """A user share permission in SDS."""

    item_type: Annotated[ItemType, Field(description=_d_item_type)]
    item_uuid: Annotated[UUID4, Field(description=_d_item_uuid)]
    shared_with: Annotated[User, Field(description=_d_shared_with)]
    permission_level: Annotated[PermissionLevel, Field(description=_d_permission)]