"""Tests for the User model and related enums."""

import uuid

import pytest
from pydantic import ValidationError
from spectrumx.models.user import ItemType
from spectrumx.models.user import PermissionLevel
from spectrumx.models.user import User
from spectrumx.models.user import UserSharePermission


class TestPermissionLevel:
    """Tests for PermissionLevel enum."""

    def test_missing_returns_viewer(self) -> None:
        """PermissionLevel._missing_() returns VIEWER for unknown value."""
        assert PermissionLevel._missing_("unknown") == PermissionLevel.VIEWER

    def test_missing_called_via_constructor(self) -> None:
        """PermissionLevel('unknown') returns VIEWER for unknown value."""
        assert PermissionLevel("unknown") == PermissionLevel.VIEWER

    def test_co_owner(self) -> None:
        """PermissionLevel.CO_OWNER == 'co-owner'."""
        assert PermissionLevel.CO_OWNER == "co-owner"

    def test_contributor(self) -> None:
        """PermissionLevel.CONTRIBUTOR == 'contributor'."""
        assert PermissionLevel.CONTRIBUTOR == "contributor"

    def test_viewer(self) -> None:
        """PermissionLevel.VIEWER == 'viewer'."""
        assert PermissionLevel.VIEWER == "viewer"

    @pytest.mark.parametrize(
        "member",
        list(PermissionLevel),
        ids=[m.name for m in PermissionLevel],
    )
    def test_value_round_trips_through_constructor(
        self, member: PermissionLevel
    ) -> None:
        """Serialization round-trip: ``PermissionLevel(member.value) is member``."""
        assert PermissionLevel(member.value) is member


class TestItemType:
    """Tests for ItemType enum."""

    def test_dataset(self) -> None:
        """ItemType.DATASET == 'dataset'."""
        assert ItemType.DATASET == "dataset"

    def test_capture(self) -> None:
        """ItemType.CAPTURE == 'capture'."""
        assert ItemType.CAPTURE == "capture"

    @pytest.mark.parametrize("member", list(ItemType), ids=[m.name for m in ItemType])
    def test_value_round_trips_through_constructor(self, member: ItemType) -> None:
        """Serialization round-trip: ``ItemType(member.value) is member``."""
        assert ItemType(member.value) is member

    def test_invalid_value_raises_value_error(self) -> None:
        """Error path: an unknown serialization value raises ValueError."""
        with pytest.raises(ValueError, match="is not a valid ItemType"):
            ItemType("invalid")  # type: ignore[arg-type]


class TestUser:
    """Tests for the User model."""

    def test_create_with_name_and_email(self) -> None:
        """User constructs with name/email and defaults uuid to None."""
        user = User(name="Test User", email="test@example.com")
        assert user.name == "Test User"
        assert user.email == "test@example.com"
        assert user.uuid is None

    def test_create_with_defaults(self) -> None:
        """User created with no args has all fields as None."""
        user = User.model_validate({})
        assert user.name is None
        assert user.email is None
        assert user.uuid is None

    def test_extra_fields_are_ignored(self) -> None:
        """User ignores unknown fields per its ``extra="ignore"`` config."""
        user = User.model_validate({"name": "x", "email": "y", "spam": "ignored"})
        assert user.name == "x"
        assert user.email == "y"
        assert not hasattr(user, "spam")


class TestUserSharePermission:
    """Tests for the UserSharePermission model."""

    def _shared_with(self) -> User:
        return User(name="Sharee", email="sharee@example.com")

    def test_valid_construction(self) -> None:
        """UserSharePermission constructs with all required fields."""
        item_uid = uuid.uuid4()
        perm = UserSharePermission(
            item_type=ItemType.DATASET,
            item_uuid=item_uid,
            shared_with=self._shared_with(),
            permission_level=PermissionLevel.CO_OWNER,
        )
        assert perm.item_type is ItemType.DATASET
        assert perm.item_uuid == item_uid
        assert perm.shared_with.name == "Sharee"
        assert perm.permission_level is PermissionLevel.CO_OWNER

    def test_item_type_coerced_from_string(self) -> None:
        """item_type accepts string serialization value and coerces to enum."""
        perm = UserSharePermission.model_validate(
            {
                "item_type": "capture",
                "item_uuid": uuid.uuid4(),
                "shared_with": self._shared_with(),
                "permission_level": "co-owner",
            }
        )
        assert perm.item_type is ItemType.CAPTURE
        assert perm.permission_level is PermissionLevel.CO_OWNER

    def test_missing_shared_with_raises_validation_error(self) -> None:
        """Omitting the required ``shared_with`` field raises ValidationError."""
        with pytest.raises(ValidationError):
            UserSharePermission(
                item_type=ItemType.DATASET,
                item_uuid=uuid.uuid4(),
                permission_level=PermissionLevel.VIEWER,
            )  # type: ignore[call-arg]

    def test_missing_item_uuid_raises_validation_error(self) -> None:
        """Omitting the required ``item_uuid`` field raises ValidationError."""
        with pytest.raises(ValidationError):
            UserSharePermission(
                item_type=ItemType.DATASET,
                shared_with=self._shared_with(),
                permission_level=PermissionLevel.VIEWER,
            )  # type: ignore[call-arg]
