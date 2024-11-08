"""File serializers for the SDS Gateway API methods."""

import logging
from pathlib import Path
from pathlib import PurePosixPath

from rest_framework import serializers

from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer
from sds_gateway.api_methods.serializers.user_serializer import UserGetSerializer
from sds_gateway.users.models import User

BAD_REQUEST = 400
CONFLICT = 409


class FileGetSerializer(serializers.ModelSerializer[File]):
    owner = UserGetSerializer()
    dataset = DatasetGetSerializer()
    capture = CaptureGetSerializer()
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    # add @property-ies as read-only fields
    user_directory = serializers.CharField(read_only=True)

    class Meta:
        model = File
        fields = (
            "bucket_name",
            "capture",
            "created_at",
            "dataset",
            "directory",
            "expiration_date",
            "file",
            "media_type",
            "name",
            "owner",
            "permissions",
            "size",
            "sum_blake3",
            "updated_at",
            "user_directory",
            "uuid",
        )


class FilePostSerializer(serializers.ModelSerializer[File]):
    class Meta:
        model = File
        fields = [
            "uuid",
            "created_at",
            "directory",
            "expiration_date",
            "file",
            "media_type",
            "name",
            "owner",
            "permissions",
            "size",
            "sum_blake3",
            "updated_at",
        ]
        read_only_fields = ["uuid"]
        user_mutable_fields = ["name", "directory", "media_type", "permissions"]

    def is_valid(self, *, raise_exception: bool = True) -> bool:
        """Checks if the data is valid."""
        # initial data must have 'file' and 'metadata'
        if not self.initial_data:
            self._errors = {
                "detail": [
                    "No data provided.",
                ],
            }
            return super().is_valid(raise_exception=raise_exception)

        for field in ["file", "metadata"]:
            if field not in self.initial_data:
                self._errors = {
                    field: [
                        "This field is required.",
                    ],
                }
            return super().is_valid(raise_exception=raise_exception)

        # check required metadata fields
        required_fields = [*self.Meta.user_mutable_fields]
        for field in required_fields:
            logging.info(
                "Checking if %s is in initial metadata: %s",
                field,
                self.initial_data["metadata"],
            )
            if field not in self.initial_data["metadata"]:
                self._errors = {
                    f'metadata["{field}"]': [
                        "This field is required.",
                    ],
                }

        return super().is_valid(raise_exception=raise_exception)

    def create(self, validated_data) -> File:
        # Set the owner to the request user
        validated_data["owner"] = self.context["request_user"]
        user_files_dir = f"/files/{validated_data['owner'].email}"

        # Ensure directory is not a relative path
        if not PurePosixPath(validated_data["directory"]).is_absolute():
            raise serializers.ValidationError(
                {"detail": "Relative paths are not allowed."},
                code=str(BAD_REQUEST),
            )

        # ensure the resolved path is within the user's files directory
        validated_data["directory"] = f"{user_files_dir}{validated_data["directory"]}/"
        resolved_dir = Path(validated_data["directory"]).resolve(strict=False)
        resolved_user_files_dir = Path(user_files_dir).resolve(strict=False)
        if not resolved_dir.is_relative_to(resolved_user_files_dir):
            raise serializers.ValidationError(
                {
                    "detail": f"The provided directory must be in the user's files directory: {user_files_dir}",  # noqa: E501
                },
                code=str(BAD_REQUEST),
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
                code=str(CONFLICT),
            )

        validated_data["sum_blake3"] = checksum
        logging.warning("File media type: %s", type(validated_data["file"]))
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

    def update(self, instance, validated_data) -> File:
        attrs_to_change = {
            key: value
            for key, value in validated_data.items()
            if key in self.Meta.user_mutable_fields
        }

        # media type is immutable after it's set once, so we disallow changing it
        if instance.media_type != "" and "media_type" in attrs_to_change:
            attrs_to_change.pop("media_type")

        for attr, value in attrs_to_change.items():
            setattr(instance, attr, value)

        return instance

    def check_file_contents_exist(
        self,
        user: User,
        directory: str,
        name: str,
        blake3_sum: str,
        request_data: dict[str, str],
    ) -> dict[str, bool]:
        """Checks if SDS already has the contents of this file.

        Args:
            user:           The requesting user.
            directory:      The virtual directory of the file in SDS.
            name:           The name of the file.
            blake3_sum:     The blake3 checksum of the file contents.
            request_data:   The request data.
        Returns:
            A dictionary with the following flags:
                - file_contents_exist_for_user: True / False.
                - file_exists_in_tree: True / False.
                - user_mutable_attributes_differ: True / False.
        """
        identical_user_owned_file = File.objects.filter(
            owner=user,
            sum_blake3=blake3_sum,
        )
        file_contents_exist_for_user = identical_user_owned_file.exists()
        existing_file = identical_user_owned_file.filter(
            directory=directory,
            name=name,
        ).first()

        if existing_file is None:
            # attrs always differ when the file doesn't exist
            user_mutable_attributes_differ = True
        else:
            # check mutable attributes between existing file and request data
            user_mutable_attributes_differ = False
            for attr in self.Meta.user_mutable_fields:
                if (
                    attr in request_data
                    and getattr(existing_file, attr) != request_data[attr]
                ):
                    user_mutable_attributes_differ = True
                    break

        return {
            "file_contents_exist_for_user": file_contents_exist_for_user,
            "file_exists_in_tree": existing_file is not None,
            "user_mutable_attributes_differ": user_mutable_attributes_differ,
        }


class FileCheckResponseSerializer(serializers.Serializer[File]):
    """Serializer for the response of the file check endpoint."""

    file_contents_exist_for_user = serializers.BooleanField()
    file_exists_in_tree = serializers.BooleanField()
    user_mutable_attributes_differ = serializers.BooleanField()
