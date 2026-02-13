"""Dataset serializers for the API methods."""

from rest_framework import serializers

from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import UserSharePermission


class DatasetGetSerializer(serializers.ModelSerializer[Dataset]):
    authors = serializers.SerializerMethodField()
    keywords = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%m/%d/%Y %H:%M:%S", read_only=True)
    is_shared_with_me = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    shared_users = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()
    permission_level = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_advance_version = serializers.SerializerMethodField()
    next_version = serializers.SerializerMethodField()

    def get_authors(self, obj):
        """Return the full authors list using the model's get_authors_display method."""
        return obj.get_authors_display()

    def get_keywords(self, obj):
        """Return a list of keyword names for the dataset."""
        return [kw.name for kw in obj.keywords.filter(is_deleted=False)]

    def get_is_shared_with_me(self, obj):
        """Check if the dataset is shared with the current user."""
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            return UserSharePermission.objects.filter(
                shared_with=request.user,
                item_type=ItemType.DATASET,
                item_uuid=obj.uuid,
                is_enabled=True,
                is_deleted=False,
            ).exists()
        return False

    def get_is_owner(self, obj):
        """Check if the current user is the owner of the dataset."""
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            return obj.owner == request.user
        return False

    def get_shared_users(self, obj):
        """Get users and groups who have access to this dataset."""
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            return []

        # Get all permissions on this dataset
        permissions = (
            UserSharePermission.objects.filter(
                item_type=ItemType.DATASET,
                item_uuid=obj.uuid,
                is_enabled=True,
                is_deleted=False,
            )
            .select_related("shared_with")
            .prefetch_related("share_groups__members", "share_groups__owner")
        )

        shared_users = []
        processed_groups = set()  # Track groups we've already added

        for perm in permissions:
            # Handle share groups
            for group in perm.share_groups.filter(is_deleted=False):
                if group.uuid not in processed_groups:
                    shared_users.append(
                        {
                            "id": group.uuid,
                            "name": group.name,
                            "email": f"group:{group.uuid}",
                            "type": "group",
                            "permission_level": perm.permission_level,
                            "member_count": group.members.count(),
                            "owner": group.owner.name or group.owner.email,
                            "is_group_owner": group.owner == request.user,
                            "members": [
                                {
                                    "name": member.name or member.email,
                                    "email": member.email,
                                }
                                for member in group.members.all()
                            ],
                        }
                    )
                    processed_groups.add(group.uuid)

            # Handle individual users (only if they don't have group access)
            if perm.shared_with and not perm.share_groups.exists():
                shared_users.append(
                    {
                        "id": perm.shared_with.id,
                        "name": perm.shared_with.name or perm.shared_with.email,
                        "email": perm.shared_with.email,
                        "type": "user",
                        "permission_level": perm.permission_level,
                    }
                )

        return shared_users

    def get_owner_name(self, obj):
        """Get the owner's display name."""
        return obj.owner.name if obj.owner else "Owner"

    def get_owner_email(self, obj):
        """Get the owner's email."""
        return obj.owner.email if obj.owner else ""

    def get_permission_level(self, obj):
        """Get the current user's permission level for this dataset."""
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            return None

        # Check if user is the owner
        if obj.owner == request.user:
            return PermissionLevel.OWNER

        # Check for shared permissions
        permission = UserSharePermission.objects.filter(
            shared_with=request.user,
            item_type=ItemType.DATASET,
            item_uuid=obj.uuid,
            is_enabled=True,
            is_deleted=False,
        ).first()

        return permission.permission_level if permission else None

    def get_can_edit(self, obj):
        """Check if the current user can edit this dataset."""
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            return False

        # Check if user is the owner
        if obj.owner == request.user:
            return True

        # Check for shared permissions that allow editing
        permission = UserSharePermission.objects.filter(
            shared_with=request.user,
            item_type=ItemType.DATASET,
            item_uuid=obj.uuid,
            is_enabled=True,
            is_deleted=False,
        ).first()

        if permission:
            return permission.permission_level in [PermissionLevel.CO_OWNER, PermissionLevel.CONTRIBUTOR]

        return False

    def get_can_advance_version(self, obj):
        """Check if the current user can advance the version of the dataset."""
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            return False

        # Check if user is the owner
        if obj.owner == request.user:
            return True

        # Check for shared permissions that allow advancing the version
        permission = UserSharePermission.objects.filter(
            shared_with=request.user,
            item_type=ItemType.DATASET,
            item_uuid=obj.uuid,
            is_enabled=True,
            is_deleted=False,
        ).first()

        if permission:
            return permission.permission_level == PermissionLevel.CO_OWNER

        return False

    def get_next_version(self, obj):
        """Get the next version of the dataset."""
        next_version = None
        if obj.next_version.exists():
            next_version_obj = obj.next_version.first()
            next_version = next_version_obj.version
        return next_version

    class Meta:
        model = Dataset
        fields = "__all__"
