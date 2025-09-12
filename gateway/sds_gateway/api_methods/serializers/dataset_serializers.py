"""Dataset serializers for the API methods."""

from rest_framework import serializers

from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission


class DatasetGetSerializer(serializers.ModelSerializer[Dataset]):
    authors = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    is_shared_with_me = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    def get_authors(self, obj):
        return obj.authors[0] if obj.authors else None

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

    class Meta:
        model = Dataset
        fields = "__all__"
