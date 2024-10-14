from django.contrib.auth import get_user_model
from rest_framework import serializers

from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "name"]


class FileGetSerializer(serializers.ModelSerializer):
    owner = UserSerializer()
    dataset = DatasetGetSerializer()
    capture = CaptureGetSerializer()

    class Meta:
        model = File
        fields = "__all__"


class FilePostSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = [
            "uuid",
            "file",
            "name",
            "directory",
            "media_type",
            "owner",
            "permissions",
            "size",
            "sum_blake3",
        ]
        read_only_fields = ["uuid", "size", "sum_blake3"]

    def create(self, validated_data):
        # Set the owner to the request user
        validated_data["owner"] = self.context["request_user"]
        validated_data["directory"] = (
            f"/files/{validated_data['owner'].email}/{validated_data["directory"]}/"
        )
        if "media_type" not in validated_data:
            validated_data["media_type"] = ""

        file_instance = File(**validated_data)
        file_instance.size = file_instance.file.size
        file_instance.name = file_instance.file.name
        file_instance.sum_blake3 = file_instance.calculate_checksum()
        file_instance.file.name = file_instance.sum_blake3

        file_instance.save()
        return file_instance

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            if attr != "file":
                setattr(instance, attr, value)

        if "file" in validated_data:
            new_file = validated_data["file"]

            # Calculate the checksum before deleting the old file
            checksum = instance.calculate_checksum(new_file)

            # Delete the old file
            instance.file.delete(save=False)

            # Assign the new file
            instance.file = new_file

            # Update the instance attributes
            instance.size = instance.file.size
            instance.name = instance.file.name
            instance.sum_blake3 = checksum
            instance.file.name = checksum

        instance.save()
        return instance
