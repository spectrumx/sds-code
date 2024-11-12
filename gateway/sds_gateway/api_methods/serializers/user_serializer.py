from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserGetSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "email", "name"]
