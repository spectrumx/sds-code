"""Dataset serializers for the API methods."""

from rest_framework import serializers

from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission


class DatasetGetSerializer(serializers.ModelSerializer[Dataset]):
    authors = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%m/%d/%Y %H:%M:%S", read_only=True)
    is_shared_with_me = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    shared_users = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()
    permission_level = serializers.SerializerMethodField()

    def get_authors(self, obj):
        """Return the full authors list using the model's get_authors_display method."""
        return obj.get_authors_display()

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
        """Get users who have access to this dataset."""
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            return []
        
        # Get all users who have permissions on this dataset
        permissions = UserSharePermission.objects.filter(
            item_type=ItemType.DATASET,
            item_uuid=obj.uuid,
            is_enabled=True,
            is_deleted=False,
        ).select_related("shared_with")
        
        shared_users = []
        for perm in permissions:
            shared_users.append({
                "id": perm.shared_with.id,
                "name": perm.shared_with.name or perm.shared_with.email,
                "email": perm.shared_with.email,
                "permission_level": perm.permission_level,
            })
        
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
            return "owner"
            
        # Check for shared permissions
        permission = UserSharePermission.objects.filter(
            shared_with=request.user,
            item_type=ItemType.DATASET,
            item_uuid=obj.uuid,
            is_enabled=True,
            is_deleted=False,
        ).first()
        
        return permission.permission_level if permission else None

    class Meta:
        model = Dataset
        fields = "__all__"
