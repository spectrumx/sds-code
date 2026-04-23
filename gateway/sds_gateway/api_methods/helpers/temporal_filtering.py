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


def _catch_capture_type_error(capture_type: CaptureType) -> None:
    if capture_type != CaptureType.DigitalRF:
        msg = "Only DigitalRF captures are supported for temporal filtering."
        log.error(msg)
        raise ValueError(msg)


def _filter_capture_data_files_selection_bounds(
    capture: Capture,
    start_time: int,  # relative ms from start of capture (from UI)
    end_time: int,  # relative ms from start of capture (from UI)
) -> QuerySet[File]:
    """Filter the capture file selection bounds to the given start and end times."""
    if capture.start_time is None:
        msg = f"Capture {capture.uuid} has no indexed start_time for temporal filtering"
        raise ValueError(msg)

    epoch_start_ms = capture.start_time * 1000
    start_ms = epoch_start_ms + start_time
    end_ms = epoch_start_ms + end_time

    start_file_name = drf_rf_filename_from_ms(start_ms)
    end_file_name = drf_rf_filename_from_ms(end_ms)

    data_files = capture.get_drf_data_files_queryset()
    return data_files.filter(
        name__gte=start_file_name,
        name__lte=end_file_name,
    ).order_by("name")


def get_capture_files_with_temporal_filter(
    capture_type: CaptureType,
    capture: Capture,
    start_time: int | None = None,  # milliseconds since start of capture
    end_time: int | None = None,
) -> QuerySet[File]:
    """Get the capture files with temporal filtering."""
    _catch_capture_type_error(capture_type)

    if start_time is None or end_time is None:
        log.warning(
            "Start or end time is None; returning all capture files without "
            "temporal filtering"
        )
        return get_capture_files(capture)

    # get non-data files
    non_data_files = get_capture_files(capture).exclude(
        name__regex=DRF_RF_FILENAME_REGEX_STR
    )

    # get data files with temporal filtering
    data_files = _filter_capture_data_files_selection_bounds(
        capture, start_time, end_time
    )

    # return all files
    return non_data_files.union(data_files)
