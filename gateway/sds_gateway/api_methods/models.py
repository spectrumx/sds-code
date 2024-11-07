"""Describes the models for the API methods."""

import datetime
import json
import uuid

from blake3 import blake3 as Blake3  # noqa: N812
from django.conf import settings
from django.db import models


def default_expiration_date() -> datetime.date:
    """Returns the default expiration date for a file."""
    # 2 years from now
    return (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=730)).date()


class BaseModel(models.Model):
    """
    Superclass for all models in the API methods app.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Allows this class to be abstract."""

        abstract = True


class File(BaseModel):
    """
    Model to define files uploaded through the API.
    """

    deleted_at = models.DateTimeField(blank=True, null=True)
    directory = models.CharField(max_length=2048, default="files/")
    expiration_date = models.DateField(default=default_expiration_date)
    file = models.FileField(upload_to="files/")
    is_deleted = models.BooleanField(default=False)
    media_type = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255, blank=True)
    permissions = models.CharField(max_length=9, default="rw-r--r--")
    size = models.IntegerField(blank=True)
    sum_blake3 = models.CharField(max_length=64, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name="files",
        on_delete=models.PROTECT,  # prevents users from being deleted if they own files (delete the files first). # noqa: E501
    )
    bucket_name = models.CharField(
        max_length=255,
        default=settings.AWS_STORAGE_BUCKET_NAME,
    )
    dataset = models.ForeignKey(
        "Dataset",
        blank=True,
        null=True,
        related_name="files",
        on_delete=models.SET_NULL,
    )
    capture = models.ForeignKey(
        "Capture",
        blank=True,
        null=True,
        related_name="files",
        on_delete=models.SET_NULL,
    )

    def __str__(self) -> str:
        return f"{self.directory}{self.name}"

    def calculate_checksum(self, file_obj=None):
        checksum = Blake3()  # pylint: disable=not-callable
        file = self.file
        if file_obj:
            file = file_obj

        for chunk in file.chunks():
            checksum.update(chunk)
        return checksum.hexdigest()


class Capture(BaseModel):
    """
    Model to define captures (specific file type) uploaded through the API.
    """

    CAPTURE_TYPE_CHOICES = [
        ("drf", "Digital RF"),
    ]

    channel = models.CharField(max_length=255, blank=True)
    capture_type = models.CharField(
        max_length=255,
        choices=CAPTURE_TYPE_CHOICES,
        default="drf",
    )
    top_level_dir = models.CharField(max_length=2048, blank=True)
    index_name = models.CharField(max_length=255, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name="captures",
        on_delete=models.PROTECT,
    )

    def __str__(self):
        return f"{self.capture_type} capture for channel {self.channel} added on {self.created_at}"  # noqa: E501


class Dataset(BaseModel):
    """
    Model for datasets defined and created through the API.

    Schema Definition: https://github.com/spectrumx/schema-definitions/blob/master/definitions/sds/abstractions/dataset/README.md
    """

    list_fields = ["authors", "keywords", "institutions"]

    name = models.CharField(max_length=255, blank=False, default=None)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name="datasets",
        on_delete=models.PROTECT,
    )
    abstract = models.TextField(blank=True)
    description = models.TextField(blank=True)
    doi = models.CharField(max_length=255, blank=True)
    authors = models.TextField(blank=True)
    license = models.CharField(max_length=255, blank=True)
    keywords = models.TextField(blank=True)
    institutions = models.TextField(blank=True)
    release_date = models.DateField(blank=True, null=True)
    repository = models.URLField(blank=True)
    version = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    provenance = models.JSONField(blank=True, null=True)
    citation = models.JSONField(blank=True, null=True)
    other = models.JSONField(blank=True, null=True)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        # Serialize the list fields to a JSON string before saving
        for field in self.list_fields:
            field_value = getattr(self, field)
            if field_value:
                if isinstance(getattr(self, field), list):
                    setattr(self, field, json.dumps(getattr(self, field)))
                else:
                    # raise ValueError exception if a list field is not in list format
                    msg = f"A field you are trying to populate ('{field}') must be a list, but you provided a value of type: {type(field_value).__name__}. For your convenience, the list fields in this table include: {self.list_fields!s}."  # noqa: E501
                    raise ValueError(msg)

        super().save(*args, **kwargs)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)

        # Deserialize the JSON strings back to lists
        for field in cls.list_fields:
            if getattr(instance, field):
                setattr(instance, field, json.loads(getattr(instance, field)))
        return instance
