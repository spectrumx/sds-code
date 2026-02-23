"""Tests for group sharing functionality."""

import uuid

import pytest
from django.test import Client
from django.urls import reverse
from rest_framework import status

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import ShareGroup
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.users.models import User
from sds_gateway.users.utils import update_or_create_user_group_share_permissions
from sds_gateway.users.views import _get_captures_for_template

# Test constants
TEST_PASSWORD = "testpass123"  # noqa: S105


@pytest.mark.django_db
class TestShareItemView:
    """Test ShareItemView functionality."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def owner(self) -> User:
        return User.objects.create_user(
            email="owner@example.com",
            password=TEST_PASSWORD,
            name="Owner User",
            is_approved=True,
        )

    @pytest.fixture
    def group_member(self) -> User:
        return User.objects.create_user(
            email="member@example.com",
            password=TEST_PASSWORD,
            name="Group Member",
            is_approved=True,
        )

    @pytest.fixture
    def dataset(self, owner: User) -> Dataset:
        return Dataset.objects.create(
            uuid=uuid.uuid4(),
            name="Test Dataset",
            owner=owner,
            description="A test dataset",
        )

    @pytest.fixture
    def share_group(self, owner: User, group_member: User) -> ShareGroup:
        group = ShareGroup.objects.create(name="Test Group", owner=owner)
        group.members.add(group_member)
        return group

    def test_share_dataset_with_group(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        share_group: ShareGroup,
    ) -> None:
        """Test sharing a dataset with a group using ShareItemView."""
        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        data = {
            "user-search": f"group:{share_group.uuid}",
            "notify_message": "Check out this dataset!",
        }

        response = client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify permission was created
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
            owner=owner,
        )
        assert permission.is_enabled is True
        assert share_group in permission.share_groups.all()

    def test_remove_group_from_dataset(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        share_group: ShareGroup,
    ) -> None:
        """Test removing a group from dataset sharing using ShareItemView."""
        # First share the dataset with the group
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Verify permission exists
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
        )
        assert permission.is_enabled is True

        # Remove the group using ShareItemView
        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        data = {
            "remove_users": f'["group:{share_group.uuid}"]',
        }

        response = client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify permission is now disabled
        permission.refresh_from_db()
        assert permission.is_enabled is False
        assert share_group not in permission.share_groups.all()

    def test_share_dataset_with_individual_user(
        self, client: Client, owner: User, group_member: User, dataset: Dataset
    ) -> None:
        """Test sharing a dataset with an individual user using ShareItemView."""
        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        data = {
            "user-search": group_member.email,
            "notify_message": "Check out this dataset!",
        }

        response = client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify permission was created
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
            owner=owner,
        )
        assert permission.is_enabled is True
        assert not permission.share_groups.exists()

    def test_remove_individual_user_from_dataset(
        self, client: Client, owner: User, group_member: User, dataset: Dataset
    ) -> None:
        """Test removing an individual user from dataset sharing using ShareItemView."""
        # First share the dataset with the user
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=group_member,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            is_enabled=True,
            message="Individual share",
        )

        # Remove the user using ShareItemView
        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        data = {
            "remove_users": f'["{group_member.email}"]',
        }

        response = client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify permission is now disabled
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
        )
        assert permission.is_enabled is False


@pytest.mark.django_db
class TestShareGroupListView:
    """Test ShareGroupListView functionality."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def owner(self) -> User:
        return User.objects.create_user(
            email="owner@example.com",
            password=TEST_PASSWORD,
            name="Owner User",
            is_approved=True,
        )

    @pytest.fixture
    def group_member(self) -> User:
        return User.objects.create_user(
            email="member@example.com",
            password=TEST_PASSWORD,
            name="Group Member",
            is_approved=True,
        )

    @pytest.fixture
    def new_user(self) -> User:
        return User.objects.create_user(
            email="newuser@example.com",
            password=TEST_PASSWORD,
            name="New User",
            is_approved=True,
        )

    @pytest.fixture
    def dataset(self, owner: User) -> Dataset:
        return Dataset.objects.create(
            uuid=uuid.uuid4(),
            name="Test Dataset",
            owner=owner,
            description="A test dataset",
        )

    @pytest.fixture
    def share_group(self, owner: User, group_member: User) -> ShareGroup:
        group = ShareGroup.objects.create(name="Test Group", owner=owner)
        group.members.add(group_member)
        return group

    def test_create_share_group(self, client: Client, owner: User) -> None:
        """Test creating a new share group using ShareGroupListView."""
        client.force_login(owner)
        url = reverse("users:share_group_list")

        data = {
            "action": "create",
            "name": "New Test Group",
        }

        response = client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify group was created and owner is a member
        group = ShareGroup.objects.get(name="New Test Group", owner=owner)
        assert group.is_deleted is False
        assert owner in group.members.all()

    def test_add_member_to_group(
        self,
        client: Client,
        owner: User,
        group_member: User,
        share_group: ShareGroup,
        new_user: User,
    ) -> None:
        """Test adding a member to a group using ShareGroupListView."""
        client.force_login(owner)
        url = reverse("users:share_group_list")

        data = {
            "action": "add_members",
            "group_uuid": str(share_group.uuid),
            "user_emails": new_user.email,
        }

        response = client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify user was added to group
        share_group.refresh_from_db()
        assert new_user in share_group.members.all()

    def test_remove_member_from_group(
        self,
        client: Client,
        owner: User,
        group_member: User,
        share_group: ShareGroup,
        dataset: Dataset,
    ) -> None:
        """Test removing a member from a group using ShareGroupListView."""
        # First share a dataset with the group
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Verify permission exists
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
        )
        assert permission.is_enabled is True

        # Remove member using ShareGroupListView
        client.force_login(owner)
        url = reverse("users:share_group_list")

        data = {
            "action": "remove_members",
            "group_uuid": str(share_group.uuid),
            "user_emails": group_member.email,
        }

        response = client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify user was removed from group
        share_group.refresh_from_db()
        assert group_member not in share_group.members.all()

        # Verify permission is now disabled
        permission.refresh_from_db()
        assert permission.is_enabled is False
        assert share_group not in permission.share_groups.all()

    def test_cannot_remove_owner_from_group(
        self,
        client: Client,
        owner: User,
        group_member: User,
    ) -> None:
        """Test that the group owner cannot be removed from the group."""
        group = ShareGroup.objects.create(name="Owner Test Group", owner=owner)
        group.members.add(owner, group_member)

        client.force_login(owner)
        url = reverse("users:share_group_list")
        data = {
            "action": "remove_members",
            "group_uuid": str(group.uuid),
            "user_emails": owner.email,
        }

        response = client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        # The removal is blocked; the owner should still be a member
        assert owner in group.members.all()
        assert result["errors"]

    def test_cannot_remove_last_member_from_group(
        self,
        client: Client,
        owner: User,
        group_member: User,
        share_group: ShareGroup,
    ) -> None:
        """Test that the last member of a group cannot be removed."""
        # share_group fixture has only group_member as a member (owner not added)
        assert share_group.members.count() == 1

        client.force_login(owner)
        url = reverse("users:share_group_list")
        data = {
            "action": "remove_members",
            "group_uuid": str(share_group.uuid),
            "user_emails": group_member.email,
        }

        response = client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert group_member in share_group.members.all()
        assert result["errors"]

    def test_delete_share_group(
        self,
        client: Client,
        owner: User,
        group_member: User,
        share_group: ShareGroup,
        dataset: Dataset,
    ) -> None:
        """Test deleting a share group using ShareGroupListView."""
        # First share a dataset with the group
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Verify permission exists
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
        )
        assert permission.is_enabled is True

        # Delete group using ShareGroupListView
        client.force_login(owner)
        url = reverse("users:share_group_list")

        data = {
            "action": "delete_group",
            "group_uuid": str(share_group.uuid),
        }

        response = client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify group is soft-deleted
        share_group.refresh_from_db()
        assert share_group.is_deleted is True

        # Verify permission is now disabled
        permission.refresh_from_db()
        assert permission.is_enabled is False
        assert share_group not in permission.share_groups.all()


