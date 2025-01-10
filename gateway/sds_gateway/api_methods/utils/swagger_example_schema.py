"""Swagger example schema for API methods."""

# ruff: noqa: E501

from django.core.files.uploadedfile import SimpleUploadedFile

from sds_gateway.api_methods.models import File

capture_request_example_schema = {
    "top_level_dir": "/path/to/top_level_dir",
    "channel": "channel_0",
    "capture_type": "drf",
    "index_name": "capture_metadata",
}

capture_response_example_schema = {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "owner": {
        "id": 0,
        "email": "user@example.com",
        "name": "Owner Name",
    },
    "metadata": {
        "H5Tget_class": 1,
        "H5Tget_size": 4,
        "H5Tget_order": 0,
        "H5Tget_precision": 32,
        "H5Tget_offset": 0,
        "subdir_cadence_secs": 3600,
        "file_cadence_millisecs": 1000,
        "sample_rate_numerator": 300000,
        "sample_rate_denominator": 2,
        "samples_per_second": 150000,
        "start_bound": 1515000000,
        "end_bound": 1515005000,
        "is_complex": True,
        "is_continuous": True,
        "epoch": "2024-11-04T23:18:02.829Z",
        "digital_rf_version": "2.5.4",
        "sequence_num": 0,
        "init_utc_timestamp": 1515000000,
        "computer_time": 1515000000,
        "center_freq": 100000000,
        "span": 1000000,
        "gain": 10.0,
        "bandwidth": 300000,
        "custom_attrs": {
            "custom_attr_1": "value_1",
            "custom_attr_2": "value_2",
        },
    },
    "created_at": "2024-11-04T23:18:02.829Z",
    "updated_at": "2024-11-04T23:18:02.829Z",
    "channel": "channel_0",
    "capture_type": "drf",
    "index_name": "capture_metadata",
    "top_level_dir": "/path/to/top_level_dir",
}

example_file_name = "file.h5"
example_file_obj = SimpleUploadedFile(example_file_name, b"file_content")
example_size = example_file_obj.size
example_checksum = File().calculate_checksum(example_file_obj)
minio_file_url = f"http://minio:9000/spectrumx/files/{example_checksum}?X-Amz-Example-Param-1=example-value"

# file post/get/put example schema
file_post_request_example_schema = {
    "file": example_file_obj,
    "directory": "/path/to/file",
    "media_type": "application/x-hdf5",
    "permissions": "rw-r--r--",
}

file_post_response_example_schema = {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "file": minio_file_url,
    "name": example_file_name,
    "directory": "/files/user@example.com/path/to/file",
    "media_type": "application/x-hdf5",
    "owner": 0,
    "permissions": "rw-r--r--",
    "size": example_size,
    "sum_blake3": example_checksum,
}

file_list_response_example_schema = {
    "count": 105,
    "next": "http://localhost:8000/api/latest/assets/files/?page=2&page_size=3",
    "previous": None,
    "results": [
        {
            "bucket_name": "spectrumx",
            "capture": None,
            "created_at": "2025-01-06 14:38:24",
            "dataset": None,
            "directory": "/files/sds_user/0LoiUqJt2d/",
            "expiration_date": "2027-01-06T14:38:24.361963-05:00",
            "file": "http://minio:9000/spectrumx/files/514513e51ad9887f7debee71b4bb26cf24720d9ae02404d467b424b444101d83?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=minioadmin%2F20250110%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20250110T004858Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=16b4ec54382bd2e24f7dc13815451f096bfcda0b3e46608707a4c5c8756b9150",
            "media_type": "text/plain",
            "name": "test_file_kprX1E.txt",
            "owner": {"id": 1, "email": "sds_user", "name": ""},
            "permissions": "rw-r--r--",
            "size": 8100,
            "sum_blake3": "514513e51ad9887f7debee71b4bb26cf24720d9ae02404d467b424b444101d83",
            "updated_at": "2025-01-06 14:38:24",
            "uuid": "2df64c69-8e16-4509-a2f1-fa9c629b1d8a",
        },
        {
            "bucket_name": "spectrumx",
            "capture": None,
            "created_at": "2024-12-16 21:14:01",
            "dataset": None,
            "directory": "/files/sds_user/1ciYuIKVRL/",
            "expiration_date": "2026-12-16T21:14:01.700497-05:00",
            "file": "http://minio:9000/spectrumx/files/0fe9dbd2417345775fe2b6d412879c45160e4e4e49cede7be6dc4a766ab34f1b?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=minioadmin%2F20250110%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20250110T004858Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=0607ab7c36dec416f3b71ecf58b3dd7294efb5ee54dddfda303f8e07f5ef6238",
            "media_type": "text/plain",
            "name": "test_file_0RKgWy.txt",
            "owner": {"id": 1, "email": "sds_user", "name": ""},
            "permissions": "rw-r--r--",
            "size": 8100,
            "sum_blake3": "0fe9dbd2417345775fe2b6d412879c45160e4e4e49cede7be6dc4a766ab34f1b",
            "updated_at": "2024-12-16 21:14:01",
            "uuid": "8987bdeb-9d72-4840-9e0f-a80f6e32e0d0",
        },
        {
            "bucket_name": "spectrumx",
            "capture": None,
            "created_at": "2025-01-06 14:37:35",
            "dataset": None,
            "directory": "/files/sds_user/2NectR0cYr/",
            "expiration_date": "2027-01-06T14:37:35.056678-05:00",
            "file": "http://minio:9000/spectrumx/files/6187db034bf0e6fbbd8b1d00a77b5b38654fcd3ab36fc3cf273b48fe87154ba9?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=minioadmin%2F20250110%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20250110T004858Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=1cd266ec3e2635d8b8cc0c67ff5e61f9a5e4f96b06a99c20333aad5252b87fac",
            "media_type": "text/plain",
            "name": "test_file_WUpKxZ.txt",
            "owner": {"id": 1, "email": "sds_user", "name": ""},
            "permissions": "rw-r--r--",
            "size": 8100,
            "sum_blake3": "6187db034bf0e6fbbd8b1d00a77b5b38654fcd3ab36fc3cf273b48fe87154ba9",
            "updated_at": "2025-01-06 14:37:35",
            "uuid": "a8e8b4cc-cdab-4002-b871-8e209ce52fc3",
        },
    ],
}

file_put_request_example_schema = {
    "name": "new_file_name.h5",
    "directory": "/files/user@example.com/new/path/to/file",
    "media_type": "application/x-hdf5",
    "permissions": "rw-rw-r--",
}

file_contents_check_request_example_schema = {
    "directory": "/path/to/file",
    "media_type": "application/x-hdf5",
    "name": "file.h5",
    "permissions": "rw-r--r--",
    "sum_blake3": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
}
