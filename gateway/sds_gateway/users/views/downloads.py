from pathlib import Path
from typing import Any
from uuid import UUID

from django.http import FileResponse
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from loguru import logger as log

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.tasks import is_user_locked
from sds_gateway.api_methods.tasks import send_item_files_email
from sds_gateway.users.mixins import Auth0LoginRequiredMixin


class TemporaryZipDownloadView(Auth0LoginRequiredMixin, View):
    """View to display a temporary zip file download page and serve the file."""

    template_name = "users/temporary_zip_download.html"

    def get(self, request, *args, **kwargs) -> HttpResponse:
        """Display download page for a temporary zip file or serve the file."""
        zip_uuid = kwargs.get("uuid")
        if not zip_uuid:
            log.warning("No UUID provided in temporary zip download request")
            error_msg = "UUID is required"
            raise Http404(error_msg)

        # Check if this is a download request (automatic download from JavaScript)
        if request.GET.get("download") == "true":
            return self._serve_file_download(zip_uuid, request.user)

        try:
            # Get the temporary zip file
            temp_zip = get_object_or_404(
                TemporaryZipFile,
                uuid=zip_uuid,
                owner=request.user,
            )

            # Check if file still exists on disk
            file_exists = (
                Path(temp_zip.file_path).exists() if temp_zip.file_path else False
            )

            # Determine status and prepare context
            if temp_zip.is_deleted:
                status = "deleted"
                message = "This file has been deleted and is no longer available."
            elif temp_zip.is_expired:
                status = "expired"
                message = "This download link has expired and is no longer available."
            elif not file_exists:
                status = "file_missing"
                message = "The file was not found on the server."
            else:
                status = "available"
                message = None

            # Convert UTC expiry date to user's timezone for display
            expires_at_local = (
                timezone.localtime(temp_zip.expires_at) if temp_zip.expires_at else None
            )

            context = {
                "temp_zip": temp_zip,
                "status": status,
                "message": message,
                "file_exists": file_exists,
                "expires_at_local": expires_at_local,
            }

            return render(request, template_name=self.template_name, context=context)

        except TemporaryZipFile.DoesNotExist as err:
            log.warning(
                f"Temporary zip file not found: {zip_uuid} for user: {request.user.id}"
            )
            error_msg = "File not found."
            raise Http404(error_msg) from err

    def _serve_file_download(self, zip_uuid: str, user) -> HttpResponse:
        """Serve the zip file for download."""
        # Get the temporary zip file
        temp_zip = get_object_or_404(
            TemporaryZipFile,
            uuid=zip_uuid,
            owner=user,
        )

        log.info(f"Found temporary zip file: {temp_zip.filename}")

        file_path = Path(temp_zip.file_path)
        if not file_path.exists():
            log.warning(f"File not found on disk: {temp_zip.file_path}")
            return JsonResponse(
                {"error": "The file was not found on the server."}, status=404
            )

        try:
            fh = file_path.open("rb")
            response = FileResponse(
                fh,
                content_type="application/zip",
                as_attachment=True,
                filename=temp_zip.filename,
            )

            # Mark the file as downloaded
            temp_zip.mark_downloaded()
        except OSError:
            log.exception(f"Error reading file: {temp_zip.file_path}")
            return JsonResponse({"error": "Error reading file."}, status=500)
        else:
            return response


user_temporary_zip_download_view = TemporaryZipDownloadView.as_view()


def _parse_optional_time(
    raw_value: str | None, param_name: str
) -> tuple[int | None, JsonResponse | None]:
    """Parse optional start/end time.

    Returns (value, None), or (None, error JsonResponse).
    """
    if raw_value in (None, ""):
        return None, None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None, JsonResponse(
            {
                "success": False,
                "message": f"Invalid {param_name}; it must be an integer value.",
            },
            status=400,
        )
    if value < 0:
        message = f"Invalid {param_name}; it must be greater than or equal to 0."
        return None, JsonResponse(
            {
                "success": False,
                "message": message,
            },
            status=400,
        )
    return value, None


def _validate_time_range(
    start_time: int | None, end_time: int | None
) -> JsonResponse | None:
    """Return 400 JsonResponse if both provided and start >= end; else None."""
    if start_time is not None and end_time is not None and start_time >= end_time:
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid time range; start_time must be less than end_time.",
            },
            status=400,
        )
    return None


class DownloadItemView(Auth0LoginRequiredMixin, View):
    """
    Unified view to handle item download requests for both datasets and captures.

    This view follows the same pattern as ShareItemView, accepting item_type
    as a URL parameter and handling the download logic generically.
    """

    # Map item types to their corresponding models
    ITEM_MODELS = {
        ItemType.DATASET: Dataset,
        ItemType.CAPTURE: Capture,
    }

    def post(  # noqa: PLR0911
        self,
        request: HttpRequest,
        item_uuid: UUID,
        item_type: ItemType,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        """
        Handle item download request.

        Args:
            request: The HTTP request object
            item_uuid: The UUID of the item to download
            item_type: The type of item to download from ItemType enum

        Returns:
            A JSON response containing the download status
        """
        # Optional start and end times for temporal filtering
        raw_start_time = request.POST.get("start_time")
        raw_end_time = request.POST.get("end_time")

        start_time, err = _parse_optional_time(raw_start_time, "start_time")
        if err is not None:
            return err
        end_time, err = _parse_optional_time(raw_end_time, "end_time")
        if err is not None:
            return err
        err = _validate_time_range(start_time, end_time)
        if err is not None:
            return err

        # Validate item type
        if item_type not in self.ITEM_MODELS:
            return JsonResponse(
                {"success": False, "message": "Invalid item type"},
                status=400,
            )

        # Check if user has access to the item (either as owner or shared user)
        if not user_has_access_to_item(request.user, item_uuid, item_type):
            return JsonResponse(
                {
                    "success": False,
                    "message": f"{item_type.capitalize()} not found or access denied",
                    "item_uuid": item_uuid,
                },
                status=404,
            )

        # Get the item
        model_class = self.ITEM_MODELS[item_type]
        try:
            item = get_object_or_404(
                model_class,
                uuid=item_uuid,
                is_deleted=False,
            )
        except model_class.DoesNotExist:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"{item_type.capitalize()} not found",
                    "item_uuid": item_uuid,
                },
                status=404,
            )

        # Get user email
        user_email = request.user.email
        if not user_email:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"User email is required for sending {item_type} files.",
                },
                status=400,
            )

        # Check if a user already has a task running
        task_name = f"{item_type}_download"
        if is_user_locked(str(request.user.id), task_name):
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        f"You already have a {item_type} download in progress. "
                        "Please wait for it to complete."
                    ),
                },
                status=400,
            )

        # Trigger the unified Celery task
        task = send_item_files_email.delay(
            str(item.uuid),
            str(request.user.id),
            item_type,
            start_time=start_time,
            end_time=end_time,
        )

        return JsonResponse(
            {
                "success": True,
                "message": (
                    f"{item_type.capitalize()} download request accepted. "
                    "You will receive an email with the files shortly."
                ),
                "task_id": task.id,
                "item_name": getattr(item, "name", str(item)),
                "user_email": user_email,
            },
            status=202,
        )


user_download_item_view = DownloadItemView.as_view()
