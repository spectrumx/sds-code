import datetime
import json
import logging
from pathlib import Path
from typing import Any
from typing import cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import EmptyPage
from django.core.paginator import PageNotAnInteger
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError
from django.db.models import Q
from django.db.models.query import QuerySet
from django.db.utils import IntegrityError
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import TemplateView
from django.views.generic import UpdateView

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import KeySources
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user
from sds_gateway.users.forms import CaptureSearchForm
from sds_gateway.users.forms import DatasetInfoForm
from sds_gateway.users.forms import FileSearchForm
from sds_gateway.users.mixins import ApprovedUserRequiredMixin
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.mixins import FormSearchMixin
from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey

# Add logger for debugging
logger = logging.getLogger(__name__)


class UserDetailView(Auth0LoginRequiredMixin, DetailView):  # pyright: ignore[reportMissingTypeArgument]
    model = User
    slug_field = "id"
    slug_url_arg = "id"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(Auth0LoginRequiredMixin, SuccessMessageMixin, UpdateView):  # pyright: ignore[reportMissingTypeArgument]
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self):
        # for mypy to know that the user is authenticated
        assert self.request.user.is_authenticated
        return self.request.user.get_absolute_url()

    def get_object(self, queryset=None) -> AbstractBaseUser | AnonymousUser:
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(Auth0LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self) -> str:
        return reverse("users:generate_api_key")


user_redirect_view = UserRedirectView.as_view()


