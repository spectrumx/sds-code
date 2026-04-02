import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import cast
from uuid import UUID

from django.contrib import messages
from django.core.paginator import EmptyPage
from django.core.paginator import PageNotAnInteger
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError
from django.db import transaction
from django.db.models import Q
from django.db.models import Sum
from django.db.models.query import QuerySet
from django.db.utils import IntegrityError
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.defaultfilters import slugify
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from loguru import logger as log

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import Keyword
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.models import get_shared_users_for_item
from sds_gateway.api_methods.models import get_user_permission_level
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer
from sds_gateway.api_methods.serializers.dataset_serializers import (
    get_dataset_serializer,
)
from sds_gateway.api_methods.utils.relationship_utils import (
    get_dataset_files_including_captures,
)
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user
from sds_gateway.users.forms import CaptureSearchForm
from sds_gateway.users.forms import DatasetInfoForm
from sds_gateway.users.forms import FileSearchForm
from sds_gateway.users.forms import PublishedDatasetSearchForm
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.mixins import FileTreeMixin
from sds_gateway.users.mixins import FormSearchMixin
from sds_gateway.users.models import User
from sds_gateway.users.utils import deduplicate_composite_captures

from .captures import _apply_frequency_filters_to_list

if TYPE_CHECKING:
    from rest_framework.utils.serializer_helpers import ReturnDict


