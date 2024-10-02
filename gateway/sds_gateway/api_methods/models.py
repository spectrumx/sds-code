# Description: This file contains the models for the API methods.
import datetime
import uuid

from blake3 import blake3
from django.conf import settings
from django.db import models


def default_expiration_date():
    # 2 years from now
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=730)


class BaseModel(models.Model):
    """
    Superclass for all models in the API methods app.

    Attributes:
        uuid: UUIDField - The UUID of the object.
        created_at: DateTimeField - The date and time the object was created.
        updated_at: DateTimeField - The date and time the object was last updated.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class File(BaseModel):
    """
    Model to define files uploaded through the API.

    Attributes:
        file: FileField - The file uploaded.
        name: CharField - The name of the file.
        directory: CharField - The directory the file is stored in (tracked by DB only).
        media_type: CharField - The media type of the file (former MIME type).
        permissions: CharField - The permissions of the file (ex: rwxrwxrwx).
        size: IntegerField - The size of the file (in bytes).
        sum_sha256: CharField - The SHA256 checksum of the file.
        owner: ForeignKey - The user that owns the file.
        bucket_name: CharField - The name of the MinIO bucket the file is stored in.
        dataset: ForeignKey - The dataset the file belongs to (optional).
    """

    file = models.FileField(upload_to="files/")
    name = models.CharField(max_length=255, blank=True)
    directory = models.CharField(max_length=2048, default="files/")
    media_type = models.CharField(max_length=255, default="application/x-hdf5")
    permissions = models.CharField(max_length=255, default="rwxrwxrwx")
    size = models.IntegerField(blank=True)
    sum_blake3 = models.CharField(max_length=64, blank=True)
    expiration_date = models.DateTimeField(default=default_expiration_date)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name="files",
        on_delete=models.SET_NULL,
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
    drf_capture = models.ForeignKey(
        "Capture",
        blank=True,
        null=True,
        related_name="files",
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f"{self.directory}/{self.name}"

    def save(self, *args, **kwargs):
        self.size = self.file.size

        if not self.name:
            self.name = self.file.name

        if not self.sum_blake3:
            self.sum_blake3 = self.calculate_checksum()
            self.file.name = self.sum_blake3

        super().save(*args, **kwargs)

    def calculate_checksum(self):
        checksum = blake3()
        for chunk in self.file.chunks():
            checksum.update(chunk)
        return checksum.hexdigest()


class Capture(BaseModel):
    """
    Model to define captures (specific file type) uploaded through the API.

    Attributes:
        channel: CharField - The channel the capture was taken on.
        capture_type: CharField - The type of capture (ex: Digital RF).
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

    def __str__(self):
        return f"{self.capture_type} capture for channel {self.channel} added on {self.created_at}"  # noqa: E501


class Dataset(BaseModel):
    """
    Model for datasets defined and created through the API.

    Attributes:
        name: CharField - The name of the dataset, required.
        abstract: TextField - The abstract of the publication, optional.
        description: TextField - A short description of the dataset, optional.
        doi: CharField - The DOI of the dataset, optional.
        authors: ManyToManyField - The authors of the dataset.
        license: CharField - The license of the dataset.
        keywords: CharField - The keywords of the dataset.
        institutions: CharField - The institutions associated with the dataset.
        release_date: DateTimeField - The date the dataset was released.
        repository: URLField - The repository of the dataset.
        version: CharField - The version of the dataset.
        website: URLField - The website of the dataset.
        provenance: JSONField - The provenance of the dataset.
        citation: JSONField - The citation of the dataset.
        other: JSONField - Other information about the
    """

    name = models.CharField(max_length=255)
    abstract = models.TextField(blank=True)
    description = models.TextField(blank=True)
    doi = models.CharField(max_length=255, blank=True)
    authors = models.ManyToManyField(settings.AUTH_USER_MODEL)
    license = models.CharField(max_length=255, blank=True)
    keywords = models.CharField(max_length=255, blank=True)
    institutions = models.CharField(max_length=255, blank=True)
    release_date = models.DateTimeField(blank=True)
    repository = models.URLField(blank=True)
    version = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    provenance = models.JSONField(blank=True)
    citation = models.JSONField(blank=True)
    other = models.JSONField(blank=True)

    def __str__(self):
        return self.name