class GenerateAPIKeyView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    template_name = "users/user_api_key.html"

    def get(self, request, *args, **kwargs):
        # check if API key expired
        api_key = (
            UserAPIKey.objects.filter(user=request.user)
            .exclude(source=KeySources.SVIBackend)
            .first()
        )
        if api_key is None:
            return render(
                request,
                template_name=self.template_name,
                context={
                    "api_key": False,
                    "expires_at": None,
                    "expired": False,
                },
            )

        return render(
            request,
            template_name=self.template_name,
            context={
                "api_key": True,  # return True if API key exists
                "expires_at": api_key.expiry_date.strftime("%Y-%m-%d %H:%M:%S")
                if api_key.expiry_date
                else "Does not expire",
                "expired": api_key.expiry_date < datetime.datetime.now(datetime.UTC)
                if api_key.expiry_date
                else False,
            },
        )

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Regenerates an API key for the authenticated user."""
        existing_api_key = (
            UserAPIKey.objects.filter(user=request.user)
            .exclude(source=KeySources.SVIBackend)
            .first()
        )
        if existing_api_key:
            existing_api_key.delete()

        # create an API key for the user (with no expiration date for now)
        _, raw_key = UserAPIKey.objects.create_key(
            name=request.user.email,
            user=request.user,
            source=KeySources.SDSWebUI,
        )
        return render(
            request,
            template_name=self.template_name,
            context={
                "api_key": raw_key,  # key only returned when API key is created
                "expires_at": None,
                "expired": False,
            },
        )


user_generate_api_key_view = GenerateAPIKeyView.as_view()


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


class ListCapturesView(Auth0LoginRequiredMixin, View):
    """Handle HTML requests for the captures list page."""

    template_name = "users/file_list.html"
    default_items_per_page = 25
    max_items_per_page = 100

    def _extract_request_params(self, request):
        """Extract and return request parameters for HTML view."""
        return {
            "page": int(request.GET.get("page", 1)),
            "sort_by": request.GET.get("sort_by", "created_at"),
            "sort_order": request.GET.get("sort_order", "desc"),
            "search": request.GET.get("search", ""),
            "date_start": request.GET.get("date_start", ""),
            "date_end": request.GET.get("date_end", ""),
            "cap_type": request.GET.get("capture_type", ""),
            "min_freq": request.GET.get("min_freq", ""),
            "max_freq": request.GET.get("max_freq", ""),
            "items_per_page": min(
                int(request.GET.get("items_per_page", self.default_items_per_page)),
                self.max_items_per_page,
            ),
        }

    def get(self, request, *args, **kwargs) -> HttpResponse:
        """Handle HTML page requests for captures list."""
        # Extract request parameters
        params = self._extract_request_params(request)

        # Query database for captures
        qs = request.user.captures.filter(is_deleted=False)

        # Apply all filters
        qs = _apply_basic_filters(
            qs=qs,
            search=params["search"],
            date_start=params["date_start"],
            date_end=params["date_end"],
            cap_type=params["cap_type"],
        )
        qs = _apply_frequency_filters(
            qs=qs, min_freq=params["min_freq"], max_freq=params["max_freq"]
        )

        qs = _apply_sorting(
            qs=qs, sort_by=params["sort_by"], sort_order=params["sort_order"]
        )

        # Paginate the results
        paginator = Paginator(qs, params["items_per_page"])
        try:
            page_obj = paginator.page(params["page"])
        except (EmptyPage, PageNotAnInteger):
            page_obj = paginator.page(1)

        # Serialize captures for template
        enhanced_captures = []
        for capture in page_obj:
            # CaptureGetSerializer includes all computed fields
            capture_data = CaptureGetSerializer(capture).data
            enhanced_captures.append(capture_data)

        # Update the page_obj with enhanced captures
        page_obj.object_list = enhanced_captures

        return render(
            request,
            self.template_name,
            {
                "captures": page_obj,
                "sort_by": params["sort_by"],
                "sort_order": params["sort_order"],
                "search": params["search"],
                "date_start": params["date_start"],
                "date_end": params["date_end"],
                "capture_type": params["cap_type"],
                "min_freq": params["min_freq"],
                "max_freq": params["max_freq"],
                "items_per_page": params["items_per_page"],
            },
        )


class CapturesAPIView(Auth0LoginRequiredMixin, View):
    """Handle API/JSON requests for captures search."""

    def _extract_request_params(self, request):
        """Extract and return request parameters for API view."""
        return {
            "sort_by": request.GET.get("sort_by", "created_at"),
            "sort_order": request.GET.get("sort_order", "desc"),
            "search": request.GET.get("search", ""),
            "date_start": request.GET.get("date_start", ""),
            "date_end": request.GET.get("date_end", ""),
            "cap_type": request.GET.get("capture_type", ""),
            "min_freq": request.GET.get("min_freq", ""),
            "max_freq": request.GET.get("max_freq", ""),
        }

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """Handle AJAX requests for the captures API."""
        logger = logging.getLogger(__name__)

        try:
            # Extract and validate parameters
            params = self._extract_request_params(request)

            # Start with base queryset
            qs = Capture.objects.filter(owner=request.user)

            # Apply filters
            qs = _apply_basic_filters(
                qs=qs,
                search=params["search"],
                date_start=params["date_start"],
                date_end=params["date_end"],
                cap_type=params["cap_type"],
            )
            qs = _apply_frequency_filters(
                qs=qs, min_freq=params["min_freq"], max_freq=params["max_freq"]
            )

            qs = _apply_sorting(
                qs=qs, sort_by=params["sort_by"], sort_order=params["sort_order"]
            )

            # Limit results for API performance
            captures_list = list(qs[:25])

            captures_data = []
            for capture in captures_list:
                try:
                    # Use CaptureGetSerializer - includes all computed fields
                    capture_data = CaptureGetSerializer(capture).data
                    captures_data.append(capture_data)
                except Exception:
                    logger.exception("Error serializing capture %s", capture.uuid)
                    raise

            response_data = {
                "captures": captures_data,
                "has_results": len(captures_data) > 0,
                "total_count": len(captures_data),
            }
            return JsonResponse(response_data)

        except Exception as e:
            logger.exception("API request failed")
            return JsonResponse({"error": f"Search failed: {e!s}"}, status=500)


user_capture_list_view = ListCapturesView.as_view()
user_captures_api_view = CapturesAPIView.as_view()


class GroupCapturesView(LoginRequiredMixin, FormSearchMixin, TemplateView):
    template_name = "users/group_captures.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_dir = sanitize_path_rel_to_user(
            unsafe_path="/",
            request=self.request,
        )

        # Check if we're editing an existing dataset
        dataset_uuid = self.request.GET.get("dataset_uuid", None)
        existing_dataset = None
        if dataset_uuid:
            existing_dataset = get_object_or_404(
                Dataset, uuid=dataset_uuid, owner=self.request.user
            )

        # Get form
        if self.request.method == "POST":
            dataset_form = DatasetInfoForm(self.request.POST, user=self.request.user)
        else:
            initial_data = {}
            if existing_dataset:
                initial_data = {
                    "name": existing_dataset.name,
                    "description": existing_dataset.description,
                    "author": existing_dataset.authors[0],
                }
            dataset_form = DatasetInfoForm(user=self.request.user, initial=initial_data)

        selected_files, selected_files_details = self._get_file_context(
            base_dir=base_dir, existing_dataset=existing_dataset
        )
        selected_captures, selected_captures_details = self._get_capture_context(
            existing_dataset=existing_dataset
        )

        # Add to context
        context.update(
            {
                "dataset_form": dataset_form,
                "capture_search_form": CaptureSearchForm(),
                "file_search_form": FileSearchForm(user=self.request.user),
                "selected_captures": json.dumps(
                    selected_captures, cls=DjangoJSONEncoder
                ),
                "selected_files": json.dumps(selected_files, cls=DjangoJSONEncoder),
                "form": dataset_form,
                "existing_dataset": existing_dataset,
                "selected_captures_details_json": json.dumps(
                    selected_captures_details, cls=DjangoJSONEncoder
                ),
                "selected_files_details_json": json.dumps(
                    selected_files_details, cls=DjangoJSONEncoder
                ),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            try:
                if "search_captures" in request.GET:
                    form = CaptureSearchForm(request.GET)
                    if form.is_valid():
                        captures = self.search_captures(form.cleaned_data)
                        return JsonResponse(self.get_paginated_response(captures))
                    return JsonResponse({"error": form.errors}, status=400)

                if "search_files" in request.GET:
                    base_dir = sanitize_path_rel_to_user(
                        unsafe_path="/",
                        request=self.request,
                    )
                    form = FileSearchForm(request.GET, user=self.request.user)
                    if form.is_valid():
                        files = self.search_files(form.cleaned_data)
                        return JsonResponse(
                            {
                                "tree": self._get_directory_tree(files, str(base_dir)),
                                "extension_choices": form.fields[
                                    "file_extension"
                                ].choices,
                                "search_values": {
                                    "file_name": form.cleaned_data.get("file_name", ""),
                                    "file_extension": form.cleaned_data.get(
                                        "file_extension", ""
                                    ),
                                    "directory": form.cleaned_data.get("directory", ""),
                                },
                            },
                        )
                    return JsonResponse({"error": form.errors}, status=400)
            except (OSError, DatabaseError) as e:
                return JsonResponse({"error": str(e)}, status=500)

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Handle dataset creation/update with selected captures and files."""
        try:
            # Process the dataset form for actual submission
            dataset_form = DatasetInfoForm(request.POST, user=request.user)
            if not dataset_form.is_valid():
                return JsonResponse(
                    {"success": False, "errors": dataset_form.errors},
                    status=400,
                )

            # Get selected captures and files from hidden fields
            selected_captures = request.POST.get("selected_captures", "").split(",")
            selected_files = request.POST.get("selected_files", "").split(",")

            # Validate that at least one capture or file is selected
            if not selected_captures[0] and not selected_files[0]:
                return JsonResponse(
                    {
                        "success": False,
                        "errors": {
                            "non_field_errors": [
                                "Please select at least one capture or file.",
                            ],
                        },
                    },
                    status=400,
                )

            # Check if we're editing an existing dataset
            dataset_uuid = request.GET.get("dataset_uuid", None)
            if dataset_uuid:
                dataset = get_object_or_404(
                    Dataset, uuid=dataset_uuid, owner=request.user
                )
                dataset.name = dataset_form.cleaned_data["name"]
                dataset.description = dataset_form.cleaned_data["description"]
                dataset.authors = [dataset_form.cleaned_data["author"]]
                dataset.save()

                # Clear existing relationships
                dataset.captures.clear()
                dataset.files.clear()
            else:
                # Create new dataset
                dataset = Dataset.objects.create(
                    name=dataset_form.cleaned_data["name"],
                    description=dataset_form.cleaned_data["description"],
                    authors=[dataset_form.cleaned_data["author"]],
                    owner=request.user,
                )

            # Add selected captures to the dataset
            if selected_captures[0]:
                captures = Capture.objects.filter(uuid__in=selected_captures)
                dataset.captures.add(*captures)

            # Add selected files to the dataset
            if selected_files[0]:
                files = File.objects.filter(uuid__in=selected_files)
                dataset.files.add(*files)

            # Return success response with redirect URL
            return JsonResponse(
                {"success": True, "redirect_url": reverse("users:dataset_list")},
            )

        except (DatabaseError, IntegrityError) as e:
            return JsonResponse(
                {"success": False, "errors": {"non_field_errors": [str(e)]}},
                status=500,
            )

    def _get_directory_tree(
        self, files: QuerySet[File], base_dir: str
    ) -> dict[str, Any]:
        """Build a nested directory tree structure."""
        tree = {}

        # Add files in base directory if they exist
        tree["files"] = self._add_files_to_tree(files, base_dir)

        # Initialize the children
        tree["children"] = {}

        # Get all directories that start with base_dir
        distinct_file_paths = (
            files.filter(directory__startswith=base_dir)
            .values_list("directory", flat=True)
            .distinct()
        )

        for file_path in distinct_file_paths:
            # Skip if it's the base directory itself
            if file_path == base_dir:
                continue

            # Get relative path from base_dir
            rel_path = file_path.replace(base_dir, "").strip("/")
            if not rel_path:
                continue

            # Split path into parts and build nested structure
            path_parts = rel_path.split("/")

            # initialize the children
            current_dict = tree["children"]

            # Build the path one level at a time
            current_path = base_dir
            for part in path_parts:
                current_path = f"{current_path}/{part}"

                if part not in current_dict:
                    current_dict[part] = {
                        "type": "directory",
                        "name": part,
                        "path": current_path,
                        "children": {},
                        "files": [],
                        "size": 0,
                        "created_at": None,
                    }
                    # Add files for this directory level
                    current_dict[part]["files"] = self._add_files_to_tree(
                        files,
                        current_path,
                    )

                # Move to the children dictionary for the next iteration
                current_dict = current_dict[part]["children"]

        # Now that the tree is built, calculate stats for all directories
        self._update_directory_stats(tree)
        return tree

    def _update_directory_stats(self, tree: dict[str, Any]) -> None:
        """Update size and date stats for all directories in the tree."""
        # Process all directories first
        for dir_data in tree.get("children", {}).values():
            self._update_directory_stats(dir_data)

        # Then calculate stats for current directory
        total_size = 0
        earliest_date = None

        # Process files in current directory
        for file in tree.get("files", []):
            total_size += file["size"]
            if file["created_at"]:
                if not earliest_date or file["created_at"] < earliest_date:
                    earliest_date = file["created_at"]

        # Add stats from all subdirectories
        for dir_data in tree.get("children", {}).values():
            total_size += dir_data["size"]
            dir_date = dir_data["created_at"]
            if dir_date:
                if not earliest_date or dir_date < earliest_date:
                    earliest_date = dir_date

        # Update current directory stats
        tree["size"] = total_size
        tree["created_at"] = earliest_date

    def _add_files_to_tree(
        self, files: QuerySet[File], directory: str
    ) -> list[dict[str, Any]]:
        files_in_directory = files.filter(directory=directory)
        return [
            {
                "id": str(file.uuid),
                "name": file.name,
                "type": "file",
                "media_type": file.media_type,
                "size": file.size,
                "created_at": file.created_at,
            }
            for file in files_in_directory
        ]

    def _get_file_context(
        self,
        base_dir: Path | None = None,
        existing_dataset: Dataset | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        selected_files = []
        selected_files_details = {}
        if not existing_dataset:
            return selected_files, selected_files_details

        files_queryset = existing_dataset.files.all()

        # Prepare file details for JavaScript
        for selected_file in files_queryset:
            rel_path = (
                f"{selected_file.directory.replace(str(base_dir), '')}"
                if base_dir
                else None
            )
            selected_files.append(
                {
                    "id": str(selected_file.uuid),
                    "name": selected_file.name,
                    "media_type": selected_file.media_type,
                    "size": selected_file.size,
                    "relative_path": rel_path,
                }
            )
            selected_files_details[str(selected_file.uuid)] = {
                "name": selected_file.name,
                "media_type": selected_file.media_type,
                "size": selected_file.size,
                "relative_path": rel_path,
            }

        return selected_files, selected_files_details

    def _get_capture_context(
        self, existing_dataset: Dataset | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        selected_captures = []
        selected_captures_details = {}
        if existing_dataset:
            captures_queryset = existing_dataset.captures.all()
            # Prepare capture details for JavaScript
            for capture in captures_queryset:
                selected_captures.append(str(capture.uuid))
                selected_captures_details[str(capture.uuid)] = {
                    "type": "RadioHound"
                    if capture.capture_type == "rh"
                    else "DigitalRF"
                    if capture.capture_type == "drf"
                    else capture.capture_type,
                    "directory": capture.top_level_dir.split("/")[-1],
                    "channel": capture.channel or "-",
                    "scan_group": capture.scan_group or "-",
                    "created_at": capture.created_at.isoformat(),
                }

        return selected_captures, selected_captures_details


user_group_captures_view = GroupCapturesView.as_view()


class ListDatasetsView(Auth0LoginRequiredMixin, View):
    template_name = "users/dataset_list.html"

    def get(self, request, *args, **kwargs) -> HttpResponse:
        datasets = (
            request.user.datasets.filter(is_deleted=False).all().order_by("-created_at")
        )
        serializer = DatasetGetSerializer(datasets, many=True)
        paginator = Paginator(serializer.data, per_page=15)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        return render(
            request,
            template_name=self.template_name,
            context={
                "page_obj": page_obj,
            },
        )


def _apply_basic_filters(
    qs: QuerySet[Capture],
    search: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    cap_type: str | None = None,
) -> QuerySet[Capture]:
    """Apply basic filters: search, date range, and capture type."""
    if search:
        qs = qs.filter(
            Q(channel__icontains=search)
            | Q(index_name__icontains=search)
            | Q(capture_type__icontains=search)
            | Q(uuid__icontains=search)
        )
    if date_start:
        qs = qs.filter(created_at__gte=date_start)
    if date_end:
        qs = qs.filter(created_at__lte=date_end)
    if cap_type:
        qs = qs.filter(capture_type=cap_type)

    return qs


def _apply_frequency_filters(
    qs: QuerySet[Capture], min_freq: str, max_freq: str
) -> QuerySet[Capture]:
    """Apply center frequency range filters using OpenSearch data (fast!)."""
    # Only apply frequency filtering if meaningful parameters are provided
    min_freq_str = str(min_freq).strip() if min_freq else ""
    max_freq_str = str(max_freq).strip() if max_freq else ""

    # If both frequency parameters are empty, don't apply frequency filtering
    if not min_freq_str and not max_freq_str:
        return qs

    # Convert to float, skip filtering if invalid values
    try:
        min_freq_val = float(min_freq_str) if min_freq_str else None
    except ValueError:
        min_freq_val = None

    try:
        max_freq_val = float(max_freq_str) if max_freq_str else None
    except ValueError:
        max_freq_val = None

    # If both conversions failed, don't apply frequency filtering
    if min_freq_val is None and max_freq_val is None:
        return qs

    try:
        # Bulk load frequency metadata for all captures
        frequency_data = Capture.bulk_load_frequency_metadata(qs)

        filtered_uuids = []
        for capture in qs:
            capture_uuid = str(capture.uuid)
            freq_info = frequency_data.get(capture_uuid, {})
            center_freq_hz = freq_info.get("center_frequency")

            if center_freq_hz is None:
                # If no frequency data and filters are active, exclude it
                continue  # Skip this capture

            center_freq_ghz = center_freq_hz / 1e9

            # Apply frequency range filter
            if min_freq_val is not None and center_freq_ghz < min_freq_val:
                continue  # Skip this capture
            if max_freq_val is not None and center_freq_ghz > max_freq_val:
                continue  # Skip this capture

            # Capture passed all filters
            filtered_uuids.append(capture.uuid)

        return qs.filter(uuid__in=filtered_uuids)

    except Exception:
        logger.exception("Error applying frequency filters")
        return qs  # Return unfiltered queryset on error


def _apply_sorting(
    qs: QuerySet[Capture],
    sort_by: str,
    sort_order: str = "desc",
):
    """Apply sorting to the queryset."""
    if sort_order == "desc":
        return qs.order_by(f"-{sort_by}")
    return qs.order_by(sort_by)


user_dataset_list_view = ListDatasetsView.as_view()
