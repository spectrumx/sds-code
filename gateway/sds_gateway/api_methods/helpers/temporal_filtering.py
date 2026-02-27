import re

from django.db.models import QuerySet

from sds_gateway.api_methods.models import CaptureType, Capture, File
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.api_methods.utils.relationship_utils import get_capture_files
from loguru import logger as log

# Digital RF spec: rf@SECONDS.MILLISECONDS.h5 (e.g. rf@1396379502.000.h5)
# https://github.com/MITHaystack/digital_rf
DRF_RF_FILENAME_PATTERN = re.compile(
    r"^rf@(\d+)\.(\d+)\.h5$",
    re.IGNORECASE,
)
DRF_RF_FILENAME_REGEX_STR = r"^rf@\d+\.\d+\.h5$"


def drf_rf_filename_from_ms(ms: int) -> str:
    """Format ms as DRF rf data filename (canonical for range queries)."""
    return f"rf@{ms // 1000}.{ms % 1000:03d}.h5"


def drf_rf_filename_to_ms(file_name: str) -> int | None:
    """
    Parse DRF rf data filename to milliseconds.
    Handles rf@SECONDS.MILLISECONDS.h5; fractional part padded to 3 digits.
    """
    name = file_name.strip()
    match = DRF_RF_FILENAME_PATTERN.match(name)
    if not match:
        return None
    try:
        seconds = int(match.group(1))
        frac = match.group(2).ljust(3, "0")[:3]
        return seconds * 1000 + int(frac)
    except (ValueError, TypeError):
        return None


def _catch_capture_type_error(capture_type: CaptureType) -> None:
    if capture_type != CaptureType.DigitalRF:
        msg = "Only DigitalRF captures are supported for temporal filtering."
        log.error(msg)
        raise ValueError(msg)


def _parse_drf_rf_timestamp(file_name: str) -> int | None:
    """Extract timestamp in ms from a Digital RF data filename (alias for drf_rf_filename_to_ms)."""
    return drf_rf_filename_to_ms(file_name)


def get_capture_bounds(capture_type: CaptureType, capture_uuid: str) -> tuple[int, int]:
    """Get start and end bounds for capture from opensearch."""
    
    _catch_capture_type_error(capture_type)

    client = get_opensearch_client()
    index = f"captures-{capture_type}"

    try:
        response = client.get(index=index, id=capture_uuid)
    except Exception as e:
        if getattr(e, "status_code", None) == 404 or (hasattr(e, "info") and e.info.get("status") == 404):
            raise ValueError(
                f"Capture {capture_uuid} not found in OpenSearch index {index}"
            ) from e
        raise

    if not response.get("found"):
        raise ValueError(
            f"Capture {capture_uuid} not found in OpenSearch index {index}"
        )

    source = response["_source"]
    search_props = source["search_props"]
    start_time = search_props["start_time"]
    end_time = search_props["end_time"]
    return start_time, end_time


def get_data_files(capture_type: CaptureType, capture: Capture) -> QuerySet[File]:
    """Get the data files in the capture."""
    _catch_capture_type_error(capture_type)

    return get_capture_files(capture).filter(name__regex=DRF_RF_FILENAME_REGEX_STR)


def get_file_cadence(capture_type: CaptureType, capture: Capture) -> int:
    """Get the file cadence in milliseconds. OpenSearch bounds are in seconds."""
    _catch_capture_type_error(capture_type)

    capture_uuid = str(capture.uuid)
    try:
        start_time, end_time = get_capture_bounds(capture_type, capture_uuid)
    except ValueError as e:
        log.error(e)
        raise e

    data_files = get_data_files(capture_type, capture)
    count = data_files.count()

    # the first file represents the beginning of the capture
    # exclude it from the count to get the correct file cadence
    # the count - 1 gives us the number of "spaces" between the files
    count -= 1
    if count == 0:
        return 0
    duration_sec = end_time - start_time
    duration_ms = duration_sec * 1000
    return max(1, int(duration_ms / count))


def get_duration_bounds(capture_type: CaptureType, capture_uuid: str, relative_time: int) -> tuple[int, int]:
    """Return (0, length_of_capture_ms). OpenSearch bounds are in seconds."""
    try:
        start_time, end_time = get_capture_bounds(capture_type, capture_uuid)
    except ValueError as e:
        log.error(e)
        raise e

    length_of_capture_ms = (end_time - start_time) * 1000
    return 0, length_of_capture_ms


def filter_capture_data_files_selection_bounds(
    capture_type: CaptureType,
    capture: Capture,
    start_time: int,  # relative ms from start of capture (from UI)
    end_time: int,    # relative ms from start of capture (from UI)
) -> QuerySet[File]:
    """Filter the capture file selection bounds to the given start and end times."""
    _catch_capture_type_error(capture_type)
    epoch_start_sec, _ = get_capture_bounds(capture_type, capture.uuid)
    epoch_start_ms = epoch_start_sec * 1000
    start_ms = epoch_start_ms + start_time
    end_ms = epoch_start_ms + end_time

    start_file_name = drf_rf_filename_from_ms(start_ms)
    end_file_name = drf_rf_filename_from_ms(end_ms)

    data_files = get_data_files(capture_type, capture)
    return data_files.filter(
        name__gte=start_file_name,
        name__lte=end_file_name,
    ).order_by("name")

def get_capture_files_with_temporal_filter(
    capture_type: CaptureType,
    capture: Capture,
    start_time: int | None = None, # milliseconds since epoch (start of capture)
    end_time: int | None = None, # milliseconds since epoch
) -> QuerySet[File]:
    """Get the capture files with temporal filtering."""
    _catch_capture_type_error(capture_type)

    if start_time is None or end_time is None:
        log.warning("Start or end time is None, returning all capture files without temporal filtering")
        return get_capture_files(capture)

    # get non-data files
    non_data_files = get_capture_files(capture).exclude(name__regex=DRF_RF_FILENAME_REGEX_STR)

    # get data files with temporal filtering
    data_files = filter_capture_data_files_selection_bounds(
        capture_type, capture, start_time, end_time
    )

    # return all files
    return non_data_files.union(data_files)