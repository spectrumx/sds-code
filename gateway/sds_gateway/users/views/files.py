import json
from typing import cast

from django.core.paginator import EmptyPage
from django.core.paginator import PageNotAnInteger
from django.core.paginator import Paginator
from django.db.models.query import QuerySet
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.views import View
from django.views.generic import DetailView
from loguru import logger as log
from minio.error import MinioException

from sds_gateway.api_methods.helpers.download_file import FileDownloadError
from sds_gateway.api_methods.helpers.download_file import download_file
from sds_gateway.api_methods.helpers.file_helpers import (
    check_file_contents_exist_helper,
)
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.utils.asset_access_control import user_has_access_to_file
from sds_gateway.users.file_utils import get_file_content_response
from sds_gateway.users.file_utils import validate_file_preview_request
from sds_gateway.users.files_utils import add_capture_files
from sds_gateway.users.files_utils import add_root_items
from sds_gateway.users.files_utils import add_shared_items
from sds_gateway.users.files_utils import add_user_files
from sds_gateway.users.files_utils import build_breadcrumbs
from sds_gateway.users.files_utils import items_to_dicts
from sds_gateway.users.h5_service import H5PreviewService
from sds_gateway.users.item_models import Item
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.navigation_models import NavigationContext
from sds_gateway.users.navigation_models import NavigationType
from sds_gateway.visualizations.config import get_visualization_compatibility


class ListFilesView(Auth0LoginRequiredMixin, View):
    template_name = "users/file_list.html"
    items_per_page = 25

    def get(self, request, *args, **kwargs) -> HttpResponse:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")

        # Get filter parameters
        search = request.GET.get("search", "")
        date_start = request.GET.get("date_start", "")
        date_end = request.GET.get("date_end", "")
        center_freq = request.GET.get("center_freq", "")
        bandwidth = request.GET.get("bandwidth", "")
        location = request.GET.get("location", "")

        # Base queryset
        files_qs = request.user.files.filter(is_deleted=False)

        # Apply search filter
        if search:
            files_qs = files_qs.filter(name__icontains=search)

        # Apply date range filter
        if date_start:
            files_qs = files_qs.filter(created_at__gte=date_start)
        if date_end:
            files_qs = files_qs.filter(created_at__lte=date_end)

        # Apply other filters
        if center_freq:
            files_qs = files_qs.filter(center_frequency=center_freq)
        if bandwidth:
            files_qs = files_qs.filter(bandwidth=bandwidth)
        if location:
            files_qs = files_qs.filter(location=location)

        # Handle sorting
        if sort_by:
            if sort_order == "desc":
                files_qs = files_qs.order_by(f"-{sort_by}")
            else:
                files_qs = files_qs.order_by(sort_by)

        # Paginate the results
        paginator = Paginator(files_qs, self.items_per_page)
        try:
            files_page = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            files_page = paginator.page(1)

        # Get visualization compatibility data
        visualization_compatibility = get_visualization_compatibility()

        return render(
            request,
            template_name=self.template_name,
            context={
                "files": files_page,
                "total_pages": paginator.num_pages,
                "current_page": page,
                "total_items": paginator.count,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "visualization_compatibility": visualization_compatibility,
            },
        )


user_file_list_view = ListFilesView.as_view()


class FileDetailView(Auth0LoginRequiredMixin, DetailView):  # pyright: ignore[reportMissingTypeArgument]
    model = File
    slug_field = "uuid"
    slug_url_kwarg = "uuid"
    template_name = "users/file_detail.html"

    def get_queryset(self) -> QuerySet[File]:
        return self.request.user.files.filter(is_deleted=False).all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target_file = cast("File", self.get_object())
        if target_file is None:
            return context
        serializer = FileGetSerializer(target_file)
        context["returning_page"] = self.request.GET.get("returning_page", default=1)
        context["file"] = serializer.data
        context["skip_fields"] = [
            "bucket_name",
            "deleted_at",
            "file",
            "is_deleted",
            "name",
        ]
        return context


user_file_detail_view = FileDetailView.as_view()


class FileDownloadView(Auth0LoginRequiredMixin, View):
    """Session-authenticated file download for the Users UI."""

    def get(self, request: HttpRequest, uuid: str, *args, **kwargs) -> HttpResponse:
        file_obj = get_object_or_404(File, uuid=uuid, is_deleted=False)

        # Access control: owner or shared via capture/dataset
        has_access = user_has_access_to_file(request.user, file_obj)

        if not has_access:
            return JsonResponse({"error": "Not found or access denied"}, status=404)

        try:
            content = download_file(file_obj)
        except (MinioException, FileDownloadError) as e:
            log.warning(f"Error downloading file {file_obj.name}: {e}")
            return JsonResponse({"error": "Failed to download file"}, status=500)

        response = HttpResponse(
            content,
            content_type=file_obj.media_type or "application/octet-stream",
        )
        response["Content-Disposition"] = f'attachment; filename="{file_obj.name}"'
        return response


