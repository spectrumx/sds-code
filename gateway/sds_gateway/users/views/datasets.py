import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import cast
from uuid import UUID

from django.contrib import messages
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError
from django.db.models import Q
from django.db.models import Sum
from django.db.models.query import QuerySet
from django.db.utils import IntegrityError
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from loguru import logger as log

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import Keyword
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.models import get_user_permission_level
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user
from sds_gateway.users.forms import CaptureSearchForm
from sds_gateway.users.forms import DatasetInfoForm
from sds_gateway.users.forms import FileSearchForm
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.mixins import FileTreeMixin
from sds_gateway.users.mixins import FormSearchMixin
from sds_gateway.users.models import User
from sds_gateway.users.utils import deduplicate_composite_captures

if TYPE_CHECKING:
    from rest_framework.utils.serializer_helpers import ReturnDict


class GroupCapturesView(
    Auth0LoginRequiredMixin, FormSearchMixin, FileTreeMixin, TemplateView
):
    template_name = "users/group_captures.html"

    def get(self, request, *args, **kwargs):  # noqa: C901, PLR0911
        """Handle GET request with permission checking and AJAX requests."""
        # Check if editing existing dataset
        dataset_uuid_str = request.GET.get("dataset_uuid")

        if dataset_uuid_str:
            try:
                dataset_uuid = UUID(dataset_uuid_str)
            except ValueError:
                messages.error(request, "Invalid dataset UUID.")
                return redirect("users:dataset_list")
            # Check if user has access to edit this dataset
            if not user_has_access_to_item(
                request.user, dataset_uuid, ItemType.DATASET
            ):
                messages.error(request, "Dataset not found or access denied.")
                return redirect("users:dataset_list")

            # Check if user can edit dataset metadata
            if not UserSharePermission.user_can_edit_dataset(
                request.user, dataset_uuid, ItemType.DATASET
            ) and not UserSharePermission.user_can_add_assets(
                request.user, dataset_uuid, ItemType.DATASET
            ):
                messages.error(
                    request, "You don't have permission to edit this dataset."
                )
                return redirect("users:dataset_list")

        # Handle AJAX requests
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
                        tree_data = self._get_directory_tree(files, str(base_dir))

                        return JsonResponse(
                            {
                                "tree": tree_data,
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
            try:
                dataset_uuid = UUID(dataset_uuid_str)
            except ValueError as err:
                msg = "Invalid dataset UUID."
                raise Http404(msg) from err
            # Check if user has access to this dataset
            if not user_has_access_to_item(
                self.request.user, dataset_uuid, ItemType.DATASET
            ):
                msg = "Dataset not found or access denied."
                raise Http404(msg)

            # Get the dataset - it exists and user has access
            existing_dataset = Dataset.objects.get(uuid=dataset_uuid)
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
            # Validate form and get selected items
            validation_result = self._validate_dataset_form(request)
            if validation_result:
                return validation_result

            dataset_uuid_str = request.GET.get("dataset_uuid")
            if dataset_uuid_str:
                try:
                    dataset_uuid = UUID(dataset_uuid_str)
                except ValueError:
                    messages.error(request, "Invalid dataset UUID.")
                    return redirect("users:dataset_list")
                # Handle dataset editing
                return self._handle_dataset_edit(request, dataset_uuid)
            # Handle dataset creation
            return self._handle_dataset_creation(request)

        except (DatabaseError, IntegrityError) as e:
            log.exception("Database error in dataset creation")
            return JsonResponse(
                {"success": False, "errors": {"non_field_errors": [str(e)]}},
                status=500,
            )

    def _validate_dataset_form(self, request) -> JsonResponse | None:
        """Validate the dataset form and return error response if invalid."""
        # Check if this is an edit operation first
        dataset_uuid_str = request.GET.get("dataset_uuid")

        if dataset_uuid_str:
            try:
                dataset_uuid = UUID(dataset_uuid_str)
            except ValueError:
                messages.error(request, "Invalid dataset UUID.")
                return JsonResponse(
                    {
                        "success": False,
                        "errors": {"non_field_errors": ["Invalid dataset UUID."]},
                    },
                    status=400,
                )

            # For editing, validate permissions first
            permission_level = get_user_permission_level(
                request.user, dataset_uuid, ItemType.DATASET
            )

            if not permission_level:
                return JsonResponse(
                    {
                        "success": False,
                        "errors": {"non_field_errors": ["Access denied."]},
                    },
                    status=403,
                )

            # Only validate form if user can edit metadata
            can_edit = UserSharePermission.user_can_edit_dataset(
                request.user, dataset_uuid, ItemType.DATASET
            )

            if can_edit:
                dataset_form = DatasetInfoForm(request.POST, user=request.user)
                if not dataset_form.is_valid():
                    return JsonResponse(
                        {"success": False, "errors": dataset_form.errors},
                        status=400,
                    )
            # If user can't edit metadata, skip form validation
        else:
            # For new dataset creation, always validate form
            dataset_form = DatasetInfoForm(request.POST, user=request.user)
            if not dataset_form.is_valid():
                return JsonResponse(
                    {"success": False, "errors": dataset_form.errors},
                    status=400,
                )

            # For creation, get selected captures and files from hidden fields
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

        return None

    def _set_authors_el_ids(self, authors: list) -> str:
        """Set the author element IDs for the page lifecycle in edit mode."""
        for author in authors:
            author["_stableId"] = str(uuid.uuid4())
        return json.dumps(authors)

    def _handle_dataset_creation(self, request) -> JsonResponse:
        """Handle dataset creation."""
        dataset_form, selected_captures, selected_files = self._get_form_and_selections(
            request
        )

        # Create dataset
        dataset = self._create_or_update_dataset(request, dataset_form)

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

    def _handle_dataset_edit(self, request, dataset_uuid: UUID) -> JsonResponse:
        """Handle dataset editing with asset management."""

        # Get the dataset
        dataset = get_object_or_404(Dataset, uuid=dataset_uuid)

        # Check permissions
        permission_level = get_user_permission_level(
            request.user, dataset_uuid, ItemType.DATASET
        )

        if not permission_level:
            return JsonResponse(
                {
                    "success": False,
                    "errors": {"non_field_errors": ["Access denied."]},
                },
                status=403,
            )

        # Update metadata if user has permission
        if UserSharePermission.user_can_edit_dataset(
            request.user, dataset_uuid, ItemType.DATASET
        ):
            dataset_form = DatasetInfoForm(request.POST, user=request.user)
            if dataset_form.is_valid():
                dataset.name = dataset_form.cleaned_data["name"]
                dataset.description = dataset_form.cleaned_data["description"]

                # Handle authors with changes tracking
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
                dataset.save()

                # Handle keywords update
                # Clear existing keyword relationships
                dataset.keywords.clear()
                # Persist keywords from form (comma-separated)
                raw_keywords = dataset_form.cleaned_data.get("keywords", "") or ""
                if raw_keywords:
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

        # Handle asset changes
        asset_changes = self._parse_asset_changes(request)

        # Apply asset changes based on permissions
        self._apply_asset_changes(
            dataset, asset_changes, request.user, permission_level
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
        captures_add = request.POST.get("captures_add", "")
        captures_remove = request.POST.get("captures_remove", "")

        if captures_add:
            changes["captures"]["add"] = [
                capture_id.strip()
                for capture_id in captures_add.split(",")
                if capture_id.strip()
            ]
        if captures_remove:
            changes["captures"]["remove"] = [
                capture_id.strip()
                for capture_id in captures_remove.split(",")
                if capture_id.strip()
            ]

        # Parse files changes
        files_add = request.POST.get("files_add", "")
        files_remove = request.POST.get("files_remove", "")

        if files_add:
            changes["files"]["add"] = [
                file_id.strip() for file_id in files_add.split(",") if file_id.strip()
            ]
        if files_remove:
            changes["files"]["remove"] = [
                file_id.strip()
                for file_id in files_remove.split(",")
                if file_id.strip()
            ]

        return changes

    def _apply_asset_changes(  # noqa: C901, PLR0912
        self, dataset: Dataset, changes: dict, user: User, permission_level: str
    ):
        """Apply asset changes based on user permissions."""
        # Handle captures
        if UserSharePermission.user_can_add_assets(
            user, dataset.uuid, ItemType.DATASET
        ):
            # Add captures
            for capture_id in changes["captures"]["add"]:
                try:
                    capture = Capture.objects.get(
                        uuid=capture_id, owner=user, is_deleted=False
                    )
                    dataset.captures.add(capture)
                except Capture.DoesNotExist:
                    continue

        if UserSharePermission.user_can_remove_assets(
            user, dataset.uuid, ItemType.DATASET
        ):
            # Remove captures
            for capture_id in changes["captures"]["remove"]:
                try:
                    capture = Capture.objects.get(uuid=capture_id, is_deleted=False)
                    # Check if user can remove this capture
                    if (
                        capture.owner == user
                        or UserSharePermission.user_can_remove_others_assets(
                            user, dataset.uuid, ItemType.DATASET
                        )
                    ):
                        dataset.captures.remove(capture)
                except Capture.DoesNotExist:
                    continue

        # Handle files
        if UserSharePermission.user_can_add_assets(
            user, dataset.uuid, ItemType.DATASET
        ):
            # Add files
            for file_id in changes["files"]["add"]:
                try:
                    file_obj = File.objects.get(
                        uuid=file_id, owner=user, is_deleted=False
                    )
                    dataset.files.add(file_obj)
                except File.DoesNotExist:
                    continue

        if UserSharePermission.user_can_remove_assets(
            user, dataset.uuid, ItemType.DATASET
        ):
            # Remove files
            for file_id in changes["files"]["remove"]:
                try:
                    file_obj = File.objects.get(uuid=file_id, is_deleted=False)
                    # Check if user can remove this file
                    if (
                        file_obj.owner == user
                        or UserSharePermission.user_can_remove_others_assets(
                            user, dataset.uuid, ItemType.DATASET
                        )
                    ):
                        dataset.files.remove(file_obj)
                except File.DoesNotExist:
                    continue

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
                result.append(changes["modified"][i]["new"])
            else:
                result.append(author)

        # Add new authors
        result.extend(authors[i] for i in changes.get("added", []))

        return result

    def _get_form_and_selections(
        self, request
    ) -> tuple[DatasetInfoForm, list[str], list[str]]:
        """Get the form and selected items from the request."""
        dataset_form = DatasetInfoForm(request.POST, user=request.user)
        dataset_form.is_valid()  # We already validated above

        selected_captures = request.POST.get("selected_captures", "").split(",")
        selected_files = request.POST.get("selected_files", "").split(",")

        return dataset_form, selected_captures, selected_files

    def _create_or_update_dataset(self, request, dataset_form) -> Dataset:
        """Create a new dataset or update an existing one."""
        dataset_uuid = request.GET.get("dataset_uuid", None)

        if dataset_uuid:
            dataset = get_object_or_404(Dataset, uuid=dataset_uuid, owner=request.user)
            dataset.name = dataset_form.cleaned_data["name"]
            dataset.description = dataset_form.cleaned_data["description"]
            # Parse authors from JSON string
            authors_json = dataset_form.cleaned_data["authors"]
            authors = json.loads(authors_json)
            dataset.authors = authors
            dataset.status = dataset_form.cleaned_data["status"]
            dataset.save()

            # Clear existing relationships
            dataset.captures.clear()
            dataset.files.clear()
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
                owner=request.user,
            )

        # Persist keywords from form (comma-separated)
        raw_keywords = dataset_form.cleaned_data.get("keywords", "") or ""
        if raw_keywords:
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
            self._serialize_datasets(owned_datasets, request.user)
        )
        datasets_with_shared_users.extend(
            self._serialize_datasets(shared_datasets, request.user)
        )

        page_obj = self._paginate_datasets(datasets_with_shared_users, request)

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

        return "-created_at"  # Default sorting

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

    def _serialize_datasets(
        self, datasets: QuerySet[Dataset], user: User
    ) -> list[dict[str, Any]]:
        """Prepare serialized datasets."""
        result = []
        for dataset in datasets:
            # Use serializer with request context for proper field calculation
            context = {"request": type("Request", (), {"user": user})()}
            dataset_data = cast(
                "ReturnDict", DatasetGetSerializer(dataset, context=context).data
            )

            # Add the original model for template access
            dataset_data["dataset"] = dataset
            result.append(dataset_data)
        return result

    def _paginate_datasets(
        self, datasets: list[dict[str, Any]], request: HttpRequest
    ) -> Any:
        """Paginate the datasets list."""
        paginator = Paginator(datasets, per_page=15)
        page_number = request.GET.get("page")
        return paginator.get_page(page_number)


user_dataset_list_view = ListDatasetsView.as_view()


class DatasetDetailsView(Auth0LoginRequiredMixin, FileTreeMixin, View):
    """View to handle dataset details modal requests."""

    def _get_dataset_files(self, dataset: Dataset) -> QuerySet[File]:
        """
        Get all files associated with a dataset,
        including files from linked captures.

        Args:
            dataset: The dataset to get files for

        Returns:
            A QuerySet of files associated with the dataset
        """
        # Get files directly associated with the dataset
        dataset_files = dataset.files.filter(is_deleted=False)

        # Get files from linked captures
        capture_file_ids = []
        dataset_captures = dataset.captures.filter(is_deleted=False)
        for capture in dataset_captures:
            capture_file_ids.extend(
                capture.files.filter(is_deleted=False).values_list("uuid", flat=True)
            )

        return File.objects.filter(
            Q(uuid__in=dataset_files.values_list("uuid", flat=True))
            | Q(uuid__in=capture_file_ids)
        )

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

        # Check if user has access to the dataset
        if not user_has_access_to_item(request.user, dataset_uuid, ItemType.DATASET):
            return JsonResponse(
                {"error": "Dataset not found or access denied"}, status=404
            )

        try:
            dataset = get_object_or_404(Dataset, uuid=dataset_uuid, is_deleted=False)

            # Get dataset information
            dataset_data = DatasetGetSerializer(dataset).data

            # Get all files associated with the dataset
            files_queryset = self._get_dataset_files(dataset)

            # Calculate statistics
            total_files = files_queryset.count()
            captures_count = files_queryset.filter(capture__isnull=False).count()
            artifacts_count = files_queryset.filter(capture__isnull=True).count()
            total_size = files_queryset.aggregate(total=Sum("size"))["total"] or 0

            # Use the same base directory logic as GroupCapturesView
            base_dir = sanitize_path_rel_to_user(
                unsafe_path="/",
                request=request,
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
