"""Swagger example schema for API methods."""

# ruff: noqa: E501

from django.core.files.uploadedfile import SimpleUploadedFile

from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File

example_cap_creation_request = {
    "top_level_dir": "/captures/drf/example/test-HCkyf3IFmF/",
    "channel": "cap-2024-06-27T14-00-00",
    "capture_type": CaptureType.DigitalRF,
    "index_name": "capture_metadata",
}

example_cap_creation_response = {
    "uuid": "2c413fbb-4132-4d56-a0c0-633acdd71676",
    "owner": {
        "id": 1,
        "email": "user@example.com",
        "name": "",
    },
    "capture_props": {
        "samples_per_second": 2500000,
        "start_bound": 1719499740,
        "end_bound": 1719499741,
        "is_complex": True,
        "is_continuous": True,
        "center_freq": 1024000000,
        "bandwidth": 100000000,
        "custom_attrs": {
            "num_subchannels": 1,
            "index": 4298748970000000,
            "processing/channelizer_filter_taps": [],
            "processing/decimation": 1,
            "processing/interpolation": 1,
            "processing/resampling_filter_taps": [],
            "processing/scaling": 1,
            "receiver/center_freq": 1024000000.4842604,
            "receiver/clock_rate": 125000000,
            "receiver/clock_source": "external",
            "receiver/dc_offset": False,
            "receiver/description": "UHD USRP source using GNU Radio",
            "receiver/id": "172.16.20.43",
            "receiver/info/mboard_id": "n310",
            "receiver/info/mboard_name": "n/a",
            "receiver/info/mboard_serial": "31649FE",
            "receiver/info/rx_antenna": "RX2",
            "receiver/info/rx_id": "336",
            "receiver/info/rx_serial": "3162222",
            "receiver/info/rx_subdev_name": "Magnesium",
            "receiver/info/rx_subdev_spec": "A:0 A:1",
            "receiver/iq_balance": "",
            "receiver/lo_export": "",
            "receiver/lo_offset": 624999.4039535522,
            "receiver/lo_source": "",
            "receiver/otw_format": "sc16",
            "receiver/samp_rate": 2500000,
            "receiver/stream_args": "",
            "receiver/subdev": "A:0",
            "receiver/time_source": "external",
        },
    },
    "files": [
        {
            "uuid": "1f246d09-bd19-42d7-a15a-9c2f4f328afa",
            "name": "drf_properties.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/",
        },
        {
            "uuid": "27d0588e-9883-4613-ac4f-c2e4662d55e9",
            "name": "dmd_properties.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/metadata/",
        },
        {
            "uuid": "6d7ccef4-208f-48fb-96fe-bc4a8527fa7c",
            "name": "rf@1719499741.625.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "84b76d81-28af-4d64-8261-95a61a4a8275",
            "name": "rf@1719499741.875.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "2e6f3cd7-e54b-4587-b25d-b8a5ca500329",
            "name": "rf@1719499741.500.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "553ea258-7b61-44fa-b816-0332983c0f4c",
            "name": "rf@1719499741.250.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "5887b336-0254-4577-a1aa-8819a12240c7",
            "name": "rf@1719499740.125.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "30d30cf1-5d6c-42c9-ae5a-2391e7bd7d1e",
            "name": "metadata@1719499588.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/metadata/2024-06-27T14-00-00/",
        },
        {
            "uuid": "24307947-6ebd-4988-8d52-71230d6f9d5a",
            "name": "rf@1719499741.000.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "387a58e8-3e6c-49f4-9109-1952faf485af",
            "name": "rf@1719499741.125.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "a33a37ab-c40e-4cce-ada3-f3294613aa54",
            "name": "rf@1719499740.375.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "50c7cb34-877f-4ba2-a74a-3f3e7880bb2a",
            "name": "rf@1719499741.750.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "b8bd1781-8331-4a89-b40e-4e8364744829",
            "name": "rf@1719499740.250.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "e866a56b-22e7-4a61-bc69-2c2062b212ab",
            "name": "rf@1719499740.500.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "5e85ae1e-ad33-4580-8dbf-17fba1546594",
            "name": "rf@1719499740.625.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "75afc0c3-daa4-4456-adb4-004eac4a6727",
            "name": "rf@1719499741.375.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "7e0666b2-3a8d-4b6b-a074-f9721c0fb562",
            "name": "rf@1719499740.875.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "6c9e6f2b-d182-48f5-8e08-50309725be8e",
            "name": "rf@1719499740.750.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
        {
            "uuid": "86d0a0b9-a7cc-4678-a820-54dd4b05456d",
            "name": "rf@1719499740.000.h5",
            "directory": "/files/user@example.com/captures/drf/example/test-HCkyf3IFmF/cap-2024-06-27T14-00-00/2024-06-27T14-00-00/",
        },
    ],
    "created_at": "2025-03-05T12:23:26.229351-05:00",
    "updated_at": "2025-03-05T12:23:26.229368-05:00",
    "deleted_at": None,
    "is_deleted": False,
    "channel": "cap-2024-06-27T14-00-00",
    "scan_group": None,
    "capture_type": "drf",
    "top_level_dir": "/captures/drf/example/test-HCkyf3IFmF/",
    "index_name": "capture_metadata",
    "origin": "user",
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

example_file_update_request = {
    "name": "new_file_name.h5",
    "directory": "/files/user@example.com/new/path/to/file",
    "media_type": "application/x-hdf5",
    "permissions": "rw-rw-r--",
}

example_file_content_check_request = {
    "directory": "/path/to/file",
    "media_type": "application/x-hdf5",
    "name": "file.h5",
    "permissions": "rw-r--r--",
    "sum_blake3": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
}

capture_list_request_example_schema = {
    "capture_type": CaptureType.DigitalRF,
    "metadata_filters": {
        "start_bound": {"gte": 1515000000},
        "end_bound": {"lte": 1515005000},
    },
}

capture_list_response_example_schema = {
    "count": 105,
    "next": "http://localhost:8000/api/latest/assets/captures/?page=2&page_size=3",
    "previous": None,
    "results": [
        capture_response_example_schema,
        capture_response_example_schema,
        capture_response_example_schema,
    ],
}