class FileContentView(Auth0LoginRequiredMixin, View):
    """Serve small text content of a file for modal previews.

    Supports rendering JSON as pretty-printed text. Enforces basic access
    control: owners or users with access to the parent capture/dataset.
    """

    MAX_BYTES = 1024 * 1024  # 1 MiB safety limit for previews

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Get file content for preview."""
        file_uuid = kwargs.get("uuid")
        if not file_uuid:
            return JsonResponse({"error": "File UUID required"}, status=400)

        file_obj = get_object_or_404(File, uuid=file_uuid, is_deleted=False)

        # Validate request (access control and size checks)
        error_response = validate_file_preview_request(
            request.user, file_obj, self.MAX_BYTES
        )
        if error_response is not None:
            return error_response

        # Get file content response
        try:
            return get_file_content_response(file_obj, self.MAX_BYTES)
        except OSError as e:
            log.warning(f"Error reading file content for preview: {e}")
            return JsonResponse({"error": "Error reading file"}, status=500)


class FileH5InfoView(Auth0LoginRequiredMixin, View):
    """Return a summarized structure for an HDF5 file as JSON for modal preview."""

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse | None:
        file_uuid = kwargs.get("uuid")
        if not file_uuid:
            return JsonResponse({"error": "File UUID required"}, status=400)

        file_obj = get_object_or_404(File, uuid=file_uuid, is_deleted=False)

        # Use the H5 service to handle all the complex logic
        h5_service = H5PreviewService()
        return h5_service.get_preview(file_obj, request.user)


class CheckFileExistsView(Auth0LoginRequiredMixin, View):
    """View to check if a file exists based on path, name, and checksum."""

    def get(self, request, *args, **kwargs):
        """Handle GET request to ensure CSRF token is available."""

        return JsonResponse({"csrf_token": request.META.get("CSRF_COOKIE", "")})

    def post(self, request, *args, **kwargs):
        """Check if a file exists using the provided path, name, and checksum."""
        try:
            # Get data from request
            data = json.loads(request.body)
            directory = data.get("directory", "")
            filename = data.get("filename", "")
            checksum = data.get("checksum", "")

            # Validate required fields
            if not all([directory, filename, checksum]):
                return JsonResponse(
                    {
                        "error": (
                            "Missing required fields: directory, filename, and "
                            "checksum are required"
                        )
                    },
                    status=400,
                )

            # Prepare data for check_file_contents_exist_helper
            check_data = {
                "directory": directory,
                "name": filename,
                "sum_blake3": checksum,
            }

            # Call the helper function
            response = check_file_contents_exist_helper(request, check_data)

            # Extract the response data
            if hasattr(response, "data"):
                response_data = response.data
            else:
                response_data = str(response)

            # Return the result
            return JsonResponse(
                {
                    "status_code": response.status_code,
                    "data": response_data,
                }
            )

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON in request body"}, status=400)


user_check_file_exists_view = CheckFileExistsView.as_view()


class FilesView(Auth0LoginRequiredMixin, View):
    """Handle HTML requests for the files page."""

    template_name = "users/files.html"

    def get(self, request, *args, **kwargs) -> HttpResponse:
        """Handle HTML page requests for files page."""
        # Get the current directory from query params
        current_dir = request.GET.get("dir", "/")

        # Debug logging
        log.debug(f"FilesView: current_dir={current_dir}")

        # Initialize items list with proper typing
        items: list[Item] = []

        # Parse the current directory into a navigation context
        nav_context = NavigationContext.from_path(current_dir)

        if nav_context.type == NavigationType.ROOT:
            # Root directory - show captures and datasets as folders
            items.extend(self._add_root_items(request))
        elif nav_context.type == NavigationType.CAPTURE:
            # Inside a capture - show nested directories/files within the capture
            if not nav_context.capture_uuid:
                return HttpResponseRedirect("/users/files/")
            items.extend(
                add_capture_files(
                    request, nav_context.capture_uuid, subpath=nav_context.subpath
                )
            )
        elif nav_context.type == NavigationType.DATASET:
            # Inside a dataset - show nested directories/files within the dataset
            # TODO: Implement dataset file browsing when needed
            return HttpResponseRedirect("/users/files/")
        elif nav_context.type == NavigationType.USER_FILES:
            # Inside user file directory - show nested directories/files
            items.extend(add_user_files(request, subpath=nav_context.subpath))
        else:
            # Unknown directory - go back to root
            return HttpResponseRedirect("/users/files/")

        # Build breadcrumb parts
        breadcrumb_parts = build_breadcrumbs(nav_context.to_path(), request.user.email)

        # Debug logging
        log.debug(
            f"FilesView: context summary items={len(items)}",
        )
        log.debug(
            f"FilesView: first items preview={items[:3] if items else 'No items'}",
        )

        # Additional debugging for directory items
        for i, item in enumerate(items):
            if hasattr(item, "type") and item.type == "directory":
                log.debug(f"FilesView: directory item {i} => {item}")

        # Convert Pydantic models to dictionaries for template
        items_data = items_to_dicts(items)

        return render(
            request,
            self.template_name,
            {
                "items": items_data,
                "current_dir": nav_context.to_path(),
                "breadcrumb_parts": breadcrumb_parts,
                "user_email": request.user.email,
            },
        )

    def _add_root_items(self, request) -> list[Item]:
        """Add captures and datasets to the root directory."""
        items = add_root_items(request)
        # Add shared items
        items.extend(add_shared_items(request))
        return items


def files_view(request):
    """Simple function-based view for files page."""
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return redirect("users:redirect")

    return render(
        request,
        "users/files.html",
        {
            "items": [],
            "current_dir": request.GET.get("dir", "/"),
            "breadcrumb_parts": [],
            "user_email": getattr(request.user, "email", ""),
        },
    )
