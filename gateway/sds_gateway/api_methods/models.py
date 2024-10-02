# Description: This file contains the models for the API methods.
import uuid
from datetime import datetime

from blake3 import blake3
from django.conf import settings
from django.db import models


# helper functions
def unix_epoch_time():
    return datetime(1970, 1, 1, tzinfo=datetime.UTC)


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
    directory = models.CharField(max_length=2048)
    media_type = models.CharField(max_length=255, default="application/x-hdf5")
    permissions = models.CharField(max_length=255, default="rwxrwxrwx")
    size = models.IntegerField(blank=True)
    sum_blake3 = models.CharField(max_length=64, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
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


class Capture(File):
    """
    Model to define captures (specific file type) uploaded through the API.

    Attributes:
        unix_time_code: IntegerField - The Unix time code of the capture.
        sequence_num: IntegerField - The sequence number of the capture.
        init_utc_timestamp: DateTimeField - The initial UTC timestamp of the capture.
        computer_time: DateTimeField - The computer time of the capture.
        metadata: ForeignKey - The metadata associated with the capture.
    """

    unix_time_code = models.IntegerField()
    sequence_num = models.IntegerField()
    init_utc_timestamp = models.DateTimeField()
    computer_time = models.DateTimeField()
    metadata = models.ForeignKey(
        "CaptureMetadata",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )


class CaptureMetadata(BaseModel):
    """
    Model to define metadata associated with a capture.

    Attributes:
        capture_type: CharField - The type of capture (ex: digital_rf, sig_mf).
        date_captured: DateTimeField - The date the capture was taken.
        channel: CharField - The channel the capture was taken on.
        bound_start: IntegerField - The start bound of the capture (unix seconds).
        bound_end: IntegerField - The end bound of the capture (unix seconds).
        H5Tget_class: IntegerField - The class of the H5T.
        H5Tget_size: IntegerField - The size of the H5T.
        H5Tget_order: IntegerField - The order of the H5T.
        H5Tget_precision: IntegerField - The precision of the H5T.
        H5Tget_offset: IntegerField - The offset of the H5T.
        subdir_cadence_secs: IntegerField - The cadence of the subdirectory in seconds.
        file_cadence_millisecs: IntegerField - The cadence of the file in milliseconds.
        sample_rate_numerator: IntegerField - The numerator of the sample rate.
        sample_rate_denominator: IntegerField - The denominator of the sample rate.
        samples_per_second: IntegerField - The samples per second.
        is_complex: BooleanField - Whether the capture is complex.
        is_continuous: BooleanField - Whether the capture is continuous.
        epoch: DateTimeField - The linux epoch.
        digital_rf_time_description: CharField - The time description of digital_rf.
        digital_rf_version: CharField - The version of digital_rf.
        center_freq: IntegerField - The center frequency of the capture.
        span: IntegerField - The span of the capture.
        gain: FloatField - The gain of the capture.
        resolution_bandwidth: IntegerField - The resolution bandwidth of the capture.
        antenna: CharField - The antenna used in the capture.
        indoor_outdoor: CharField - Whether the capture was taken indoors or outdoors.
        antenna_direction: FloatField - The direction of the antenna.
        custom_attrs: JSONField - Custom attributes of the capture.
    """

    CAPTURE_TYPE_CHOICES = [
        ("digital_rf", "Digital RF"),
        ("sig_mf", "SigMF"),
    ]

    capture_type = models.CharField(max_length=20, choices=CAPTURE_TYPE_CHOICES)
    date_captured = models.DateTimeField()
    channel = models.CharField(max_length=255)
    bound_start = models.IntegerField()
    bound_end = models.IntegerField()
    H5Tget_class = models.IntegerField()
    H5Tget_size = models.IntegerField()
    H5Tget_order = models.IntegerField()
    H5Tget_precision = models.IntegerField()
    H5Tget_offset = models.IntegerField()
    subdir_cadence_secs = models.IntegerField()
    file_cadence_millisecs = models.IntegerField()
    sample_rate_numerator = models.IntegerField()
    sample_rate_denominator = models.IntegerField()
    samples_per_second = models.IntegerField()
    is_complex = models.BooleanField()
    is_continuous = models.BooleanField()
    epoch = models.DateTimeField(default=unix_epoch_time)
    digital_rf_time_description = models.CharField(max_length=255)
    digital_rf_version = models.CharField(max_length=255)
    center_freq = models.IntegerField()
    span = models.IntegerField()
    gain = models.FloatField()
    resolution_bandwidth = models.IntegerField()
    antenna = models.CharField(max_length=255)
    indoor_outdoor = models.CharField(max_length=255)
    antenna_direction = models.FloatField()
    custom_attrs = models.JSONField()

    def __str__(self):
        return f"Metadata for {self.channel} channel on {self.date_captured} from {self.bound_start} to {self.bound_end} ({self.capture_type})"  # noqa: E501


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
