"""H5 file processing service."""

import logging

from django.http import JsonResponse

from .file_utils import PreviewFileTooLargeError
from .file_utils import check_file_access
from .file_utils import temp_h5_file_context
from .file_utils import validate_h5_file

logger = logging.getLogger(__name__)


class H5PreviewService:
    """Service for handling H5 file preview operations."""

    H5_MAX_BYTES = 200 * 1024 * 1024  # 200 MiB cap for preview temp copy

    def __init__(self, max_bytes=None):
        self.max_bytes = max_bytes or self.H5_MAX_BYTES

    def get_preview(self, file_obj, user):
        """
        Get H5 file preview information.

        Args:
            file_obj: The file object to preview
            user: The user requesting the preview

        Returns:
            JsonResponse: The preview response or error response
        """
        # Check access
        if not check_file_access(file_obj, user):
            return JsonResponse({"error": "Not found or access denied"}, status=404)

        # Validate file
        is_valid, error_response = validate_h5_file(file_obj, self.max_bytes)
        if not is_valid:
            return error_response

        # Process file with context manager
        try:
            with temp_h5_file_context(file_obj, self.max_bytes):
                # TODO: Implement actual HDF5 preview functionality here
                return JsonResponse(
                    {
                        "error": "H5 file preview not yet implemented",
                        "message": (
                            "HDF5 file preview functionality is not available yet. "
                            "Please download the file to view its contents."
                        ),
                    }
                )
        except PreviewFileTooLargeError:
            return JsonResponse({"error": "File too large to preview"}, status=413)
        except OSError as e:
            logger.warning("Error creating H5 preview: %s", e)
            return JsonResponse({"error": "Error reading HDF5 file"}, status=500)
