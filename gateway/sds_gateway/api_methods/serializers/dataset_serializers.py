"""Dataset serializers for the API methods."""

import json

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
    keywords = serializers.SerializerMethodField()

    def get_authors(self, obj):
        return obj.authors[0] if obj.authors else None

    def get_keywords(self, obj):
        """
        Return keywords as a clean list of strings, ready for frontend display.
        Handles all formats: JSON string, list, or empty.
        """
        if not obj.keywords:
            return []

        # If it's already a list (from from_db deserialization), return it
        if isinstance(obj.keywords, list):
            return [str(k).strip() for k in obj.keywords if k and str(k).strip()]

        # If it's a string, try to parse it
        if isinstance(obj.keywords, str):
            trimmed = obj.keywords.strip()
            if not trimmed:
                return []

            # Try to parse as JSON
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, list):
                    return [str(k).strip() for k in parsed if k and str(k).strip()]
            except (json.JSONDecodeError, TypeError):
                # If JSON parsing fails, treat as comma-separated string
                return [k.strip() for k in trimmed.split(",") if k.strip()]

        return []

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
