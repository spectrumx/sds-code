import re

from django.db.models import QuerySet
from loguru import logger as log

from sds_gateway.api_methods.models import DRF_RF_FILENAME_REGEX_STR
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.relationship_utils import get_capture_files

# Digital RF spec: rf@SECONDS.MILLISECONDS.h5 (e.g. rf@1396379502.000.h5)
# https://github.com/MITHaystack/digital_rf
DRF_RF_FILENAME_PATTERN = re.compile(
    r"^rf@(\d+)\.(\d+)\.h5$",
    re.IGNORECASE,
)


def drf_rf_filename_from_ms(ms: int) -> str:
    """Format ms as DRF rf data filename (canonical for range queries)."""
    return f"rf@{ms // 1000}.{ms % 1000:03d}.h5"


def _catch_value_errors(capture_type: CaptureType, capture: Capture) -> None:

    if capture_type != CaptureType.DigitalRF:
        msg = "Only DigitalRF captures are supported for temporal filtering."
        log.error(msg)
        raise ValueError(msg)

    if capture.start_time is None:
        msg = f"Capture {capture.uuid} has no indexed start_time for temporal filtering"
        raise ValueError(msg)


def get_capture_files_with_temporal_filter(
    capture_type: CaptureType,
    capture: Capture,
    start_time: int | None = None,  # milliseconds since start of capture
    end_time: int | None = None,
) -> QuerySet[File]:
    """Get the capture files with temporal filtering."""
    _catch_value_errors(capture_type, capture)

    capture_files = get_capture_files(capture)

    if start_time is None or end_time is None:
        log.warning(
            "Start or end time is None; returning all capture files without "
            "temporal filtering"
        )
        return capture_files

    epoch_start_ms = capture.start_time * 1000
    start_ms = epoch_start_ms + start_time
    end_ms = epoch_start_ms + end_time

    return filter_files_by_temporal_bounds(
        capture_files,
        start_ms,
        end_ms,
    )


def filter_files_by_temporal_bounds(
    files: QuerySet[File],
    start_time: int,
    end_time: int,
) -> QuerySet[File]:
    """Filter files by temporal bounds."""

    # get non-data files
    non_data_files = files.exclude(name__regex=DRF_RF_FILENAME_REGEX_STR)

    unfiltered_data_files = files.filter(name__regex=DRF_RF_FILENAME_REGEX_STR)

    start_file_name = drf_rf_filename_from_ms(start_time)
    end_file_name = drf_rf_filename_from_ms(end_time)

    filtered_data_files = unfiltered_data_files.filter(
        name__gte=start_file_name,
        name__lte=end_file_name,
    ).order_by("name")

    # return all files
    return non_data_files.union(filtered_data_files)