class GroupCapturesView(
    Auth0LoginRequiredMixin, FormSearchMixin, FileTreeMixin, TemplateView
):
    template_name = "users/group_captures.html"

    # ========== Helper Methods ==========

    def _parse_dataset_uuid(
        self, dataset_uuid_str: str, *, raise_on_error: bool = False
    ) -> UUID | None:
        """
        Parse dataset UUID string with consistent error handling.

        Args:
            dataset_uuid_str: String representation of UUID
            raise_on_error: If True, raises Http404 on error. If False, returns None.

        Returns:
            UUID object if valid, None if invalid (when raise_on_error=False)

        Raises:
            Http404: If raise_on_error=True and UUID is invalid
        """
        try:
            return UUID(dataset_uuid_str)
        except ValueError as err:
            if raise_on_error:
                msg = "Invalid dataset UUID."
                raise Http404(msg) from err
            return None

    def _parse_comma_separated_ids(self, value: str) -> list[str]:
        """
        Parse comma-separated IDs from a string.

        Args:
            value: Comma-separated string of IDs

        Returns:
            List of trimmed, non-empty IDs
        """
        if not value:
            return []
        return [item_id.strip() for item_id in value.split(",") if item_id.strip()]

    def _get_error_response(
        self,
        message: str | None = None,
        errors: dict | None = None,
        status_code: int = 400,
    ) -> JsonResponse:
        """
        Create standardized error response.

        Args:
            message: Single error message (for non_field_errors)
            errors: Dictionary of field errors
            status_code: HTTP status code

        Returns:
            JsonResponse with standardized error format
        """
        if message:
            return JsonResponse(
                {
                    "success": False,
                    "errors": {"non_field_errors": [message]},
                },
                status=status_code,
            )
        if errors:
            return JsonResponse(
                {"success": False, "errors": errors},
                status=status_code,
            )
        return JsonResponse(
            {"success": False, "errors": {"non_field_errors": ["An error occurred."]}},
            status=status_code,
        )

    def _get_dataset(
        self, dataset_uuid: UUID, user: User | None = None, *, raise_404: bool = True
    ) -> Dataset | None:
        """
        Safely retrieve a dataset with consistent error handling.

        Args:
            dataset_uuid: UUID of the dataset
            user: Optional user to filter by owner
            raise_404: If True, raises Http404 if not found. If False, returns None.

        Returns:
            Dataset object if found, None if not found (when raise_404=False)

        Raises:
            Http404: If raise_404=True and dataset not found
        """
        if raise_404:
            if user:
                return get_object_or_404(Dataset, uuid=dataset_uuid, owner=user)
            return get_object_or_404(Dataset, uuid=dataset_uuid)

        # When raise_404=False, use objects.get() to return None instead of raising
        try:
            filters = {"uuid": dataset_uuid}
            if user:
                filters["owner"] = user
            return Dataset.objects.get(**filters)
        except Dataset.DoesNotExist:
            return None

    def _get_capture(
        self, capture_id: str, user: User | None = None, *, require_owner: bool = False
    ) -> Capture | None:
        """
        Safely retrieve a capture with consistent error handling.

        Args:
            capture_id: UUID string of the capture
            user: Optional user to filter by owner
            require_owner: If True, only returns captures owned by user

        Returns:
            Capture object if found and accessible, None otherwise
        """
        try:
            filters = {"uuid": capture_id, "is_deleted": False}
            if require_owner and user:
                filters["owner"] = user
            # Additional check if user provided but require_owner is False
            # Still allow if user has access (for shared captures)
            return Capture.objects.get(**filters)
        except Capture.DoesNotExist:
            return None

    def _get_file(
        self, file_id: str, user: User | None = None, *, require_owner: bool = False
    ) -> File | None:
        """
        Safely retrieve a file with consistent error handling.

        Args:
            file_id: UUID string of the file
            user: Optional user to filter by owner
            require_owner: If True, only returns files owned by user

        Returns:
            File object if found and accessible, None otherwise
        """
        try:
            filters = {"uuid": file_id, "is_deleted": False}
            if require_owner and user:
                filters["owner"] = user
            return File.objects.get(**filters)
        except File.DoesNotExist:
            return None

    def _process_keywords(self, dataset: Dataset, raw_keywords: str) -> None:
        """
        Process and associate keywords with a dataset.

        Args:
            dataset: Dataset to associate keywords with
            raw_keywords: Comma-separated string of keywords
        """
        if not raw_keywords:
            return

        # Slugify and deduplicate keywords
        slugified_keywords = {
            slugify(p.strip())
            for p in raw_keywords.split(",")
            if p.strip() and slugify(p.strip())
        }

        # Get or create keywords and associate them with the dataset
        for slug in slugified_keywords:
            keyword, _created = Keyword.objects.get_or_create(name=slug)
            keyword.datasets.add(dataset)

    def _get_permission_cache(
        self, user: User, dataset_uuid: UUID
    ) -> dict[str, bool | PermissionLevel | None]:
        """
        Get and cache permission information for a user and dataset.

        Args:
            user: User to check permissions for
            dataset_uuid: UUID of the dataset

        Returns:
            Dictionary with permission information
        """
        return {
            "has_access": user_has_access_to_item(user, dataset_uuid, ItemType.DATASET),
            "permission_level": get_user_permission_level(
                user, dataset_uuid, ItemType.DATASET
            ),
            "can_edit_dataset": UserSharePermission.user_can_edit_dataset(
                user, dataset_uuid, ItemType.DATASET
            ),
            "can_add_assets": UserSharePermission.user_can_add_assets(
                user, dataset_uuid, ItemType.DATASET
            ),
            "can_remove_assets": UserSharePermission.user_can_remove_assets(
                user, dataset_uuid, ItemType.DATASET
            ),
            "can_remove_others_assets": (
                UserSharePermission.user_can_remove_others_assets(
                    user, dataset_uuid, ItemType.DATASET
                )
            ),
        }

    # ========== View Methods ==========

    def get(self, request, *args, **kwargs):
        """Handle GET request with permission checking and AJAX requests."""
        dataset_uuid = request.GET.get("dataset_uuid")

        # Validate dataset permissions if editing
        if dataset_uuid:
            validation_error = self._validate_dataset_edit_permissions(
                request, dataset_uuid
            )
            if validation_error:
                return validation_error

        # Handle AJAX requests
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            ajax_response = self._handle_ajax_request(request)
            if ajax_response:
                return ajax_response

        return super().get(request, *args, **kwargs)

    def _validate_dataset_edit_permissions(
        self, request: HttpRequest, dataset_uuid: str
    ) -> HttpResponseRedirect | None:
        """Validate user permissions for editing a dataset."""
        # Check if user has access to edit this dataset
        if not user_has_access_to_item(request.user, dataset_uuid, ItemType.DATASET):
            messages.error(request, "Dataset not found or access denied.")
            return redirect("users:dataset_list")

        # Get the dataset to check its status
        dataset = get_object_or_404(Dataset, uuid=dataset_uuid)

        # Check if dataset is final (published) - cannot be edited
        if dataset.status == DatasetStatus.FINAL or dataset.is_public:
            messages.error(request, "This dataset is published and cannot be edited.")
            return redirect("users:dataset_list")

        # Check if user can edit dataset metadata
        if not UserSharePermission.user_can_edit_dataset(
            request.user, dataset_uuid, ItemType.DATASET
        ) and not UserSharePermission.user_can_add_assets(
            request.user, dataset_uuid, ItemType.DATASET
        ):
            messages.error(request, "You don't have permission to edit this dataset.")
            return redirect("users:dataset_list")

        return None

    def _handle_ajax_request(self, request: HttpRequest) -> JsonResponse | None:
        """Handle AJAX requests for search operations."""
        try:
            if "search_captures" in request.GET:
                return self._handle_capture_search(request)

            if "search_files" in request.GET:
                return self._handle_file_search(request)

        except (OSError, DatabaseError) as e:
            return JsonResponse({"error": str(e)}, status=500)

        return None

    def _handle_capture_search(self, request: HttpRequest) -> JsonResponse:
        """Handle AJAX request for capture search."""
        form = CaptureSearchForm(request.GET)
        if form.is_valid():
            captures = self.search_captures(form.cleaned_data, request)
            return JsonResponse(self.get_paginated_response(captures, request))
        return self._get_error_response(errors=form.errors, status_code=400)

    def _handle_file_search(self, request: HttpRequest) -> JsonResponse:
        """Handle AJAX request for file search."""
        base_dir = sanitize_path_rel_to_user(
            unsafe_path="/",
            request=request,
        )

        form = FileSearchForm(request.GET, user=request.user)
        if form.is_valid():
            files = self.search_files(form.cleaned_data, request)
            tree_data = self._get_directory_tree(files, str(base_dir))

            return JsonResponse(
                {
                    "tree": tree_data,
                    "extension_choices": form.fields["file_extension"].choices,
                    "search_values": {
                        "file_name": form.cleaned_data.get("file_name", ""),
                        "file_extension": form.cleaned_data.get("file_extension", ""),
                        "directory": form.cleaned_data.get("directory", ""),
                    },
                },
            )
        return self._get_error_response(errors=form.errors, status_code=400)

    def search_captures(self, search_data, request) -> list[Capture]:
        """Override to only return captures owned by the user for dataset creation."""
        # Only get captures owned by the user (no shared captures)
        queryset = Capture.objects.filter(
            owner=request.user,
            is_deleted=False,
        )

        # Build a Q object for complex queries
        q_objects = Q()

        if search_data.get("directory"):
            q_objects &= Q(top_level_dir__icontains=search_data["directory"])
        if search_data.get("capture_type"):
            q_objects &= Q(capture_type=search_data["capture_type"])
        if search_data.get("scan_group"):
            q_objects &= Q(scan_group__icontains=search_data["scan_group"])
        if search_data.get("channel"):
            q_objects &= Q(channel__icontains=search_data["channel"])

        queryset = queryset.filter(q_objects).order_by("-created_at")

        # Use utility function to deduplicate composite captures
        return deduplicate_composite_captures(list(queryset))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_dir = sanitize_path_rel_to_user(
            unsafe_path="/",
            request=self.request,
        )

        # Check if we're editing an existing dataset
        dataset_uuid_str = self.request.GET.get("dataset_uuid", None)
        existing_dataset = None
        permission_level = None
        is_owner = False
        dataset_uuid = None

        if dataset_uuid_str:
            dataset_uuid = self._parse_dataset_uuid(
                dataset_uuid_str, raise_on_error=True
            )

            # Check if user has access to this dataset
            if not user_has_access_to_item(
                self.request.user, dataset_uuid, ItemType.DATASET
            ):
                msg = "Dataset not found or access denied."
                raise Http404(msg)

            # Get the dataset - it exists and user has access
            existing_dataset = self._get_dataset(dataset_uuid, raise_404=True)
            permission_level = get_user_permission_level(
                self.request.user, dataset_uuid, ItemType.DATASET
            )
            is_owner = existing_dataset.owner == self.request.user
        else:
            # For new dataset creation, user is always the owner
            permission_level = PermissionLevel.OWNER
            is_owner = True

        # Get form
        if self.request.method == "POST":
            dataset_form = DatasetInfoForm(self.request.POST, user=self.request.user)
        else:
            initial_data = {}
            if existing_dataset:
                authors_json = self._set_authors_el_ids(
                    existing_dataset.get_authors_display()
                )

                initial_data = {
                    "name": existing_dataset.name,
                    "description": existing_dataset.description,
                    "keywords": ", ".join(
                        existing_dataset.keywords.values_list("name", flat=True)
                    ),
                    "authors": authors_json,
                    "status": existing_dataset.status,
                    "is_public": existing_dataset.is_public,
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
                "permission_level": permission_level,
                "is_owner": is_owner,
                "can_edit_metadata": (
                    True
                    if not dataset_uuid
                    else UserSharePermission.user_can_edit_dataset(
                        self.request.user,
                        dataset_uuid,
                        ItemType.DATASET,
                    )
                ),
                "can_add_assets": (
                    True
                    if not dataset_uuid
                    else UserSharePermission.user_can_add_assets(
                        self.request.user,
                        dataset_uuid,
                        ItemType.DATASET,
                    )
                ),
                "can_remove_assets": (
                    True
                    if not dataset_uuid
                    else UserSharePermission.user_can_remove_assets(
                        self.request.user,
                        dataset_uuid,
                        ItemType.DATASET,
                    )
                ),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        """Handle dataset creation/update with selected captures and files."""
        try:
            dataset_uuid_str = request.GET.get("dataset_uuid")
            dataset_form = DatasetInfoForm(request.POST, user=request.user)

            # Validate form and get selected items
            validation_result = self._validate_dataset_form(
                request,
                dataset_form,
                dataset_uuid_str,
            )
            if validation_result:
                return validation_result

            if dataset_uuid_str:
                # Get dataset UUID format
                dataset_uuid = self._parse_dataset_uuid(
                    dataset_uuid_str, raise_on_error=False
                )
                if not dataset_uuid:
                    return self._get_error_response(
                        message="Invalid dataset UUID.", status_code=400
                    )

                # Handle dataset editing
                return self._handle_dataset_edit(request, dataset_form, dataset_uuid)
            # Handle dataset creation
            return self._handle_dataset_creation(request, dataset_form)

        except (DatabaseError, IntegrityError) as e:
            log.exception("Database error in dataset creation")
            return self._get_error_response(message=str(e), status_code=500)
        except ValueError:
            # Handle UUID parsing errors
            return self._get_error_response(
                message="Invalid dataset UUID.", status_code=400
            )

    def _validate_dataset_form(
        self,
        request: HttpRequest,
        dataset_form: DatasetInfoForm,
        dataset_uuid_str: str | None = None,
    ) -> JsonResponse | None:
        """Validate the dataset form and return error response if invalid."""
        # Check if this is an edit operation first

        if dataset_uuid_str:
            dataset_uuid = self._parse_dataset_uuid(
                dataset_uuid_str, raise_on_error=False
            )
            if not dataset_uuid:
                messages.error(request, "Invalid dataset UUID.")
                return redirect("users:dataset_list")

            # For editing, validate permissions first
            permission_level = get_user_permission_level(
                request.user, dataset_uuid, ItemType.DATASET
            )

            if not permission_level:
                return self._get_error_response(
                    message="Access denied.", status_code=403
                )

            # Only validate form if user can edit metadata
            can_edit = UserSharePermission.user_can_edit_dataset(
                request.user, dataset_uuid, ItemType.DATASET
            )

            if can_edit:
                if not dataset_form.is_valid():
                    return self._get_error_response(
                        errors=dataset_form.errors, status_code=400
                    )
            # If user can't edit metadata, skip form validation
        else:
            # For new dataset creation, always validate form
            if not dataset_form.is_valid():
                return self._get_error_response(
                    errors=dataset_form.errors, status_code=400
                )

            # Get selected assets
            selected_captures, selected_files = self._get_asset_selections(request)

            # Validate that at least one capture or file is selected
            if len(selected_captures) == 0 and len(selected_files) == 0:
                return self._get_error_response(
                    message="Please select at least one capture or file.",
                    status_code=400,
                )

        return None

    def _set_authors_el_ids(self, authors: list) -> str:
        """Set the author element IDs for the page lifecycle in edit mode."""
        for author in authors:
            author["_stableId"] = str(uuid.uuid4())
        return json.dumps(authors)

    def _handle_dataset_creation(
        self,
        request: HttpRequest,
        dataset_form: DatasetInfoForm,
    ) -> JsonResponse:
        """Handle dataset creation."""

        # Create dataset
        dataset = self._create_or_update_dataset(request, dataset_form, dataset=None)

        # Get selected assets
        selected_captures, selected_files = self._get_asset_selections(request)

        # Add captures to dataset
        capture_error = self._add_captures_to_dataset(
            dataset, selected_captures, request
        )
        if capture_error:
            return capture_error

        # Add files to dataset
        self._add_files_to_dataset(dataset, selected_files)

        # Return success response with redirect URL
        return JsonResponse(
            {"success": True, "redirect_url": reverse("users:dataset_list")},
        )

    def _handle_dataset_edit(
        self, request, dataset_form: DatasetInfoForm, dataset_uuid: UUID
    ) -> JsonResponse:
        """Handle dataset editing with asset management."""

        # Get dataset
        dataset = self._get_dataset(dataset_uuid, user=request.user, raise_404=True)

        # Update metadata if user has permission
        if UserSharePermission.user_can_edit_dataset(
            request.user, dataset_uuid, ItemType.DATASET
        ):
            self._create_or_update_dataset(request, dataset_form, dataset)

        # Handle asset changes
        asset_changes = self._parse_asset_changes(request)

        # Apply asset changes based on permissions
        self._apply_asset_changes(
            dataset,
            asset_changes,
            request.user,
        )

        return JsonResponse(
            {"success": True, "redirect_url": reverse("users:dataset_list")},
        )

    def _parse_asset_changes(self, request) -> dict:
        """Parse asset changes from the request."""
        changes: dict[str, dict[str, list[str]]] = {
            "captures": {"add": [], "remove": []},
            "files": {"add": [], "remove": []},
        }

        # Parse captures changes
        changes["captures"]["add"] = self._parse_comma_separated_ids(
            request.POST.get("captures_add", "")
        )
        changes["captures"]["remove"] = self._parse_comma_separated_ids(
            request.POST.get("captures_remove", "")
        )

        # Parse files changes
        changes["files"]["add"] = self._parse_comma_separated_ids(
            request.POST.get("files_add", "")
        )
        changes["files"]["remove"] = self._parse_comma_separated_ids(
            request.POST.get("files_remove", "")
        )

        return changes

    def _apply_asset_changes(  # noqa: C901
        self,
        dataset: Dataset,
        changes: dict,
        user: User,
    ):
        """Apply asset changes based on user permissions."""
        # Cache permissions to avoid repeated queries
        permissions = self._get_permission_cache(user, dataset.uuid)

        # Process captures and files using the same pattern
        asset_types = [
            ("captures", Capture, dataset.captures),
            ("files", File, dataset.files),
        ]

        for asset_type_name, _asset_model, asset_relation in asset_types:
            # Add assets
            if permissions["can_add_assets"]:
                for asset_id in changes[asset_type_name]["add"]:
                    if asset_type_name == "captures":
                        asset = self._get_capture(
                            asset_id, user=user, require_owner=True
                        )
                    else:
                        asset = self._get_file(asset_id, user=user, require_owner=True)

                    if asset:
                        asset_relation.add(asset)

            # Remove assets
            if permissions["can_remove_assets"]:
                for asset_id in changes[asset_type_name]["remove"]:
                    if asset_type_name == "captures":
                        asset = self._get_capture(
                            asset_id, user=None, require_owner=False
                        )
                    else:
                        asset = self._get_file(asset_id, user=None, require_owner=False)

                    if asset:
                        # Check if user can remove this asset
                        can_remove = (
                            asset.owner == user
                            or permissions["can_remove_others_assets"]
                        )
                        if can_remove:
                            asset_relation.remove(asset)

    def _apply_author_changes(self, authors: list, changes: dict) -> list:
        """Apply author changes based on the changes tracking."""
        result = []

        # Process each author index
        for i, author in enumerate(authors):
            # Skip if marked for removal
            if i in changes.get("removed", []):
                continue

            # Apply modifications if any
            if i in changes.get("modified", {}):
                modified_author = (
                    author.copy()
                    if isinstance(author, dict)
                    else {"name": author, "orcid_id": ""}
                )
                for field, change_data in changes["modified"][i].items():
                    modified_author[field] = change_data.get(
                        "new", modified_author.get(field, "")
                    )
                result.append(modified_author)
            else:
                result.append(author)

        # Add new authors - only add those that aren't already in the result
        # The 'added' array contains indices of newly added authors in the
        # current authors array
        added_indices = changes.get("added", [])
        for i in added_indices:
            if i < len(authors):
                new_author = authors[i]
                # Check if this author is already in result (shouldn't be,
                # but safety check)
                # Convert to comparable format
                new_author_name = (
                    new_author.get("name", "")
                    if isinstance(new_author, dict)
                    else str(new_author)
                )
                new_author_orcid = (
                    new_author.get("orcid_id", "")
                    if isinstance(new_author, dict)
                    else ""
                )

                # Only add if not already present (by name and orcid)
                is_duplicate = any(
                    (
                        isinstance(a, dict)
                        and a.get("name") == new_author_name
                        and a.get("orcid_id") == new_author_orcid
                    )
                    or (not isinstance(a, dict) and str(a) == new_author_name)
                    for a in result
                )

                if not is_duplicate:
                    result.append(new_author)

        return result

    def _get_asset_selections(
        self,
        request: HttpRequest,
    ) -> tuple[list[str], list[str]]:
        """
        Get selected assets from the request.
        This function is used to get the selected assets on creation only.
        """
        selected_captures = request.POST.get("selected_captures", "").split(",")
        selected_files = request.POST.get("selected_files", "").split(",")
        return selected_captures, selected_files

    def _create_or_update_dataset(
        self,
        request: HttpRequest,
        dataset_form: DatasetInfoForm,
        dataset: Dataset | None = None,
    ) -> Dataset:
        """Create a new dataset or update an existing one."""
        if dataset:
            dataset.name = dataset_form.cleaned_data["name"]
            dataset.description = dataset_form.cleaned_data["description"]

            # Parse authors from JSON string
            authors_json = dataset_form.cleaned_data["authors"]
            authors = json.loads(authors_json)

            # Parse author changes if provided
            author_changes_json = request.POST.get("author_changes", "")
            if author_changes_json:
                try:
                    author_changes = json.loads(author_changes_json)
                    # Apply author changes
                    authors = self._apply_author_changes(authors, author_changes)
                except json.JSONDecodeError:
                    # Fallback to direct authors if parsing fails
                    pass

            dataset.authors = authors
            dataset.status = dataset_form.cleaned_data["status"]
            dataset.is_public = dataset_form.cleaned_data.get("is_public", False)
            dataset.save()

            # Clear existing keyword relationships (not the keywords themselves)
            dataset.keywords.clear()
        else:
            # Create new dataset
            # Parse authors from JSON string
            authors_json = dataset_form.cleaned_data["authors"]
            authors = json.loads(authors_json)
            dataset = Dataset.objects.create(
                name=dataset_form.cleaned_data["name"],
                description=dataset_form.cleaned_data["description"],
                authors=authors,
                status=dataset_form.cleaned_data["status"],
                is_public=dataset_form.cleaned_data.get("is_public", False),
                owner=request.user,
            )

        # Persist keywords from form (comma-separated)
        raw_keywords = dataset_form.cleaned_data.get("keywords", "") or ""
        self._process_keywords(dataset, raw_keywords)

        return dataset

    def _add_captures_to_dataset(
        self, dataset: Dataset, selected_captures: list[str], request
    ) -> JsonResponse | None:
        """Add selected captures to the dataset."""
        if not selected_captures[0]:
            return None

        for capture_id in selected_captures:
            if not capture_id:
                continue
            try:
                # Only allow adding captures owned by the user
                capture = Capture.objects.get(
                    uuid=capture_id, owner=request.user, is_deleted=False
                )
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
            except Capture.DoesNotExist:
                return JsonResponse(
                    {
                        "success": False,
                        "errors": {
                            "non_field_errors": [
                                f"Capture {capture_id} not found or you don't have "
                                "permission to add it to a dataset.",
                            ],
                        },
                    },
                    status=400,
                )

        return None

    def _add_files_to_dataset(
        self, dataset: Dataset, selected_files: list[str]
    ) -> None:
        """Add selected files to the dataset."""
        if selected_files[0]:
            files = File.objects.filter(
                uuid__in=selected_files,
                owner=self.request.user,
            )
            dataset.files.add(*files)

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
        )

        # Prepare file details for JavaScript
        for selected_file in files_queryset:
            rel_path = (
                f"{selected_file.directory.replace(str(base_dir), '')}"
                if base_dir
                else None
            )
            file_dict = self.serialize_item(selected_file, rel_path)
            selected_files.append(file_dict)

            selected_files_details[str(selected_file.uuid)] = file_dict

        return selected_files, selected_files_details

    def _get_capture_context(
        self, existing_dataset: Dataset | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        selected_captures: list[dict[str, Any]] = []
        selected_captures_details: dict[str, Any] = {}
        composite_capture_dirs: set[str] = set()
        if existing_dataset:
            captures_queryset = existing_dataset.captures.filter(
                is_deleted=False,
            )

            # Only include one composite per group
            for capture in captures_queryset.order_by("-created_at"):
                if capture.is_multi_channel:
                    if capture.top_level_dir not in composite_capture_dirs:
                        capture_dict = self.serialize_item(capture)
                        capture_uuid = str(capture_dict["id"])
                        selected_captures.append(capture_dict)
                        selected_captures_details[capture_uuid] = capture_dict
                        composite_capture_dirs.add(capture.top_level_dir)
                else:
                    capture_dict = self.serialize_item(capture)
                    capture_uuid = str(capture_dict["id"])
                    selected_captures.append(capture_dict)
                    selected_captures_details[capture_uuid] = capture_dict

        return selected_captures, selected_captures_details


user_group_captures_view = GroupCapturesView.as_view()


def filter_by_frequency_range(
    datasets: QuerySet[Dataset],
    min_freq: float | None,
    max_freq: float | None,
) -> QuerySet[Dataset]:
    """Filter datasets by frequency range of their captures.

    Reuses the existing _apply_frequency_filters_to_list function
    to filter captures, then maps back to datasets.
    """
    if min_freq is None and max_freq is None:
        return datasets

    # Get dataset UUIDs
    dataset_uuids = list(datasets.values_list("uuid", flat=True))
    if not dataset_uuids:
        return datasets.none()

    # Get all captures for these datasets and convert to list
    captures_qs = Capture.objects.filter(
        Q(Q(dataset__uuid__in=dataset_uuids) | Q(datasets__uuid__in=dataset_uuids)),
        is_deleted=False,
    ).distinct()
    captures_list = list(captures_qs.iterator(chunk_size=1000))
    if not captures_list:
        return datasets.none()

    # Use existing frequency filter function
    filtered_captures = _apply_frequency_filters_to_list(
        captures_list=captures_list,
        min_freq=min_freq,
        max_freq=max_freq,
    )

    if len(filtered_captures) == 0:
        return datasets.none()

    matching_dataset_uuids: set[uuid.UUID] = set()
    for capture in filtered_captures:
        if capture.dataset is not None:
            matching_dataset_uuids.add(capture.dataset.uuid)

        for ds in capture.datasets.all():
            matching_dataset_uuids.add(ds.uuid)

    return datasets.filter(uuid__in=matching_dataset_uuids)


def serialize_datasets_for_user(
    datasets: QuerySet[Dataset], user: User | None
) -> list[dict[str, Any]]:
    """Serialize datasets for display with user context.

    Args:
        datasets: QuerySet of Dataset objects to serialize
        user: User object or None for anonymous users

    Returns:
        List of serialized dataset dictionaries
    """
    serialized_datasets = []
    for dataset in datasets:
        # Create a mock request object for the serializer context
        context_req = {
            "request": type(
                "Request",
                (),
                {"user": user if user and user.is_authenticated else None},
            )()
        }
        dataset_data = cast(
            "ReturnDict", DatasetGetSerializer(dataset, context=context_req).data
        )
        dataset_data["dataset"] = dataset
        serialized_datasets.append(dataset_data)
    return serialized_datasets


def get_published_datasets() -> QuerySet[Dataset]:
    """Get all published datasets (status=FINAL or is_public=True)."""
    return (
        Dataset.objects.filter(
            status=DatasetStatus.FINAL,
            is_public=True,
            is_deleted=False,
        )
        .prefetch_related("keywords", "owner")
        .distinct()
        .order_by("-created_at")
    )


def apply_search_filters(
    datasets: QuerySet[Dataset],
    form_data: dict[str, Any],
) -> QuerySet[Dataset]:
    """Apply search filters to the dataset queryset."""
    query = form_data.get("query", "").strip()
    keywords_str = form_data.get("keywords", "").strip()
    min_freq = form_data.get("min_frequency")
    max_freq = form_data.get("max_frequency")

    # Apply text search
    if query:
        datasets = datasets.filter(
            Q(name__icontains=query)
            | Q(abstract__icontains=query)
            | Q(description__icontains=query)
            | Q(authors__icontains=query)
            | Q(doi__icontains=query)
        )

    # Apply keyword filter
    if keywords_str:
        # Split and slugify keywords
        keyword_slugs = {
            slugify(k.strip())
            for k in keywords_str.split(",")
            if k.strip() and slugify(k.strip())
        }
        if keyword_slugs:
            datasets = datasets.filter(keywords__name__in=keyword_slugs).distinct()

    # Apply frequency range filter
    if min_freq is not None or max_freq is not None:
        datasets = filter_by_frequency_range(datasets, min_freq, max_freq)

    return datasets


class SearchPublishedDatasetsView(View):
    """View for searching published datasets (public, no auth required)."""

    template_name = "users/published_datasets_list.html"

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Handle GET request for dataset search."""
        form = PublishedDatasetSearchForm(request.GET)
        datasets = get_published_datasets()

        # Apply search filters
        if form.is_valid():
            datasets = apply_search_filters(
                datasets,
                form.cleaned_data,
            )

        # Serialize datasets
        serialized_datasets = serialize_datasets_for_user(
            datasets, request.user if request.user.is_authenticated else None
        )

        # Paginate results
        paginator = Paginator(serialized_datasets, per_page=15)
        page_number = request.GET.get("page", 1)
        try:
            page_obj = paginator.get_page(page_number)
        except (PageNotAnInteger, EmptyPage):
            page_obj = paginator.get_page(1)

        return render(
            request,
            template_name=self.template_name,
            context={
                "search_form": form,
                "page_obj": page_obj,
            },
        )


user_search_datasets_view = SearchPublishedDatasetsView.as_view()


class ListDatasetsView(Auth0LoginRequiredMixin, View):
    template_name = "users/dataset_list.html"

    def get(self, request, *args, **kwargs) -> HttpResponse:
        """Handle GET request for dataset list."""

        sort_by, sort_order = self._get_sort_parameters(request)
        order_by = self._build_order_by(sort_by, sort_order)

        owned_datasets = self._get_owned_datasets(request.user, order_by)
        shared_datasets = self._get_shared_datasets(request.user, order_by)

        datasets_with_shared_users: list[dict] = []  # pyright: ignore[reportMissingTypeArgument]
        datasets_with_shared_users.extend(
            serialize_datasets_for_user(owned_datasets, request.user)
        )
        datasets_with_shared_users.extend(
            serialize_datasets_for_user(shared_datasets, request.user)
        )
        page_obj = self._paginate_datasets(datasets_with_shared_users, request)

        # Check if this is an AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            # Return table and modals so the client can update both after list refresh
            table_html = render_to_string(
                "users/components/dataset_list_table.html",
                {
                    "page_obj": page_obj,
                    "sort_by": sort_by,
                    "sort_order": sort_order,
                    "ajax_fragment": True,
                },
                request=request,
            )
            modals_html = render_to_string(
                "users/components/dataset_list_modals.html",
                {"page_obj": page_obj},
                request=request,
            )
            # Separator used by ListRefreshManager to split table vs modals
            list_refresh_sep = "<!-- LIST_REFRESH_SEP -->"
            return HttpResponse(table_html + list_refresh_sep + modals_html)

        return render(
            request,
            template_name=self.template_name,
            context={
                "page_obj": page_obj,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        )

    def _get_sort_parameters(self, request: HttpRequest) -> tuple[str, str]:
        """Get sort parameters from request."""
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        return sort_by, sort_order

    def _build_order_by(self, sort_by: str, sort_order: str) -> str:
        """Build order_by string for queryset."""
        allowed_sort_fields = {"name", "created_at", "updated_at", "authors"}

        if sort_by in allowed_sort_fields:
            order_prefix = "-" if sort_order == "desc" else ""
            return f"{order_prefix}{sort_by}"

        return "-created_at"

    def _get_owned_datasets(self, user: User, order_by: str) -> QuerySet[Dataset]:
        """Get datasets owned by the user."""
        return (
            user.datasets.filter(is_deleted=False)
            .prefetch_related("keywords")
            .order_by(order_by)
        )

    def _get_shared_datasets(self, user: User, order_by: str) -> QuerySet[Dataset]:
        """Get datasets shared with the user."""
        shared_permissions = UserSharePermission.objects.filter(
            shared_with=user,
            item_type=ItemType.DATASET,
            is_deleted=False,
            is_enabled=True,
        ).select_related("owner")

        shared_dataset_uuids = [perm.item_uuid for perm in shared_permissions]
        return (
            Dataset.objects.filter(uuid__in=shared_dataset_uuids, is_deleted=False)
            .exclude(owner=user)
            .prefetch_related("keywords")
            .order_by(order_by)
        )

    def _paginate_datasets(
        self, datasets: list[dict[str, Any]], request: HttpRequest
    ) -> Any:
        """Paginate the datasets list."""
        paginator = Paginator(datasets, per_page=15)
        page_number = request.GET.get("page")
        return paginator.get_page(page_number)


user_dataset_list_view = ListDatasetsView.as_view()


class DatasetDetailsView(FileTreeMixin, View):
    """View to handle dataset details modal requests."""

    def _get_dataset_files(self, dataset: Dataset) -> QuerySet[File]:
        """
        Get all files associated with a dataset,
        including files from linked captures.

        Supports both FK and M2M relationships (expand-contract pattern).

        Args:
            dataset: The dataset to get files for

        Returns:
            A QuerySet of files associated with the dataset
        """
        return get_dataset_files_including_captures(dataset, include_deleted=False)

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """
        Get dataset details and files for the modal.

        Args:
            request: The HTTP request object
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments

        Returns:
            A JSON response containing the dataset details and files
        """
        dataset_uuid_str = request.GET.get("dataset_uuid")

        if not dataset_uuid_str:
            return JsonResponse({"error": "Dataset UUID is required"}, status=400)

        try:
            dataset_uuid = UUID(dataset_uuid_str)
        except ValueError:
            return JsonResponse({"error": "Invalid dataset UUID"}, status=400)

        try:
            dataset = get_object_or_404(Dataset, uuid=dataset_uuid, is_deleted=False)

            has_public_access = (
                dataset.is_public and dataset.status == DatasetStatus.FINAL
            )
            has_user_access = request.user.is_authenticated and user_has_access_to_item(
                request.user, dataset_uuid, ItemType.DATASET
            )

            if not (has_public_access or has_user_access):
                return JsonResponse(
                    {"error": "Dataset not found or access denied"}, status=404
                )

            # Get dataset information
            dataset_data = get_dataset_serializer(
                dataset, has_user_access=has_user_access
            )

            # Get all files associated with the dataset
            files_queryset = self._get_dataset_files(dataset)

            # Calculate statistics
            total_files = files_queryset.count()
            captures_count = files_queryset.filter(capture__isnull=False).count()
            artifacts_count = files_queryset.filter(capture__isnull=True).count()
            total_size = files_queryset.aggregate(total=Sum("size"))["total"] or 0

            base_dir = sanitize_path_rel_to_user(
                unsafe_path="/",
                user=dataset.owner,
            )

            tree_data = self._get_directory_tree(files_queryset, str(base_dir))

            response_data = {
                "dataset": dataset_data,
                "tree": tree_data,
                "statistics": {
                    "total_files": total_files,
                    "captures": captures_count,
                    "artifacts": artifacts_count,
                    "total_size": total_size,
                },
            }

            return JsonResponse(response_data)

        except Dataset.DoesNotExist:
            return JsonResponse({"error": "Dataset not found"}, status=404)
        except Exception:  # noqa: BLE001
            log.exception("Error retrieving dataset details")
            return JsonResponse({"error": "Internal server error"}, status=500)


user_dataset_details_view = DatasetDetailsView.as_view()


class PublishDatasetView(Auth0LoginRequiredMixin, View):
    """View to handle dataset publishing (updating status and is_public)."""

    def post(self, request, dataset_uuid: str) -> JsonResponse:
        """Handle POST request to publish a dataset."""
        # Get the dataset
        dataset = get_object_or_404(Dataset, uuid=dataset_uuid)

        # Check if user has access
        if not user_has_access_to_item(request.user, dataset_uuid, ItemType.DATASET):
            return JsonResponse(
                {"success": False, "error": "Access denied."}, status=403
            )

        can_publish = UserSharePermission.user_can_edit_dataset(
            request.user, dataset_uuid, ItemType.DATASET
        )

        if not can_publish:
            return JsonResponse(
                {
                    "success": False,
                    "error": "You do not have permission to publish this dataset.",
                },
                status=403,
            )

        # Get status and is_public from request
        status_value = request.POST.get("status")

        is_public_raw = request.POST.get("is_public")
        if is_public_raw is None:
            is_public_value = None
        else:
            try:
                is_public_value = json.loads(is_public_raw)
            except (json.JSONDecodeError, TypeError):
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Could not determine dataset visibility.",
                    },
                    status=400,
                )

        error_messages = self._handle_400_errors(
            dataset,
            status_value,
            is_public_value=is_public_value,
        )
        if len(error_messages) > 0:
            return JsonResponse(
                {"success": False, "errors": {"non_field_errors": error_messages}},
                status=400,
            )

        # Update status if provided and dataset is not already final
        if status_value:
            dataset.status = status_value

        # Update is_public if provided and dataset is not already public
        if is_public_value is not None:
            dataset.is_public = is_public_value

        dataset.save()

        return JsonResponse(
            {
                "success": True,
                "message": "Dataset updated successfully.",
                "status": dataset.status,
                "is_public": dataset.is_public,
            }
        )

    def _handle_400_errors(
        self,
        dataset: Dataset,
        status_value: str | None,
        *,
        is_public_value: bool | None,
    ) -> list[str]:
        """Handle status change."""

        # Initialize error message
        error_messages = []

        # Validate that at least one field is being updated
        if not status_value and is_public_value is None:
            error_messages.append("No fields to update.")
        # Validate status value
        if status_value and status_value not in [
            DatasetStatus.DRAFT,
            DatasetStatus.FINAL,
        ]:
            error_messages.append("Invalid status value.")

        # Update status if provided and dataset is not already final
        if status_value:
            if (
                dataset.status == DatasetStatus.FINAL
                and status_value == DatasetStatus.DRAFT
            ):
                error_messages.append(
                    "Cannot change published dataset status back to Draft."
                )

        # Cannot make DRAFT dataset public - must be FINAL first
        if is_public_value is True:
            # Check if dataset will be DRAFT after this update
            new_status = status_value or dataset.status
            if new_status == DatasetStatus.DRAFT:
                error_messages.append(
                    "Draft datasets cannot be made public. Status must be Final."
                )

        if dataset.is_public and is_public_value is False:
            error_messages.append(
                "Cannot change public dataset visibility back to Private."
            )

        return error_messages


user_publish_dataset_view = PublishDatasetView.as_view()


class DatasetVersioningView(Auth0LoginRequiredMixin, View):
    """View to handle dataset versioning updates."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        dataset_uuid = request.POST.get("dataset_uuid")
        copy_shared_users = request.POST.get("copy_shared_users", "false").lower() in (
            "true",
            "1",
            "on",
        )
        if not dataset_uuid:
            return JsonResponse({"error": "Dataset UUID is required"}, status=400)

        dataset = get_object_or_404(Dataset, uuid=dataset_uuid, is_deleted=False)

        # check if user has access to the dataset
        if not UserSharePermission.user_can_advance_version(
            request.user, dataset_uuid, ItemType.DATASET
        ):
            return JsonResponse(
                {
                    "error": (
                        "You do not have permission to advance "
                        "the version of this dataset"
                    )
                },
                status=403,
            )

        # copy dataset with relations
        new_dataset = self._copy_dataset_with_relations(
            dataset,
            request_user=request.user,
            copy_shared_users=copy_shared_users,
        )

        return JsonResponse({"success": True, "version": new_dataset.version})

    def _copy_dataset_with_relations(
        self,
        original_dataset: Dataset,
        *,
        request_user: User,
        copy_shared_users: bool = False,
    ) -> Dataset:
        """
        Copy a dataset along with all its related files and captures.

        Args:
            original_dataset: The dataset to copy
            request_user: The user creating the new version
            copy_shared_users: Whether to copy the shared users from
            the original dataset to the new dataset
        Returns:
            The new dataset with copied related objects
        """
        new_version = original_dataset.version + 1

        # Use database transaction with locking to prevent race conditions
        # when multiple requests try to create the same version simultaneously
        with transaction.atomic():
            # Lock the original dataset to prevent concurrent version creation
            locked_dataset = Dataset.objects.select_for_update().get(
                uuid=original_dataset.uuid
            )

            # Check again for existing version within the locked transaction
            existing_version = Dataset.objects.filter(
                previous_version=locked_dataset,
                version=new_version,
                owner=request_user,
                is_deleted=False,
            ).first()

            if existing_version:
                # Return existing version if it was already created
                return existing_version

            # Fields that should not be copied from the original dataset
            # These fields will be reset for the new version
            no_copy_fields = [
                "uuid",
                "created_at",
                "updated_at",
                "status",
                "is_public",
                "shared_with",
                "previous_version",
                "version",
                "owner",
            ]

            dataset_data = {
                field.name: getattr(locked_dataset, field.name)
                for field in locked_dataset._meta.get_fields()  # noqa: SLF001
                if hasattr(field, "name")
                and field.name not in no_copy_fields
                and not field.many_to_many
                and not field.one_to_many
                and not field.one_to_one
            }
            dataset_data["owner"] = request_user
            dataset_data["version"] = new_version
            dataset_data["previous_version"] = locked_dataset

            # Ensure status is draft for new version
            dataset_data["status"] = DatasetStatus.DRAFT.value
            dataset_data["is_public"] = False

            new_dataset = Dataset.objects.create(**dataset_data)

            # Set the relationships on the new dataset
            new_dataset.captures.set(locked_dataset.captures.all())
            new_dataset.files.set(locked_dataset.files.all())
            new_dataset.keywords.set(locked_dataset.keywords.all())
            if copy_shared_users:
                self._copy_shared_users(locked_dataset, new_dataset)

        return new_dataset

    def _copy_shared_users(
        self, original_dataset: Dataset, new_dataset: Dataset
    ) -> None:
        """
        Copy the shared users from the original dataset to the new dataset.
        Args:
            original_dataset: The original dataset
            new_dataset: The new dataset
        """
        shared_users = get_shared_users_for_item(
            original_dataset.uuid, ItemType.DATASET
        )
        for shared_user in shared_users:
            UserSharePermission.objects.create(
                owner=new_dataset.owner,
                shared_with=shared_user.shared_with,
                item_type=ItemType.DATASET,
                item_uuid=new_dataset.uuid,
                is_enabled=True,
                is_deleted=False,
                permission_level=shared_user.permission_level,
            )


user_dataset_versioning_view = DatasetVersioningView.as_view()
