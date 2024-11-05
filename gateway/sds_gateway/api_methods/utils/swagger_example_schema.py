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

file_get_response_example_schema = {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "owner": {
        "id": 0,
        "email": "user@example.com",
        "name": "Owner Name",
    },
    "dataset": {
        "dataset_field_1": "value_1",
        "dataset_field_2": "value_2",
        "dataset_field_3": "value_3",
    },
    "capture": {
        "capture_field_1": "value_1",
        "capture_field_2": "value_2",
        "capture_field_3": "value_3",
    },
    "created_at": "2024-11-04T10:02:50.511753-05:00",
    "updated_at": "2024-11-04T10:58:11.950794-05:00",
    "file": minio_file_url,
    "name": example_file_name,
    "directory": "/files/user@example.com/path/to/file",
    "media_type": "application/x-hdf5",
    "permissions": "rw-r--r--",
    "size": example_size,
    "sum_blake3": example_checksum,
    "expiration_date": "2026-11-04T10:02:50.511615-05:00",
    "is_deleted": False,
    "deleted_at": None,
    "bucket_name": "spectrumx",
}

file_put_request_example_schema = {
    "name": "new_file_name.h5",
    "directory": "/files/user@example.com/new/path/to/file",
    "media_type": "application/x-hdf5",
    "permissions": "rw-rw-r--",
}
