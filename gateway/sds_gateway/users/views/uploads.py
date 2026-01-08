from pathlib import Path
from typing import Any

from django.http import HttpRequest
from django.http import JsonResponse
from django.views import View
from loguru import logger as log
from rest_framework import status

from sds_gateway.api_methods.helpers.file_helpers import create_capture_helper_simple
from sds_gateway.api_methods.helpers.file_helpers import upload_file_helper_simple
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import infer_index_name
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.views.api_keys import validate_uuid


class UploadCaptureView(Auth0LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        """Handle GET request to ensure CSRF token is available."""

        return JsonResponse({"csrf_token": request.META.get("CSRF_COOKIE", "")})

    def _process_file_uploads(
        self,
        request: HttpRequest,
        upload_chunk_files: list[Any],
        relative_paths: list[str],
    ) -> tuple[int, list[str]]:
        saved_files_count = 0
        file_errors = []
        skipped_files = []

        # Validate that both lists have the same length before processing
        if len(upload_chunk_files) != len(relative_paths):
            log.error(
                "upload_chunk_files and relative_paths have different lengths: "
                f"{len(upload_chunk_files)} vs {len(relative_paths)}",
            )
            file_errors.append(
                "Internal error: mismatched file and path counts. "
                "Please contact support."
            )
            return 0, file_errors

        for f, rel_path in zip(upload_chunk_files, relative_paths, strict=True):
            path = Path(rel_path)
            directory = "/" + str(path.parent) if path.parent != Path() else "/"
            filename = path.name
            file_size = f.size
            content_type = getattr(f, "content_type", "application/octet-stream")

            # Skip empty files (these are placeholders for skipped files)
            if file_size == 0:
                log.info(
                    f"Skipping empty file: {filename} "
                    "(likely a placeholder for skipped file)"
                )
                continue

            file_data = {
                "owner": request.user.pk,
                "name": filename,
                "directory": directory,
                "file": f,
                "size": file_size,
                "media_type": content_type,
            }
            responses, upload_errors = upload_file_helper_simple(request, file_data)

            for response in responses:
                if response.status_code in (
                    status.HTTP_200_OK,
                    status.HTTP_201_CREATED,
                ):
                    saved_files_count += 1
                else:
                    error_msg = f"Failed to upload {filename}: {response.data}"
                    file_errors.append(error_msg)
                    log.error(error_msg)
            file_errors.extend(upload_errors)
        file_errors.extend(skipped_files)
        return saved_files_count, file_errors

    def _create_capture_with_endpoint_helper(
        self,
        request: HttpRequest,
        capture_data: dict[str, Any],
        all_relative_paths: list[str] | None = None,
    ) -> tuple[str | None, str | None]:
        """Create a single capture using prepared capture data.

        Returns (capture_uuid, error) where capture_uuid is the created capture
        UUID or None if creation failed, and error is the error message or None.
        """
        try:
            # Set the index name based on capture type
            capture_data["index_name"] = infer_index_name(capture_data["capture_type"])

            # Use the helper function to create the capture
            responses, capture_errors = create_capture_helper_simple(
                request, capture_data
            )
        except (ValueError, TypeError, AttributeError) as exc:
            log.exception("Data validation error creating capture")
            return None, f"Data validation error: {exc}"
        except (ConnectionError, TimeoutError) as exc:
            log.exception("Network error creating capture")
            return None, f"Network error: {exc}"
        else:
            if responses:
                # Capture created successfully
                response = responses[0]
                if hasattr(response, "data") and isinstance(response.data, dict):
                    capture_data = response.data
                    # Extract only the UUID since that's all we use
                    capture_uuid = capture_data.get("uuid")
                    return capture_uuid, None
                log.warning(f"Unexpected response format: {response.data}")
                return (
                    None,
                    f"Unexpected response format: {response.data}",
                )
            # Capture creation failed
            error_msg = capture_errors[0] if capture_errors else "Unknown error"
            log.error(f"Failed to create capture: {error_msg}")
            return (
                None,
                f"Failed to create capture: {error_msg}",
            )

    def _calculate_top_level_dir(
        self, relative_paths: list[str], all_relative_paths: list[str]
    ) -> str:
        """Calculate the top level directory from relative paths."""
        if all_relative_paths and len(all_relative_paths) > 0:
            # Use all_relative_paths when files are skipped
            first_rel_path = all_relative_paths[0]
        elif relative_paths and len(relative_paths) > 0:
            # Use uploaded relative_paths for normal uploads
            first_rel_path = relative_paths[0]
        else:
            first_rel_path = ""

        if first_rel_path and "/" in first_rel_path:
            return "/" + first_rel_path.split("/")[0]
        if first_rel_path:
            return "/"
        return "/"

    def check_rh_scan_group(self, scan_group: str) -> str | None:
        """Check and validate RadioHound scan group.

        Args:
            scan_group: The scan group string to validate

        Returns:
            str: Error message if validation fails, None if valid
        """
        if scan_group and scan_group.strip():
            # Validate UUID format if scan_group is provided
            if not validate_uuid(scan_group.strip()):
                return (
                    f"Invalid scan group format. Must be a valid UUID, "
                    f"got: {scan_group}"
                )
        return None

    def _create_captures_by_type(
        self,
        request: HttpRequest,
        channels: list[str],
        capture_data: dict[str, Any],
        scan_group: str,
        all_relative_paths: list[str],
    ) -> tuple[list[str], list[str]]:
        """Create captures based on capture type.
        For RadioHound: Creates a single capture with scan_group
        For DigitalRF: Creates multiple captures, one for each channel
        """
        created_captures = []
        errors = []

        if capture_data["capture_type"] == CaptureType.RadioHound:
            # For RadioHound, create a single capture with scan_group
            scan_group_error = self.check_rh_scan_group(scan_group)
            if scan_group_error:
                return [], [scan_group_error]
            if scan_group and scan_group.strip():
                capture_data["scan_group"] = scan_group

            created_capture, error = self._create_capture_with_endpoint_helper(
                request, capture_data, all_relative_paths
            )
            if created_capture:
                created_captures.append(created_capture)
            if error:
                errors.append(error)
        else:
            # For DigitalRF, create captures for each channel
            for channel in channels:
                # Add channel to capture data for this iteration
                channel_capture_data = capture_data.copy()
                channel_capture_data["channel"] = channel
                created_capture, error = self._create_capture_with_endpoint_helper(
                    request,
                    channel_capture_data,
                    all_relative_paths,
                )
                if created_capture:
                    created_captures.append(created_capture)
                if error:
                    errors.append(error)

        return created_captures, errors

    def _parse_upload_request(
        self, request: HttpRequest
    ) -> tuple[list[Any], list[str], list[str], list[str], str, "CaptureType"]:
        """Parse upload request parameters."""
        upload_chunk_files = request.FILES.getlist("files")
        relative_paths = request.POST.getlist("relative_paths")
        all_relative_paths = request.POST.getlist("all_relative_paths")
        channels_str = request.POST.get("channels", "")
        channels = [ch.strip() for ch in channels_str.split(",") if ch.strip()]
        scan_group = request.POST.get("scan_group", "")
        capture_type_str = request.POST.get(
            "capture_type", CaptureType.DigitalRF.value
        )  # Default to DigitalRF
        # Convert string to CaptureType enum
        capture_type = (
            CaptureType.RadioHound
            if capture_type_str == CaptureType.RadioHound.value
            else CaptureType.DigitalRF
        )

        return (
            upload_chunk_files,
            relative_paths,
            all_relative_paths,
            channels,
            scan_group,
            capture_type,
        )

    def _check_required_fields(
        self, capture_type: "CaptureType", channels: list[str], scan_group: str
    ) -> bool:
        """Check if required fields are provided for capture creation."""
        if capture_type == CaptureType.RadioHound:
            # scan_group is optional for RadioHound captures
            return True
        return bool(channels)

    def file_upload_status_mux(
        self,
        saved_files_count: int,
        upload_chunk_files: list[Any],
        file_errors: list[str],
        *,
        all_files_empty: bool,
        has_required_fields: bool,
    ) -> str:
        """Determine the response status based on upload and capture creation
        results.

        Returns:
            "success": All files successful OR All skipped + has required fields
            "error": Some files successful OR All files failed OR All skipped +
                missing fields
        """

        if all_files_empty:
            # All files were skipped (empty)
            return "success" if has_required_fields else "error"

        if (
            saved_files_count > 0
            and saved_files_count == len(upload_chunk_files)
            and not file_errors
        ):
            # All files successful
            return "success"

        # Some files successful OR All files failed
        return "error"

    def _build_file_capture_response_data(
        self,
        file_upload_status: str,
        saved_files_count: int,
        created_captures: list[str],
        file_errors: list[str],
        capture_errors: list[str],
        *,
        all_files_empty: bool = False,
        has_required_fields: bool = False,
    ) -> dict[str, Any]:
        """Build the response data dictionary."""
        response_data = {
            "file_upload_status": file_upload_status,
            "saved_files_count": saved_files_count,
            "captures": created_captures,
        }

        # Add custom message when all files are skipped (regardless of capture creation)
        if all_files_empty and has_required_fields and not file_errors:
            response_data["message"] = "Upload skipped. All files exist on server"
        elif all_files_empty and not has_required_fields:
            # All files were skipped but missing required fields
            response_data["message"] = (
                "Upload skipped. All files exist on server, but missing required "
                "fields for capture creation"
            )
        elif all_files_empty and file_errors:
            # All files were skipped but there were errors
            response_data["message"] = (
                "Upload skipped. All files exist on server, but there were errors "
                "during processing"
            )
        elif file_upload_status == "success" and created_captures:
            # Successful upload with capture creation
            response_data["message"] = (
                f"Upload completed successfully! {saved_files_count} files uploaded "
                f"and {len(created_captures)} capture(s) created."
            )
        elif file_upload_status == "success":
            # Successful upload without capture creation
            response_data["message"] = (
                f"Upload completed successfully! {saved_files_count} files uploaded."
            )

        # Combine file upload errors and capture creation errors
        all_errors = []
        if file_errors:
            all_errors.extend(file_errors)
        if capture_errors:
            all_errors.extend(capture_errors)
        if all_errors:
            response_data["errors"] = all_errors
        return response_data

    def _process_capture_creation(
        self,
        request: HttpRequest,
        channels: list[str],
        capture_type: "CaptureType",
        scan_group: str,
        all_relative_paths: list[str],
        *,
        has_required_fields: bool,
    ) -> tuple[list[str], list[str]]:
        """Handle capture creation logic."""
        capture_errors = []
        created_captures = []

        if has_required_fields:
            log.info(
                f"Creating captures - has_required_fields: {has_required_fields}, "
                f"capture_type: {capture_type}, channels: {channels}, "
                f"scan_group: {scan_group}"
            )

            # Calculate top_level_dir from relative paths
            top_level_dir = self._calculate_top_level_dir(
                all_relative_paths, all_relative_paths
            )

            # Prepare base capture data
            capture_data = {
                "capture_type": capture_type,
                "top_level_dir": str(top_level_dir),
            }

            # Create captures based on type
            created_captures, capture_errors = self._create_captures_by_type(
                request, channels, capture_data, scan_group, all_relative_paths
            )

            if capture_errors:
                log.error(f"Capture creation errors: {capture_errors}")
        else:
            created_captures = []
            capture_errors = []

        return created_captures, capture_errors

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        try:
            (
                upload_chunk_files,
                relative_paths,
                all_relative_paths,
                channels,
                scan_group,
                capture_type,
            ) = self._parse_upload_request(request)

            saved_files_count, file_errors = self._process_file_uploads(
                request, upload_chunk_files, relative_paths
            )

            created_captures = []

            # Check if all files were empty (skipped)
            # If no files were sent (all skipped on frontend), consider them all empty
            all_files_empty = (
                all(f.size == 0 for f in upload_chunk_files)
                if upload_chunk_files
                else True
            )

            # Additional check: if no files were sent but we have all_relative_paths,
            # this indicates all files were skipped on the frontend
            if not upload_chunk_files and all_relative_paths:
                all_files_empty = True

            # Debug logging for request data
            log.info(
                "Upload request - files count: "
                f"{len(upload_chunk_files) if upload_chunk_files else 0}, "
                "all_relative_paths count: "
                f"{len(all_relative_paths) if all_relative_paths else 0}, "
                f"all_files_empty: {all_files_empty}, capture_type: {capture_type}, "
                f"channels: {channels}, scan_group: {scan_group}"
            )

            # Create captures if:
            # 1. All uploads succeeded, OR
            # 2. We have required fields (regardless of file upload status)
            capture_errors = []
            # Check if we have the required fields for capture creation
            has_required_fields = self._check_required_fields(
                capture_type, channels, scan_group
            )

            # Check if this is a chunked upload (skip capture creation for chunks)
            is_chunk = request.POST.get("is_chunk", "false").lower() == "true"
            chunk_number = request.POST.get("chunk_number", None)
            total_chunks = request.POST.get("total_chunks", None)

            # Determine if this is the last chunk or not a chunked upload
            is_last_chunk = (
                not is_chunk
                or chunk_number is None
                or total_chunks is None
                or (int(chunk_number) == int(total_chunks))
            )
            should_create_captures = is_last_chunk

            created_captures = []
            capture_errors = []

            # Only create captures if this is the last chunk AND there are no file
            # upload errors
            if should_create_captures and not file_errors:
                # Handle capture creation
                created_captures, capture_errors = self._process_capture_creation(
                    request,
                    channels,
                    capture_type,
                    scan_group,
                    all_relative_paths,
                    has_required_fields=has_required_fields,
                )
            elif should_create_captures and file_errors:
                log.info(
                    "Skipping capture creation due to "
                    f"file upload errors: {file_errors}"
                )
            else:
                log.info(
                    "Skipping capture creation for chunk "
                    f"{chunk_number} of {total_chunks}"
                )

            # Log file upload errors if they occurred
            if file_errors and not all_files_empty:
                log.error(f"File upload errors occurred. Errors: {file_errors}")

            # Determine file upload status for frontend display
            file_upload_status = self.file_upload_status_mux(
                saved_files_count,
                upload_chunk_files,
                file_errors,
                all_files_empty=all_files_empty,
                has_required_fields=has_required_fields,
            )

            file_capture_response_data = self._build_file_capture_response_data(
                file_upload_status,
                saved_files_count,
                created_captures,
                file_errors,
                capture_errors,
                all_files_empty=all_files_empty,
                has_required_fields=has_required_fields,
            )

            return JsonResponse(file_capture_response_data)

        except (ValueError, TypeError, AttributeError) as e:
            log.warning(f"Data validation error in UploadCaptureView.post: {e}")
            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid request data",
                    "error_code": "VALIDATION_ERROR",
                    "message": f"Data validation error: {e!s}",
                },
                status=400,
            )
        except (ConnectionError, TimeoutError) as e:
            log.exception("Network error in UploadCaptureView.post")
            return JsonResponse(
                {
                    "success": False,
                    "error": "Network connection error",
                    "error_code": "NETWORK_ERROR",
                    "message": f"Network error: {e!s}",
                },
                status=503,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("Unexpected error in UploadCaptureView.post")
            return JsonResponse(
                {
                    "success": False,
                    "error": "Internal server error",
                    "error_code": "UNKNOWN_ERROR",
                    "message": f"{e!s}",
                },
                status=500,
            )


user_upload_capture_view = UploadCaptureView.as_view()
