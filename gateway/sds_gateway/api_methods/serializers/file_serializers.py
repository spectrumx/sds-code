from pathlib import Path
from pathlib import PurePosixPath

from rest_framework import serializers

from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer
from sds_gateway.api_methods.serializers.user_serializer import UserSerializer


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
        read_only_fields = ["uuid"]
        user_mutable_fields = ["name", "directory", "media_type", "permissions"]

    def create(self, validated_data):
        # Set the owner to the request user
        validated_data["owner"] = self.context["request_user"]
        user_files_dir = f"/files/{validated_data['owner'].email}"

        # Ensure directory is not a relative path
        if not PurePosixPath(validated_data["directory"]).is_absolute():
            raise serializers.ValidationError(
                {"detail": "Relative paths are not allowed."},
                code=400,
            )

        # Prepend the user's files directory to the directory
        validated_data["directory"] = f"{user_files_dir}{validated_data["directory"]}/"

        # Resolve the directory to an absolute path
        resolved_dir = Path(validated_data["directory"]).resolve(strict=False)

        # Ensure the resolved path is within the user's files directory
        resolved_user_files_dir = Path(user_files_dir).resolve(strict=False)
        if not resolved_dir.is_relative_to(resolved_user_files_dir):
            raise serializers.ValidationError(
                {
                    "detail": f"The provided directory must be in the user's files directory: {user_files_dir}",  # noqa: E501
                },
                code=400,
            )

        if "media_type" not in validated_data:
            validated_data["media_type"] = ""

        checksum = File().calculate_checksum(validated_data["file"])

        file_exists_in_tree = File.objects.filter(
            sum_blake3=checksum,
            directory=validated_data["directory"],
            name=validated_data["file"].name,
        ).exists()

        existing_file_instance = File.objects.filter(
            sum_blake3=checksum,
        ).first()

        if file_exists_in_tree:
            # return a 409 Conflict status code if the file already exists
            raise serializers.ValidationError(
                {
                    "detail": "File with checksum already exists in the tree, run PATCH instead.",  # noqa: E501
                },
                code=409,
            )

        validated_data["sum_blake3"] = checksum
        if existing_file_instance:
            validated_data["file"] = existing_file_instance.file
            validated_data["size"] = existing_file_instance.size
            validated_data["name"] = existing_file_instance.name
        else:
            validated_data["size"] = validated_data["file"].size
            validated_data["name"] = validated_data["file"].name
            validated_data["file"].name = validated_data["sum_blake3"]
        file_instance = File(**validated_data)

        file_instance.save()
        return file_instance

    def update(self, instance, validated_data):
        mutable_data = {
            key: value
            for key, value in validated_data.items()
            if key in self.Meta.user_mutable_fields
        }

        # remove media type from mutable data if the instance.media_type is not ""
        if instance.media_type != "" and "media_type" in mutable_data:
            mutable_data.pop("media_type")

        for attr, value in mutable_data.items():
            setattr(instance, attr, value)

        return instance

    def check_file_conditions(
        self,
        user,
        directory,
        name,
        checksum,
        request_data,
    ):
        # Check if file contents exist under this user
        file_contents_exist_for_user = File.objects.filter(
            owner=user,
            sum_blake3=checksum,
        ).exists()

        # Check if combination of file directory, name, and checksum already exists under this user # noqa: E501
        file_exists_in_tree = File.objects.filter(
            directory=directory,
            name=name,
            sum_blake3=checksum,
        ).exists()

        # Check if any of the attributes provided differ from the user-mutable ones in the database # noqa: E501
        instance = File.objects.filter(
            owner=user,
            directory=directory,
            name=name,
            sum_blake3=checksum,
        ).first()
        user_mutable_attributes_differ = False
        if instance:
            for attr in self.Meta.user_mutable_fields:
                # Skip media_type if the instance.media_type is not ""
                if attr == "media_type" and instance.media_type != "":
                    pass

                if (
                    attr in request_data
                    and getattr(instance, attr) != request_data[attr]
                ):
                    user_mutable_attributes_differ = True
                    break

        return {
            "file_contents_exist_for_user": file_contents_exist_for_user,
            "file_exists_in_tree": file_exists_in_tree,
            "user_mutable_attributes_differ": user_mutable_attributes_differ,
        }
