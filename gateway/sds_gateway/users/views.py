import datetime
import json
import logging
from pathlib import Path
from typing import Any
from typing import cast

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
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
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
from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.tasks import is_user_locked
from sds_gateway.api_methods.tasks import notify_shared_users
from sds_gateway.api_methods.tasks import send_dataset_files_email
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user
from sds_gateway.users.forms import CaptureSearchForm
from sds_gateway.users.forms import DatasetInfoForm
from sds_gateway.users.forms import FileSearchForm
from sds_gateway.users.mixins import ApprovedUserRequiredMixin
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.mixins import FormSearchMixin
from sds_gateway.users.mixins import UserSearchMixin
from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey
from sds_gateway.users.utils import deduplicate_composite_captures

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


class ShareDatasetView(Auth0LoginRequiredMixin, UserSearchMixin, View):
    """Handle dataset sharing functionality."""

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Handle user search requests."""
        dataset_uuid = kwargs.get("dataset_uuid")

        # Get the dataset to check existing shared users
        try:
            dataset = Dataset.objects.get(uuid=dataset_uuid, owner=request.user)
            # Get users already shared with this dataset
            shared_user_ids = list(dataset.shared_with.values_list("id", flat=True))
        except Dataset.DoesNotExist:
            return JsonResponse({"error": "Dataset not found"}, status=404)

        # Use the enhanced mixin method with exclusions
        return self.search_users(request, exclude_user_ids=shared_user_ids)

    def _parse_remove_users(self, request: HttpRequest) -> list[str]:
        """Parse the remove_users JSON from the request."""
        remove_users_json = request.POST.get("remove_users", "")
        if not remove_users_json:
            return []
        try:
            return json.loads(remove_users_json)
        except json.JSONDecodeError as err:
            msg = "Invalid remove_users format"
            raise ValueError(msg) from err

    def _add_users_to_dataset(
        self, dataset: Dataset, user_emails_str: str, request_user: User
    ) -> tuple[list[str], list[str]]:
        """Add users to dataset sharing and return (shared_users, errors)."""
        if not user_emails_str:
            return [], []

        user_emails = [
            email.strip() for email in user_emails_str.split(",") if email.strip()
        ]

        shared_users = []
        errors = []

        for user_email in user_emails:
            try:
                user_to_share_with = User.objects.get(
                    email=user_email, is_approved=True
                )

                if user_to_share_with.id == request_user.id:
                    errors.append(
                        f"You cannot share a dataset with yourself ({user_email})"
                    )
                    continue

                if dataset.shared_with.filter(id=user_to_share_with.id).exists():
                    errors.append(f"Dataset is already shared with {user_email}")
                    continue

                dataset.shared_with.add(user_to_share_with)
                shared_users.append(user_email)

            except User.DoesNotExist:
                errors.append(f"User with email {user_email} not found or not approved")

        return shared_users, errors

    def _remove_users_from_dataset(
        self, dataset: Dataset, users_to_remove: list[str]
    ) -> tuple[list[str], list[str]]:
        """Remove users from dataset sharing and return (removed_users, errors)."""
        removed_users = []
        errors = []

        for user_email in users_to_remove:
            try:
                user_to_remove = User.objects.get(email=user_email)

                if not dataset.shared_with.filter(id=user_to_remove.id).exists():
                    errors.append(f"Dataset is not shared with user: {user_email}")
                    continue

                dataset.shared_with.remove(user_to_remove)
                removed_users.append(user_email)

            except User.DoesNotExist:
                errors.append(f"User with email {user_email} not found")

        return removed_users, errors

    def _build_response(
        self, shared_users: list[str], removed_users: list[str], errors: list[str]
    ) -> JsonResponse:
        """Build the response message based on the results."""
        response_parts = []
        if shared_users:
            response_parts.append(f"Dataset shared with {', '.join(shared_users)}")
        if removed_users:
            response_parts.append(f"Removed access for {', '.join(removed_users)}")

        if response_parts and not errors:
            message = ". ".join(response_parts)
            return JsonResponse({"success": True, "message": message})
        if response_parts and errors:
            message = ". ".join(response_parts) + f". Issues: {'; '.join(errors)}"
            return JsonResponse({"success": True, "message": message})
        if not response_parts and errors:
            return JsonResponse({"error": "; ".join(errors)}, status=400)

        return JsonResponse({"success": True, "message": "No changes made"})

    def post(
        self, request: HttpRequest, dataset_uuid: str, *args: Any, **kwargs: Any
    ) -> HttpResponse:
        """Share a dataset with another user."""
        # Get the dataset
        dataset = get_object_or_404(Dataset, uuid=dataset_uuid, owner=request.user)

        # Get the user emails from the form (comma-separated string)
        user_emails_str = request.POST.get("user-search", "").strip()

        # Parse users to remove
        try:
            users_to_remove = self._parse_remove_users(request)
        except ValueError:
            return JsonResponse({"error": "Invalid remove_users format"}, status=400)

        # Handle adding new users
        shared_users, add_errors = self._add_users_to_dataset(
            dataset, user_emails_str, request.user
        )

        # Handle removing users
        removed_users, remove_errors = self._remove_users_from_dataset(
            dataset, users_to_remove
        )

        # Combine all errors
        errors = add_errors + remove_errors

        # Notify shared users if requested
        notify = request.POST.get("notify_users") == "1"
        message = request.POST.get("notify_message", "").strip() or None
        if shared_users and notify:
            notify_shared_users.delay(
                dataset.uuid, shared_users, notify=True, message=message
            )

        # Build and return response
        return self._build_response(shared_users, removed_users, errors)

    def delete(
        self, request: HttpRequest, dataset_uuid: str, *args: Any, **kwargs: Any
    ) -> HttpResponse:
        """Remove a user from dataset sharing."""
        # Get the dataset
        dataset = get_object_or_404(Dataset, uuid=dataset_uuid, owner=request.user)

        # Get the user email from the request
        user_email = request.POST.get("user_email", "").strip()

        if not user_email:
            return JsonResponse({"error": "User email is required"}, status=400)

        try:
            # Find the user to remove
            user_to_remove = User.objects.get(email=user_email)

            # Check if the user is actually shared with this dataset
            if not dataset.shared_with.filter(id=user_to_remove.id).exists():
                return JsonResponse(
                    {"error": f"User {user_email} is not shared with this dataset"},
                    status=400,
                )

            # Remove the user from the dataset
            dataset.shared_with.remove(user_to_remove)

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Removed {user_email} from dataset sharing",
                }
            )

        except User.DoesNotExist:
            return JsonResponse(
                {"error": f"User with email {user_email} not found"}, status=400
            )


user_share_dataset_view = ShareDatasetView.as_view()


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

        # Use utility function to deduplicate composite captures
        unique_captures = deduplicate_composite_captures(list(qs))

        # Paginate the unique captures
        paginator = Paginator(unique_captures, params["items_per_page"])
        try:
            page_obj = paginator.page(params["page"])
        except (EmptyPage, PageNotAnInteger):
            page_obj = paginator.page(1)

        # Serialize captures for template using composite serialization
        enhanced_captures = []
        for capture in page_obj:
            # Use composite serialization to handle multi-channel captures properly
            capture_data = serialize_capture_or_composite(capture)
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

            # Use utility function to deduplicate composite captures
            unique_captures = deduplicate_composite_captures(list(qs))

            # Limit results for API performance
            captures_list = list(unique_captures[:25])

            captures_data = []
            for capture in captures_list:
                try:
                    # Use composite serialization to handle multi-channel captures
                    # properly
                    capture_data = serialize_capture_or_composite(capture)
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


class GroupCapturesView(Auth0LoginRequiredMixin, FormSearchMixin, TemplateView):
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
                        captures = self.search_captures(form.cleaned_data, request)
                        return JsonResponse(
                            self.get_paginated_response(captures, request)
                        )
                    return JsonResponse({"error": form.errors}, status=400)

                if "search_files" in request.GET:
                    base_dir = sanitize_path_rel_to_user(
                        unsafe_path="/",
                        request=self.request,
                    )
                    form = FileSearchForm(request.GET, user=self.request.user)
                    if form.is_valid():
                        files = self.search_files(form.cleaned_data, request)
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
                for capture_id in selected_captures:
                    if not capture_id:
                        continue
                    capture = Capture.objects.get(uuid=capture_id)
                    if capture.is_multi_channel:
                        # Add all captures in this composite
                        all_captures = Capture.objects.filter(
                            top_level_dir=capture.top_level_dir,
                            owner=request.user,
                            is_deleted=False,
                        )
                        dataset.captures.add(*all_captures)
                    else:
                        dataset.captures.add(capture)

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
        selected_files: list[dict[str, Any]] = []
        selected_files_details: dict[str, Any] = {}
        if not existing_dataset:
            return selected_files, selected_files_details

        files_queryset = existing_dataset.files.filter(
            is_deleted=False,
            owner=self.request.user,
        )

        # Prepare file details for JavaScript
        for selected_file in files_queryset:
            rel_path = (
                f"{selected_file.directory.replace(str(base_dir), '')}"
                if base_dir
                else None
            )
            selected_files.append(self.serialize_item(selected_file, rel_path))

            selected_files_details[str(selected_file.uuid)] = self.serialize_item(
                selected_file,
                rel_path,
            )

        return selected_files, selected_files_details

    def _get_capture_context(
        self, existing_dataset: Dataset | None = None
    ) -> tuple[list[str], dict[str, Any]]:
        selected_captures: list[str] = []
        selected_captures_details: dict[str, Any] = {}
        composite_capture_dirs: set[str] = set()
        if existing_dataset:
            captures_queryset = existing_dataset.captures.filter(
                is_deleted=False,
                owner=self.request.user,
            )
            # Only include one composite per group
            for capture in captures_queryset.order_by("-created_at"):
                if capture.is_multi_channel:
                    if capture.top_level_dir not in composite_capture_dirs:
                        capture_dict = self.serialize_item(capture)
                        capture_uuid = str(capture_dict["id"])
                        selected_captures.append(capture_uuid)
                        selected_captures_details[capture_uuid] = capture_dict
                        composite_capture_dirs.add(capture.top_level_dir)
                else:
                    capture_dict = self.serialize_item(capture)
                    capture_uuid = str(capture_dict["id"])
                    selected_captures.append(capture_uuid)
                    selected_captures_details[capture_uuid] = capture_dict

        return selected_captures, selected_captures_details


user_group_captures_view = GroupCapturesView.as_view()


class ListDatasetsView(Auth0LoginRequiredMixin, View):
    template_name = "users/dataset_list.html"

    def get(self, request, *args, **kwargs) -> HttpResponse:
        # Get sort parameters from URL
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")

        # Define allowed sort fields
        allowed_sort_fields = {"name", "created_at", "updated_at", "authors"}

        # Apply sorting
        if sort_by in allowed_sort_fields:
            order_prefix = "-" if sort_order == "desc" else ""
            order_by = f"{order_prefix}{sort_by}"
        else:
            # Default sorting
            order_by = "-created_at"

        # Get datasets owned by the user
        owned_datasets = (
            request.user.datasets.filter(is_deleted=False).all().order_by(order_by)
        )
        # Get datasets shared with the user (exclude owned)
        shared_datasets = (
            Dataset.objects.filter(shared_with=request.user, is_deleted=False)
            .exclude(owner=request.user)
            .order_by(order_by)
        )

        # Prepare datasets with shared users and flags
        datasets_with_shared_users = []
        for dataset in owned_datasets:
            dataset_data = DatasetGetSerializer(dataset).data
            shared_users = dataset.shared_with.all()
            dataset_data["shared_users"] = [
                {"name": user.name, "email": user.email} for user in shared_users
            ]
            dataset_data["is_owner"] = True
            dataset_data["is_shared_with_me"] = False
            dataset_data["owner_name"] = (
                dataset.owner.name if dataset.owner else "Owner"
            )
            dataset_data["owner_email"] = dataset.owner.email if dataset.owner else ""
            datasets_with_shared_users.append(dataset_data)
        for dataset in shared_datasets:
            dataset_data = DatasetGetSerializer(dataset).data
            shared_users = dataset.shared_with.all()
            dataset_data["shared_users"] = [
                {"name": user.name, "email": user.email} for user in shared_users
            ]
            dataset_data["is_owner"] = False
            dataset_data["is_shared_with_me"] = True
            dataset_data["owner_name"] = (
                dataset.owner.name if dataset.owner else "Owner"
            )
            dataset_data["owner_email"] = dataset.owner.email if dataset.owner else ""
            datasets_with_shared_users.append(dataset_data)

        paginator = Paginator(datasets_with_shared_users, per_page=15)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        return render(
            request,
            template_name=self.template_name,
            context={
                "page_obj": page_obj,
                "sort_by": sort_by,
                "sort_order": sort_order,
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
    # Define allowed sort fields (actual database fields only)
    allowed_sort_fields = {
        "uuid",
        "created_at",
        "updated_at",
        "deleted_at",
        "is_deleted",
        "is_public",
        "channel",
        "scan_group",
        "capture_type",
        "top_level_dir",
        "index_name",
        "owner",
        "origin",
        "dataset",
    }

    # Handle computed properties with meaningful fallbacks
    computed_field_fallbacks = {
        # Could be enhanced with OpenSearch sorting later
        "center_frequency_ghz": "created_at",
        "sample_rate_mhz": "created_at",
    }

    # Check if it's a computed field first
    if sort_by in computed_field_fallbacks:
        # For now, fall back to a meaningful sort field
        # In the future, this could be enhanced to sort by OpenSearch data
        fallback_field = computed_field_fallbacks[sort_by]
        if sort_order == "desc":
            return qs.order_by(f"-{fallback_field}")
        return qs.order_by(fallback_field)

    # Only apply sorting if the field is allowed
    if sort_by in allowed_sort_fields:
        if sort_order == "desc":
            return qs.order_by(f"-{sort_by}")
        return qs.order_by(sort_by)

    # Default sorting if field is not recognized
    return qs.order_by("-created_at")


user_dataset_list_view = ListDatasetsView.as_view()


class DatasetDownloadView(Auth0LoginRequiredMixin, View):
    """View to handle dataset download requests from the web interface."""

    def post(self, request, *args, **kwargs):
        """Handle dataset download request."""
        dataset_uuid = kwargs.get("uuid")
        if not dataset_uuid:
            return JsonResponse(
                {"success": False, "message": "Dataset UUID is required."},
                status=400,
            )

        # Get the dataset - allow both owners and shared users to download
        dataset = get_object_or_404(
            Dataset,
            uuid=dataset_uuid,
            is_deleted=False,
        )

        # Check if user is owner or shared user
        is_owner = dataset.owner == request.user
        is_shared_user = request.user in dataset.shared_with.all()

        if not (is_owner or is_shared_user):
            return JsonResponse(
                {"detail": "You don't have permission to download this dataset."},
                status=403,
            )

        # Get user email
        user_email = request.user.email
        if not user_email:
            return JsonResponse(
                {
                    "success": False,
                    "message": ("User email is required for sending dataset files."),
                },
                status=400,
            )

        # Check if a user already has a task running
        if is_user_locked(str(request.user.id), "dataset_download"):
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "You already have a dataset download in progress. "
                        "Please wait for it to complete."
                    ),
                },
                status=400,
            )

        # Trigger the Celery task
        task = send_dataset_files_email.delay(
            str(dataset.uuid),
            str(request.user.id),
        )

        return JsonResponse(
            {
                "success": True,
                "message": (
                    "Dataset download request accepted. You will receive an email "
                    "with the files shortly."
                ),
                "task_id": task.id,
                "dataset_name": dataset.name,
                "user_email": user_email,
            },
            status=202,
        )


user_dataset_download_view = DatasetDownloadView.as_view()


class TemporaryZipDownloadView(Auth0LoginRequiredMixin, View):
    """View to display a temporary zip file download page and serve the file."""

    template_name = "users/temporary_zip_download.html"

    def get(self, request, *args, **kwargs) -> HttpResponse:
        """Display download page for a temporary zip file or serve the file."""
        zip_uuid = kwargs.get("uuid")
        if not zip_uuid:
            logger.warning("No UUID provided in temporary zip download request")
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

        except TemporaryZipFile.DoesNotExist:
            logger.warning(
                "Temporary zip file not found: %s for user: %s",
                zip_uuid,
                request.user.id,
            )
            error_msg = "File not found."
            raise Http404(error_msg) from None

    def _serve_file_download(self, zip_uuid: str, user) -> HttpResponse:
        """Serve the zip file for download."""
        try:
            # Get the temporary zip file
            temp_zip = get_object_or_404(
                TemporaryZipFile,
                uuid=zip_uuid,
                owner=user,
            )

            logger.info("Found temporary zip file: %s", temp_zip.filename)

            file_path = Path(temp_zip.file_path)
            if not file_path.exists():
                logger.warning("File not found on disk: %s", temp_zip.file_path)
                return JsonResponse(
                    {"error": "The file was not found on the server."}, status=404
                )

            file_size = file_path.stat().st_size

            with file_path.open("rb") as f:
                file_content = f.read()
                response = HttpResponse(file_content, content_type="application/zip")
                response["Content-Disposition"] = (
                    f'attachment; filename="{temp_zip.filename}"'
                )
                response["Content-Length"] = file_size

                # Mark the file as downloaded
                temp_zip.mark_downloaded()

                return response

        except OSError:
            logger.exception("Error reading file: %s", temp_zip.file_path)
            return JsonResponse({"error": "Error reading file."}, status=500)


user_temporary_zip_download_view = TemporaryZipDownloadView.as_view()
