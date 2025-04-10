"""Describes the models for the API methods."""

import datetime
import json
import uuid
from enum import StrEnum
from pathlib import Path

from blake3 import blake3 as Blake3  # noqa: N812
from django.conf import settings
from django.db import models
from django.db.models import ProtectedError
from django.db.models import QuerySet
from django.db.models.signals import pre_delete
from django.dispatch import receiver


class CaptureType(StrEnum):
    """The type of radiofrequency capture."""

    DigitalRF = "drf"
    RadioHound = "rh"
    SigMF = "sigmf"


class CaptureOrigin(StrEnum):
    """How a capture was created."""

    System = "system"
    User = "user"


class KeySources(StrEnum):
    """The source of an SDS API key."""

    SDSWebUI = "sds_web_ui"
    SVIBackend = "svi_backend"
    SVIWebUI = "svi_web_ui"


def default_expiration_date() -> datetime.datetime:
    """Returns the default expiration date for a file."""
    # 2 years from now
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=730)


class BaseModel(models.Model):
    """
    Superclass for all models in the API methods app.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Allows this class to be abstract."""

        abstract = True

    def soft_delete(self) -> None:
        """Soft delete this record by marking it as deleted."""
        self.is_deleted = True
        self.deleted_at = datetime.datetime.now(datetime.UTC)
        self.save()


class ProtectedFileQuerySet(QuerySet["File"]):
    """Custom QuerySet to protect against deletion of files."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Override the delete method to raise ProtectedError if needed."""
        for obj in self:
            raise_if_file_deletion_is_blocked(instance=obj)
        return super().delete()


class File(BaseModel):
    """
    Model to define files uploaded through the API.
    """

    directory = models.CharField(max_length=2048, default="files/")
    expiration_date = models.DateTimeField(default=default_expiration_date)
    file = models.FileField(upload_to="files/")
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

    # manager override
    objects = ProtectedFileQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.directory}{self.name}"

    @property
    def user_directory(self) -> str:
        """Returns the path relative to the user root on SDS."""
        # TODO: make this the default ".directory" behavior after the workshop
        return str(Path(*self.directory.parts[2:]))

    def calculate_checksum(self, file_obj=None) -> str:
        """Calculates the BLAKE3 checksum of the file."""
        checksum = Blake3()  # pylint: disable=not-callable
        file = self.file
        if file_obj:
            file = file_obj

        for chunk in file.chunks():
            checksum.update(chunk)
        return checksum.hexdigest()

    def delete(self, *args, **kwargs) -> tuple[int, dict[str, int]]:
        """Prevents file deletion when associated with capture or dataset."""
        raise_if_file_deletion_is_blocked(instance=self)
        return super().delete(*args, **kwargs)


def raise_if_file_deletion_is_blocked(instance: File) -> None:
    """Raises an error if the file passed can't be deleted.

    Raises:
        ProtectedError if the file is associated with a capture or dataset.
    """
    associations: list[str] = []
    if instance.capture and not instance.capture.is_deleted:
        associations.append(f"capture ({instance.capture.uuid})")
    if instance.dataset and not instance.dataset.is_deleted:
        associations.append(f"dataset ({instance.dataset.uuid})")
    if not associations:
        return
    msg = (
        f"Cannot delete file '{instance.name}': it is "
        f"associated with {' and '.join(associations)}."
        " Delete the associated object(s) first."
    )
    raise ProtectedError(msg, protected_objects={instance})


@receiver(pre_delete, sender=File)
def prevent_file_deletion(sender, instance: File, **kwargs) -> None:
    """Prevents deletion of files associated with captures or datasets.

    Version to cover bulk deletions from querysets.
    """
    raise_if_file_deletion_is_blocked(instance=instance)


class Capture(BaseModel):
    """
    Model to define captures (specific file type) uploaded through the API.
    """

    CAPTURE_TYPE_CHOICES = [
        (CaptureType.DigitalRF, "Digital RF"),
        (CaptureType.RadioHound, "RadioHound"),
        (CaptureType.SigMF, "SigMF"),
    ]
    ORIGIN_CHOICES = [
        (CaptureOrigin.System, "System"),
        (CaptureOrigin.User, "User"),
    ]

    channel = models.CharField(max_length=255, blank=True)  # DRF
    scan_group = models.UUIDField(blank=True, null=True)  # RH
    capture_type = models.CharField(
        max_length=255,
        choices=CAPTURE_TYPE_CHOICES,
        default=CaptureType.DigitalRF,
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
    origin = models.CharField(
        max_length=255,
        choices=ORIGIN_CHOICES,
        default=CaptureOrigin.User,
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
    release_date = models.DateTimeField(blank=True, null=True)
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