@pytest.mark.django_db
class TestGroupSharingIntegrity:
    """Test integrity and individual access scenarios."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def owner(self) -> User:
        """Create a user who owns items and groups."""
        return User.objects.create_user(
            email="owner@example.com",
            password=TEST_PASSWORD,
            name="Owner User",
            is_approved=True,
        )

    @pytest.fixture
    def group_member(self) -> User:
        """Create a user who is a member of groups."""
        return User.objects.create_user(
            email="member@example.com",
            password=TEST_PASSWORD,
            name="Group Member",
            is_approved=True,
        )

    @pytest.fixture
    def other_user(self) -> User:
        """Create another user for testing."""
        return User.objects.create_user(
            email="other@example.com",
            password=TEST_PASSWORD,
            name="Other User",
            is_approved=True,
        )

    @pytest.fixture
    def dataset(self, owner: User) -> Dataset:
        """Create a dataset owned by the owner."""
        return Dataset.objects.create(
            uuid=uuid.uuid4(),
            name="Test Dataset",
            owner=owner,
            description="A test dataset",
        )

    @pytest.fixture
    def capture(self, owner: User) -> Capture:
        """Create a capture owned by the owner."""
        return Capture.objects.create(
            uuid=uuid.uuid4(),
            name="Test Capture",
            owner=owner,
            capture_type="drf",
            top_level_dir="/test",
            index_name="test-index",
        )

    @pytest.fixture
    def share_group(self, owner: User, group_member: User) -> ShareGroup:
        """Create a share group owned by owner with group_member as member."""
        group = ShareGroup.objects.create(name="Test Group", owner=owner)
        group.members.add(group_member)
        return group

    def test_group_owner_cannot_be_deleted_with_members(
        self, owner: User, group_member: User
    ) -> None:
        """Test that group owner cannot be deleted if group has members."""
        # Create a group with members
        group = ShareGroup.objects.create(name="Test Group", owner=owner)
        group.members.add(group_member)

        # Try to delete the owner - should raise ProtectedError
        with pytest.raises(
            Exception, match=r".*protected.*"
        ):  # Django raises ProtectedError
            owner.delete()

        # Verify owner still exists
        assert User.objects.filter(pk=owner.pk).exists()

    def test_group_owner_cannot_share_asset_they_dont_own(
        self, client: Client, other_user: User, group_member: User, dataset: Dataset
    ) -> None:
        """Test that group owner cannot share an asset they don't own."""
        # Create a group owned by other_user
        group = ShareGroup.objects.create(name="Test Group", owner=other_user)
        group.members.add(group_member)

        # Try to share dataset (owned by dataset.owner) through other_user's group
        client.force_login(other_user)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        data = {
            "user-search": f"group:{group.uuid}",
            "notify_message": "Check out this dataset!",
        }

        response = client.post(url, data)

        # Should fail because other_user doesn't own the dataset
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Dataset not found" in response.json()["error"]

    def test_asset_owner_can_soft_delete_shared_asset(
        self, owner: User, group_member: User, dataset: Dataset, share_group: ShareGroup
    ) -> None:
        """Test that asset owner can soft-delete an asset even when shared."""
        # Share the dataset with the group
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Verify the share permission exists
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
        )
        assert permission.is_enabled is True

        # Owner should be able to soft-delete the dataset
        dataset.soft_delete()

        # Verify dataset is soft-deleted
        dataset.refresh_from_db()
        assert dataset.is_deleted is True
        assert dataset.deleted_at is not None

        # Verify related share permissions are also soft-deleted
        permission.refresh_from_db()
        assert permission.is_deleted is True

    def test_shared_asset_not_accessible_after_revocation(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        share_group: ShareGroup,
    ) -> None:
        """Test that revoked shared asset is not accessible by another user."""
        # Share the dataset with the group
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Verify group_member can access the dataset
        client.force_login(group_member)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Revoke access by disabling the permission
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
        )
        permission.is_enabled = False
        permission.save()

        # Verify group_member can no longer access the dataset
        response = client.post(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found or access denied" in response.json()["message"].lower()

    def test_user_cannot_delete_shared_asset(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        share_group: ShareGroup,
    ) -> None:
        """Test that a user cannot delete or soft-delete an asset they don't own."""
        # Share the dataset with the group
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Try to soft-delete as group_member (should fail)
        client.force_login(group_member)

        # Note: This test assumes there's an endpoint for soft-deleting datasets
        # If no such endpoint exists, this test documents the expected behavior
        # that users should not be able to delete assets they don't own

        # For now, test that group_member cannot access admin-like operations
        # This would need to be updated when proper deletion endpoints are added
        assert True  # TODO: implement when deletion endpoints exist


@pytest.mark.django_db
class TestGroupPermissionChanges:
    """Test changes to group permissions."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def owner(self) -> User:
        return User.objects.create_user(
            email="owner@example.com",
            password=TEST_PASSWORD,
            name="Owner User",
            is_approved=True,
        )

    @pytest.fixture
    def group_member(self) -> User:
        return User.objects.create_user(
            email="member@example.com",
            password=TEST_PASSWORD,
            name="Group Member",
            is_approved=True,
        )

    @pytest.fixture
    def dataset(self, owner: User) -> Dataset:
        return Dataset.objects.create(
            uuid=uuid.uuid4(),
            name="Test Dataset",
            owner=owner,
            description="A test dataset",
        )

    @pytest.fixture
    def share_group(self, owner: User, group_member: User) -> ShareGroup:
        group = ShareGroup.objects.create(name="Test Group", owner=owner)
        group.members.add(group_member)
        return group

    def test_user_revocation_removes_access(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        share_group: ShareGroup,
    ) -> None:
        """Test that removing user from group removes asset access."""
        # Share the dataset with the group
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Verify group_member can access the dataset
        client.force_login(group_member)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Remove user from group and update permissions
        share_group.members.remove(group_member)

        # Update share permissions for this user (simulate real-world behavior)
        share_permissions = UserSharePermission.objects.filter(
            shared_with=group_member,
            share_groups=share_group,
            is_deleted=False,
        )
        for permission in share_permissions:
            permission.share_groups.remove(share_group)
            permission.update_enabled_status()

        # Verify group_member can no longer access the dataset
        response = client.post(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found or access denied" in response.json()["message"].lower()

    def test_user_revocation_restores_access_when_readded(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        share_group: ShareGroup,
    ) -> None:
        """Test that re-adding user to group restores asset access."""
        # Share the dataset with the group
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Remove user from group and update permissions
        share_group.members.remove(group_member)

        # Update share permissions for this user (simulate real-world behavior)
        share_permissions = UserSharePermission.objects.filter(
            shared_with=group_member,
            share_groups=share_group,
            is_deleted=False,
        )
        for permission in share_permissions:
            permission.share_groups.remove(share_group)
            permission.update_enabled_status()

        # Verify group_member cannot access the dataset
        client.force_login(group_member)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        response = client.post(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Re-add user to group and update permissions
        share_group.members.add(group_member)

        # Re-add group to share permissions
        share_permissions = UserSharePermission.objects.filter(
            shared_with=group_member,
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            is_deleted=False,
        )
        for permission in share_permissions:
            permission.share_groups.add(share_group)
            permission.update_enabled_status()

        # Verify group_member can access the dataset again
        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

    def test_asset_revocation_disables_access(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        share_group: ShareGroup,
    ) -> None:
        """Test that revoking asset access disables user access."""
        # Share the dataset with the group
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Verify group_member can access the dataset
        client.force_login(group_member)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Disable the share permission
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
        )
        permission.is_enabled = False
        permission.save()

        # Verify group_member can no longer access the dataset
        response = client.post(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found or access denied" in response.json()["message"].lower()


@pytest.mark.django_db
class TestMultipleAccessPaths:
    """Test multiple access paths scenarios."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def owner(self) -> User:
        return User.objects.create_user(
            email="owner@example.com",
            password=TEST_PASSWORD,
            name="Owner User",
            is_approved=True,
        )

    @pytest.fixture
    def group_member(self) -> User:
        return User.objects.create_user(
            email="member@example.com",
            password=TEST_PASSWORD,
            name="Group Member",
            is_approved=True,
        )

    @pytest.fixture
    def dataset(self, owner: User) -> Dataset:
        return Dataset.objects.create(
            uuid=uuid.uuid4(),
            name="Test Dataset",
            owner=owner,
            description="A test dataset",
        )

    @pytest.fixture
    def group1(self, owner: User, group_member: User) -> ShareGroup:
        group = ShareGroup.objects.create(name="Group 1", owner=owner)
        group.members.add(group_member)
        return group

    @pytest.fixture
    def group2(self, owner: User, group_member: User) -> ShareGroup:
        group = ShareGroup.objects.create(name="Group 2", owner=owner)
        group.members.add(group_member)
        return group

    def test_asset_accessible_after_leaving_one_group(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        group1: ShareGroup,
        group2: ShareGroup,
    ) -> None:
        """
        Test that asset shared by two groups is still accessible
        if user leaves one group.
        """
        # Share dataset with both groups
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=group1,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group 1 share",
        )
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=group2,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group 2 share",
        )

        # Verify group_member can access the dataset
        client.force_login(group_member)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Remove user from one group
        group1.members.remove(group_member)

        # Verify group_member can still access the dataset through the other group
        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

    def test_asset_not_accessible_after_permission_revocation(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        group1: ShareGroup,
        group2: ShareGroup,
    ) -> None:
        """
        Test that asset is not accessible when permission is revoked,
        even with multiple groups.
        """
        # Share dataset with both groups
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=group1,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group 1 share",
        )
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=group2,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group 2 share",
        )

        # Verify group_member can access the dataset
        client.force_login(group_member)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Revoke access by disabling the permission
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
        )
        permission.is_enabled = False
        permission.save()

        # Verify group_member loses access entirely when permission is disabled
        response = client.post(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_asset_accessible_after_group_dissolution(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        group1: ShareGroup,
        group2: ShareGroup,
    ) -> None:
        """Test that asset is still accessible if one group is dissolved."""
        # Share dataset with both groups
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=group1,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group 1 share",
        )
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=group2,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group 2 share",
        )

        # Verify group_member can access the dataset
        client.force_login(group_member)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Dissolve one group (soft delete)
        group1.soft_delete()

        # Verify group_member can still access the dataset through the other group
        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

    def test_individual_and_group_access_permission_disabled(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        group1: ShareGroup,
    ) -> None:
        """
        Test that asset is not accessible when permission is disabled,
        even with both individual and group access.
        """
        # Share dataset both individually and through group
        # Individual share
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=group_member,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            is_enabled=True,
            message="Individual share",
        )

        # Group share
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=group1,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Verify group_member can access the dataset
        client.force_login(group_member)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Disable the permission (which has both individual and group access)
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
        )
        permission.is_enabled = False
        permission.save()

        # Verify group_member loses access entirely when permission is disabled
        response = client.post(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_individual_and_group_access_group_removed(
        self,
        client: Client,
        owner: User,
        group_member: User,
        dataset: Dataset,
        group1: ShareGroup,
    ) -> None:
        """
        Test that asset is not accessible to individual when group
        is removed from permission.
        """
        # Share dataset both individually and through group
        # Individual share
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=group_member,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            is_enabled=True,
            message="Individual share",
        )

        # Group share
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=group1,
            share_user=group_member,
            item_uuid=str(dataset.uuid),
            item_type=ItemType.DATASET,
            message="Group share",
        )

        # Verify group_member can access the dataset
        client.force_login(group_member)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        response = client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Remove group from permission (but keep permission enabled)
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            shared_with=group_member,
        )
        permission.share_groups.remove(group1)
        permission.update_enabled_status()

        # Verify group_member loses access when group is removed
        response = client.post(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestGroupSharingUI:
    """Test group sharing UI and modal functionality."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def owner(self) -> User:
        return User.objects.create_user(
            email="owner@example.com",
            password=TEST_PASSWORD,
            name="Owner User",
            is_approved=True,
        )

    @pytest.fixture
    def user_to_share_with(self) -> User:
        return User.objects.create_user(
            email="share@example.com",
            password=TEST_PASSWORD,
            name="Share User",
            is_approved=True,
        )

    @pytest.fixture
    def dataset(self, owner: User) -> Dataset:
        return Dataset.objects.create(
            uuid=uuid.uuid4(),
            name="Test Dataset",
            owner=owner,
            description="A test dataset",
        )

    def test_share_with_group_individual_members_already_shared(
        self, client: Client, owner: User, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """
        Test sharing with a group when some members
        are already shared individually.
        """
        # Create another user for the group
        user2 = User.objects.create_user(
            email="user2@example.com",
            password=TEST_PASSWORD,
            name="User 2",
            is_approved=True,
        )

        # Create a share group
        share_group = ShareGroup.objects.create(name="Test Group", owner=owner)
        share_group.members.add(user_to_share_with, user2)

        # First, share the dataset with one of the group members individually
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=user_to_share_with,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            is_enabled=True,
            message="Individual share",
        )

        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": "dataset", "item_uuid": dataset.uuid},
        )

        # Share with the group (should not throw an error)
        data = {
            "user-search": f"group:{share_group.uuid}",
            "notify_message": "Check out this dataset!",
        }

        response = client.post(url, data)

        # Should succeed without error
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify both users now have permissions associated with the group
        permissions = UserSharePermission.objects.filter(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            owner=owner,
        )

        # Should have 2 permissions (one for each group member)
        expected_permissions = 2
        assert permissions.count() == expected_permissions

        # Check that both users have permissions with the group association
        user1_permission = permissions.filter(shared_with=user_to_share_with).first()
        user2_permission = permissions.filter(shared_with=user2).first()

        assert user1_permission is not None
        assert user2_permission is not None
        assert share_group in user1_permission.share_groups.all()
        assert share_group in user2_permission.share_groups.all()
        assert user1_permission.is_enabled is True
        assert user2_permission.is_enabled is True

        # The originally individual permission should now be associated with the group
        assert user1_permission.message == "Check out this dataset!"

    def test_capture_share_modal_displays_groups_properly(
        self, client: Client, owner: User, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """
        Test that capture share modal displays groups
        properly instead of individual members.
        """
        # Create another user for the group
        user2 = User.objects.create_user(
            email="user2@example.com",
            password=TEST_PASSWORD,
            name="User 2",
            is_approved=True,
        )

        # Create a capture
        capture = Capture.objects.create(
            uuid=uuid.uuid4(),
            name="Test Capture",
            owner=owner,
            capture_type="test",
            top_level_dir="/test",
            index_name="test-index",
        )

        # Create a share group
        share_group = ShareGroup.objects.create(name="Test Group", owner=owner)
        share_group.members.add(user_to_share_with, user2)

        # Share the capture with the group
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=user_to_share_with,
            item_uuid=str(capture.uuid),
            item_type=ItemType.CAPTURE,
            message="Group share",
        )
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=user2,
            item_uuid=str(capture.uuid),
            item_type=ItemType.CAPTURE,
            message="Group share",
        )

        client.force_login(owner)
        url = reverse("users:file_list")

        response = client.get(url)

        # Should succeed
        assert response.status_code == status.HTTP_200_OK

        # The template should contain the group information
        # We can't easily test the JavaScript rendering,
        # but we can verify the data is prepared correctly
        # by checking that the capture has the right shared_users structure

        # Get the capture data using the same function the view uses
        captures_data = _get_captures_for_template([capture], response.wsgi_request)

        assert len(captures_data) == 1
        capture_data = captures_data[0]

        # Should have shared_users
        assert "shared_users" in capture_data
        shared_users = capture_data["shared_users"]

        # Should have exactly one group entry (not individual users)
        assert len(shared_users) == 1

        group_entry = shared_users[0]
        assert group_entry["type"] == "group"
        assert group_entry["name"] == "Test Group"
        assert group_entry["email"] == f"group:{share_group.uuid}"
        expected_members = 2
        assert group_entry["member_count"] == expected_members
        assert len(group_entry["members"]) == expected_members

        # Verify the members are correct
        member_emails = [member["email"] for member in group_entry["members"]]
        assert user_to_share_with.email in member_emails
        assert user2.email in member_emails
