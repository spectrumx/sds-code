from django.contrib.auth import get_user_model
from rest_framework import serializers

from sds_gateway.api_methods.models import UserSharePermission

User = get_user_model()


class UserGetSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "email", "name"]

class UserSharePermissionSerializer(serializers.ModelSerializer[UserSharePermission]):
    class Meta:
        model = UserSharePermission
        fields = ["item_type", "item_uuid", "shared_with", "permission_level"]