import datetime
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import cast
from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import EmptyPage
from django.core.paginator import Page
from django.core.paginator import PageNotAnInteger
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
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import TemplateView
from django.views.generic import UpdateView
from loguru import logger as log
from minio.error import MinioException
from rest_framework import status

from sds_gateway.api_methods.helpers.download_file import FileDownloadError
from sds_gateway.api_methods.helpers.download_file import download_file
from sds_gateway.api_methods.helpers.file_helpers import (
    check_file_contents_exist_helper,
)
from sds_gateway.api_methods.helpers.file_helpers import create_capture_helper_simple
from sds_gateway.api_methods.helpers.file_helpers import upload_file_helper_simple
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import KeySources
from sds_gateway.api_methods.models import Keyword
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import ShareGroup
from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.models import get_user_permission_level
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.tasks import is_user_locked
from sds_gateway.api_methods.tasks import notify_shared_users
from sds_gateway.api_methods.tasks import send_item_files_email
from sds_gateway.api_methods.utils.asset_access_control import user_has_access_to_file
from sds_gateway.api_methods.utils.relationship_utils import (
    get_dataset_files_including_captures,
)
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user
from sds_gateway.users.file_utils import get_file_content_response
from sds_gateway.users.file_utils import validate_file_preview_request
from sds_gateway.users.files_utils import add_capture_files
from sds_gateway.users.files_utils import add_root_items
from sds_gateway.users.files_utils import add_shared_items
from sds_gateway.users.files_utils import add_user_files
from sds_gateway.users.files_utils import build_breadcrumbs
from sds_gateway.users.files_utils import items_to_dicts
from sds_gateway.users.forms import CaptureSearchForm
from sds_gateway.users.forms import DatasetInfoForm
from sds_gateway.users.forms import FileSearchForm
from sds_gateway.users.forms import UserUpdateForm
from sds_gateway.users.h5_service import H5PreviewService
from sds_gateway.users.item_models import Item
from sds_gateway.users.mixins import ApprovedUserRequiredMixin
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.mixins import FileTreeMixin
from sds_gateway.users.mixins import FormSearchMixin
from sds_gateway.users.mixins import UserSearchMixin
from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey
from sds_gateway.users.navigation_models import NavigationContext
from sds_gateway.users.navigation_models import NavigationType
from sds_gateway.users.utils import deduplicate_composite_captures
from sds_gateway.users.utils import render_html_fragment
from sds_gateway.users.utils import update_or_create_user_group_share_permissions
from sds_gateway.visualizations.config import get_visualization_compatibility

if TYPE_CHECKING:
    from rest_framework.utils.serializer_helpers import ReturnDict

# Constants
MAX_API_KEY_COUNT = 10


class ShareOperationError(Exception):
    """Custom exception for share operation errors with HTTP status codes."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def get_active_api_key_count(api_keys) -> int:
    """
    Calculate the number of active (non-revoked and non-expired) API keys.

    Args:
        api_keys: QuerySet of UserAPIKey objects

    Returns:
        int: Number of active API keys
    """
    now = datetime.datetime.now(datetime.UTC)
    return sum(
        1
        for key in api_keys
        if not key.revoked and (not key.expiry_date or key.expiry_date >= now)
    )


def validate_uuid(uuid_string: str) -> bool:
    """Validate if a string is a valid UUID."""
    try:
        uuid.UUID(uuid_string)
    except (ValueError, TypeError):
        return False
    else:
        return True


class UserDetailView(Auth0LoginRequiredMixin, DetailView):  # pyright: ignore[reportMissingTypeArgument]
    model = User
    slug_field = "id"
    slug_url_arg = "id"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(Auth0LoginRequiredMixin, SuccessMessageMixin, UpdateView):  # pyright: ignore[reportMissingTypeArgument]
    model = User
    form_class = UserUpdateForm
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
        return reverse("users:view_api_key")


user_redirect_view = UserRedirectView.as_view()


class GenerateAPIKeyView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    template_name = "users/user_api_key.html"

    def get(self, request, *args, **kwargs):
        # Get all API keys for the user (except SVIBackend)
        api_keys = (
            UserAPIKey.objects.filter(user=request.user)
            .exclude(source=KeySources.SVIBackend)
            .order_by("revoked", "-created")
        )  # Active keys first, then by creation date (recent first)
        now = datetime.datetime.now(datetime.UTC)
        active_api_key_count = get_active_api_key_count(api_keys)
        context = {
            "api_key": False,
            "expires_at": None,
            "expired": False,
            "current_api_keys": api_keys,
            "now": now,
            "active_api_key_count": active_api_key_count,
        }
        if not api_keys.exists():
            return render(
                request,
                template_name=self.template_name,
                context=context,
            )

        context.update(
            {
                "api_key": True,  # return True if API key exists
                "current_api_keys": api_keys,
                "now": now,
                "active_api_key_count": active_api_key_count,
            }
        )
        return render(
            request,
            template_name=self.template_name,
            context=context,
        )

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """
        Creates a new API key for the authenticated user without deleting existing keys.
        Enforces the maximum API key count (MAX_API_KEY_COUNT) per user.
        """
        # Check if user has reached the maximum number of active API keys
        api_keys = UserAPIKey.objects.filter(user=request.user).exclude(
            source=KeySources.SVIBackend
        )
        active_api_key_count = get_active_api_key_count(api_keys)
        if active_api_key_count >= MAX_API_KEY_COUNT:
            messages.error(
                request,
                f"You have reached the maximum number of API keys "
                f"({MAX_API_KEY_COUNT}). Please revoke an existing key "
                "before creating a new one.",
            )
            return redirect("users:view_api_key")

        # Get the name and description from the form
        api_key_name = request.POST.get("api_key_name", "")
        api_key_description = request.POST.get("api_key_description", "")
        api_key_expiry_date_str = request.POST.get("api_key_expiry_date", "")

        expiry_date = None
        if api_key_expiry_date_str:
            try:
                expiry_date = datetime.datetime.strptime(
                    api_key_expiry_date_str, "%Y-%m-%d"
                ).replace(tzinfo=datetime.UTC)
            except ValueError:
                messages.error(request, "Invalid expiration date format.")
                return redirect("users:view_api_key")

        # create an API key for the user
        _, raw_key = UserAPIKey.objects.create_key(
            name=api_key_name,
            description=api_key_description,
            user=request.user,
            source=KeySources.SDSWebUI,
            expiry_date=expiry_date,
        )
        request.session["new_api_key"] = raw_key
        return redirect("users:new_api_key")


user_api_key_view = GenerateAPIKeyView.as_view()


class NewAPIKeyView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    template_name = "users/new_api_key.html"

    def get(self, request, *args, **kwargs):
        api_key = request.session.pop("new_api_key", None)
        return render(request, self.template_name, {"api_key": api_key})


new_api_key_view = NewAPIKeyView.as_view()


class RevokeAPIKeyView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        key_id = request.POST.get("key_id")
        api_key = get_object_or_404(UserAPIKey, id=key_id, user=request.user)
        if not api_key.revoked:
            api_key.revoked = True
            api_key.save()
            messages.success(request, "API key revoked successfully.")
        else:
            messages.info(request, "API key is already revoked.")
        return redirect("users:view_api_key")


revoke_api_key_view = RevokeAPIKeyView.as_view()


class GenerateAPIKeyFormView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    template_name = "users/generate_api_key_form.html"

    def get(self, request, *args, **kwargs):
        api_keys = UserAPIKey.objects.filter(user=request.user).exclude(
            source=KeySources.SVIBackend
        )
        active_api_key_count = get_active_api_key_count(api_keys)
        is_allowed_to_generate_key = active_api_key_count < MAX_API_KEY_COUNT
        context = {
            "is_allowed_to_generate_key": is_allowed_to_generate_key,
        }
        return render(request, self.template_name, context)


generate_api_key_form_view = GenerateAPIKeyFormView.as_view()


class ShareItemView(Auth0LoginRequiredMixin, UserSearchMixin, View):
    """
    View to handle item sharing functionality using
    the generalized UserSharePermission model.

    This view is used to search for users to share with,
    add users to item sharing, and remove users from item sharing.

    It also handles the notification of shared users.
    """

    # Map item types to their corresponding models
    ITEM_MODELS = {
        ItemType.DATASET: Dataset,
        ItemType.CAPTURE: Capture,
    }

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Handle user search requests."""
        try:
            item_uuid_unknown = kwargs.get("item_uuid")
            item_type_unknown = kwargs.get("item_type")

            item_uuid = (
                UUID(item_uuid_unknown)
                if not isinstance(item_uuid_unknown, UUID)
                else item_uuid_unknown
            )
            item_type = (
                ItemType(item_type_unknown)
                if not isinstance(item_type_unknown, ItemType)
                else item_type_unknown
            )
        except (ValueError, TypeError):
            return JsonResponse(
                {"error": "Invalid item UUID or item type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        val_errors = ""
        if not item_uuid:
            val_errors += "Invalid item UUID\n"
        if not item_type or not isinstance(item_type, ItemType):
            val_errors += "Invalid item type format\n"
        if item_type not in self.ITEM_MODELS:
            val_errors += "Invalid item type\n"

        if val_errors:
            return JsonResponse(
                {"error": val_errors}, status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user has access to the item (either as owner or shared user)
        if not user_has_access_to_item(
            request.user, item_uuid=item_uuid, item_type=item_type
        ):
            return JsonResponse(
                {"error": f"{item_type.capitalize()} not found or access denied"},
                status=404,
            )

        # Get the item to check existing shared users
        try:
            model_class = self.ITEM_MODELS[item_type]
            # Get the item (we know it exists and user has access)

            # Get exclusion lists for search
            excluded_user_ids, excluded_group_ids = self._get_exclusion_lists(
                request.user, item_uuid=item_uuid, item_type=item_type
            )

        except model_class.DoesNotExist:
            return JsonResponse(
                {"error": f"{item_type.capitalize()} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Use the enhanced mixin method with exclusions and include groups
        return self.search_users(
            request,
            exclude_user_ids=excluded_user_ids,
            exclude_group_ids=excluded_group_ids,
            include_groups=True,
        )

    def _get_exclusion_lists(
        self, user: User, item_uuid: UUID, item_type: ItemType
    ) -> tuple[list[int], list[str]]:
        """Get lists of user IDs and group UUIDs to exclude from search results."""
        # Get individual users already shared with this item
        shared_user_ids = list(
            UserSharePermission.objects.filter(
                item_uuid=item_uuid,
                item_type=item_type,
                is_deleted=False,
                is_enabled=True,
            )
            .exclude(share_groups__isnull=False)
            .values_list("shared_with__id", flat=True)
        )

        # Get groups already shared with this item
        shared_group_ids = list(
            UserSharePermission.objects.filter(
                item_uuid=item_uuid,
                item_type=item_type,
                is_deleted=False,
                is_enabled=True,
            )
            .filter(share_groups__isnull=False)
            .values_list("share_groups__uuid", flat=True)
            .distinct()
        )

        # Get users who are members of already shared groups
        # (to exclude them from individual search)
        shared_group_member_ids = self._get_group_member_ids(shared_group_ids)

        # Combine individual shared users and group members
        # to exclude from individual search
        all_excluded_user_ids = shared_user_ids + shared_group_member_ids

        return all_excluded_user_ids, shared_group_ids

    def _get_group_member_ids(self, group_uuids: list[str]) -> list[int]:
        """Get user IDs of members in the given groups."""
        if not group_uuids:
            return []

        shared_groups = ShareGroup.objects.filter(uuid__in=group_uuids)
        member_ids = []
        for group in shared_groups:
            member_ids.extend(group.members.values_list("id", flat=True))
        return list(set(member_ids))  # Remove duplicates

    def _add_group_to_item(
        self,
        group_identifier: str,
        item_uuid: UUID,
        item_type: ItemType,
        request_user: User,
        message: str,
        permission_level: PermissionLevel = PermissionLevel.VIEWER,
    ) -> tuple[list[str], list[str]]:
        """Add a group to item sharing."""
        group_uuid = group_identifier.split(":")[1]  # Remove "group:" prefix
        shared_users: list[str] = []
        errors: list[str] = []

        try:
            group = ShareGroup.objects.get(
                uuid=group_uuid, owner=request_user, is_deleted=False
            )

            # Validate group has members
            group_members = group.members.all()
            if not group_members.exists():
                errors.append(f"Group '{group.name}' has no members")
                return shared_users, errors

            # Create individual permissions for each group member
            # Users who are already shared individually
            # will have their permissions updated
            for member in group_members:
                update_or_create_user_group_share_permissions(
                    request_user=request_user,
                    group=group,
                    share_user=member,
                    item_uuid=item_uuid,
                    item_type=item_type,
                    message=message,
                    permission_level=permission_level,
                )
                shared_users.append(member.email)

        except ShareGroup.DoesNotExist:
            errors.append("Group not found or you don't own it")

        return shared_users, errors

    def _add_individual_user_to_item(
        self,
        email: str,
        item_uuid: UUID,
        item_type: ItemType,
        request_user: User,
        message: str,
        permission_level: PermissionLevel = PermissionLevel.VIEWER,
    ) -> tuple[str | None, str | None]:
        """Add an individual user to item sharing. Returns (shared_user, error)."""
        try:
            user_to_share_with = User.objects.get(email=email, is_approved=True)

            if user_to_share_with.id == request_user.id:
                return (
                    None,
                    f"You cannot share a {item_type.lower()} with yourself ({email})",
                )

            # Check if already shared
            existing_permission = self._get_existing_user_permission(
                user_to_share_with, item_uuid, item_type, request_user
            )

            if existing_permission:
                if existing_permission.is_enabled:
                    return (
                        None,
                        f"{item_type.capitalize()} is already shared with {email}",
                    )
                # Re-enable the existing disabled permission and update permission level
                existing_permission.is_enabled = True
                existing_permission.message = message
                existing_permission.permission_level = permission_level
                existing_permission.save()
                return email, None

            # Create the share permission
            UserSharePermission.objects.create(
                owner=request_user,
                shared_with=user_to_share_with,
                item_type=item_type,
                item_uuid=item_uuid,
                message=message,
                permission_level=permission_level,
                is_enabled=True,
            )
        except User.DoesNotExist:
            return None, f"User with email {email} not found or not approved"
        else:
            return email, None

    def _get_existing_user_permission(
        self,
        user: User,
        item_uuid: UUID,
        item_type: ItemType,
        request_user: User,
    ) -> UserSharePermission | None:
        """Get existing share permission for a user and item."""
        return UserSharePermission.objects.filter(
            item_uuid=item_uuid,
            item_type=item_type,
            shared_with=user,
            is_deleted=False,
        ).first()

    def _validate_share_request(
        self, request: HttpRequest, item_uuid: UUID, item_type: ItemType
    ) -> JsonResponse | None:
        """
        Validate the share request.
        Returns error response if invalid, None if valid.
        """
        # Validate item type
        if item_type not in self.ITEM_MODELS:
            return JsonResponse({"error": "Invalid item type"}, status=400)

        # Check if user has access to the item (either as owner or shared user)
        if not user_has_access_to_item(
            request.user, item_uuid=item_uuid, item_type=item_type
        ):
            return JsonResponse(
                {"error": f"{item_type.capitalize()} not found or access denied"},
                status=404,
            )

        # For sharing operations, user must be owner or co-owner
        if not UserSharePermission.user_can_share(
            request.user, item_uuid=item_uuid, item_type=item_type
        ):
            return JsonResponse(
                {"error": "Only owners and co-owners can manage sharing"}, status=403
            )

        return None

    def _notify_shared_users_if_requested(
        self,
        request: HttpRequest,
        item_uuid: UUID,
        item_type: ItemType,
        shared_users: list[str],
        message: str,
    ) -> None:
        """Send notifications to shared users if requested."""
        notify = request.POST.get("notify_users") == "1"
        if shared_users and notify:
            notify_shared_users.delay(
                item_uuid, item_type, shared_users, notify=True, message=message
            )

    def post(
        self,
        request: HttpRequest,
        item_uuid: UUID,
        item_type: ItemType,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        """
        Unified endpoint for sharing operations: adding users, updating permissions,
        and removing users.

        Args:
            request:    The HTTP request object
            item_uuid:  The UUID of the item to share
            item_type:  The type of item to share from ItemType enum
        Returns:
            A JSON response containing the response message
        """
        # Validate request
        validation_error = self._validate_share_request(request, item_uuid, item_type)
        if validation_error:
            return validation_error

        try:
            results = self._process_share_operations(request, item_uuid, item_type)
        except ShareOperationError as e:
            return JsonResponse({"error": e.message}, status=e.status_code)
        except (ValueError, json.JSONDecodeError) as e:
            return JsonResponse({"error": str(e)}, status=400)

        return self._build_share_response(
            request,
            item_uuid,
            item_type,
            results,
        )

    def _process_share_operations(
        self, request: HttpRequest, item_uuid: UUID, item_type: ItemType
    ) -> dict[str, list[str]]:
        """Process all sharing operations and return results."""
        # Parse all change types from the request
        new_users = self._parse_new_users(request)
        permission_changes = self._parse_permission_changes(request)
        removals = self._parse_removals(request)

        # Track results
        results: dict[str, list[str]] = {
            "added": [],
            "updated": [],
            "removed": [],
            "errors": [],
        }

        # Process new user additions
        if new_users:
            added_users, add_errors = self._add_users_to_item(
                item_uuid,
                item_type,
                new_users,
                request.user,
                request.POST.get("notify_message", "").strip() or "",
            )
            results["added"].extend(added_users)
            results["errors"].extend(add_errors)

        # Process permission changes
        for change in permission_changes:
            change_result = self._process_permission_change(
                request, item_uuid, item_type, change
            )
            if change_result.get("success"):
                results["updated"].append(change_result["message"])
            else:
                results["errors"].append(change_result["error"])

        # Process removals
        for removal in removals:
            removal_result = self._process_removal(
                request, item_uuid, item_type, removal
            )
            if removal_result.get("success"):
                results["removed"].append(removal_result["message"])
            else:
                results["errors"].append(removal_result["error"])

        return results

    def _build_share_response(
        self,
        request: HttpRequest,
        item_uuid: UUID,
        item_type: ItemType,
        results: dict[str, list[str]],
    ) -> JsonResponse:
        """Build the final JSON response for sharing operations."""
        # Send notifications if requested
        if results["added"]:
            self._notify_shared_users_if_requested(
                request,
                item_uuid,
                item_type,
                results["added"],
                request.POST.get("notify_message", "").strip() or "",
            )

        # Build response message
        messages = []
        if results["added"]:
            messages.append(f"Added {len(results['added'])} user(s)")
        if results["updated"]:
            messages.append(f"Updated {len(results['updated'])} permission(s)")
        if results["removed"]:
            messages.append(f"Removed {len(results['removed'])} user(s)")

        success_message = "; ".join(messages) if messages else "No changes made"

        return JsonResponse(
            {
                "success": len(results["errors"]) == 0,
                "message": success_message,
                "details": results,
            }
        )

    def _parse_new_users(self, request: HttpRequest) -> dict:
        """Parse new users to add from the request."""
        user_emails_str = request.POST.get("user-search", "").strip()
        if not user_emails_str:
            return {}

        # Parse user permissions if provided
        user_permissions = {}
        user_permissions_str = request.POST.get("user_permissions", "")
        if user_permissions_str:
            try:
                user_permissions = json.loads(user_permissions_str)
            except json.JSONDecodeError as err:
                msg = "Invalid user_permissions format"
                raise ValueError(msg) from err
            else:
                # Validate all permission levels
                valid_permissions = [
                    PermissionLevel.VIEWER,
                    PermissionLevel.CONTRIBUTOR,
                    PermissionLevel.CO_OWNER,
                ]
                for email, perm_level in user_permissions.items():
                    if perm_level not in valid_permissions:
                        msg = (
                            f"Invalid permission level '{perm_level}' for user {email}"
                        )
                        raise ValueError(msg) from None

        # Parse user emails and their permissions
        users = {}
        identifiers = [
            identifier.strip()
            for identifier in user_emails_str.split(",")
            if identifier.strip()
        ]

        for identifier in identifiers:
            permission = user_permissions.get(identifier, PermissionLevel.VIEWER)
            users[identifier] = permission

        return users

    def _parse_permission_changes(self, request: HttpRequest) -> list[dict]:
        """Parse permission changes from the request."""
        permission_changes_json = request.POST.get("permission_changes", "")
        if not permission_changes_json:
            return []

        try:
            changes_list = json.loads(permission_changes_json)
            # Convert from [["email", {change_data}], ...] to list of dicts
            return [
                {"user_email": email, **change_data}
                for email, change_data in changes_list
            ]
        except json.JSONDecodeError as err:
            msg = "Invalid permission_changes format"
            raise ValueError(msg) from err

    def _parse_removals(self, request: HttpRequest) -> list[str]:
        """Parse user removals from the request."""
        remove_users_json = request.POST.get("remove_users", "")
        if not remove_users_json:
            return []

        try:
            return json.loads(remove_users_json)
        except json.JSONDecodeError as err:
            msg = "Invalid remove_users format"
            raise ValueError(msg) from err

    def _process_permission_change(
        self,
        request: HttpRequest,
        item_uuid: UUID,
        item_type: ItemType,
        change: dict,  # pyright: ignore[reportMissingTypeArgument]
    ) -> dict:  # pyright: ignore[reportMissingTypeArgument]
        """Process a single permission change."""
        user_email = change.get("user_email")
        new_permission = change.get("permissionLevel", PermissionLevel.VIEWER)

        if not user_email or not new_permission:
            return {"success": False, "error": "Missing email or permission level"}
        if new_permission == "remove":
            return self._process_removal(request, item_uuid, item_type, user_email)

        # Validate permission level
        valid_permissions = [
            PermissionLevel.VIEWER,
            PermissionLevel.CONTRIBUTOR,
            PermissionLevel.CO_OWNER,
        ]
        if new_permission not in valid_permissions:
            error_msg = f"Invalid permission level: {new_permission}"
            raise ShareOperationError(
                error_msg, status_code=status.HTTP_400_BAD_REQUEST
            )

        # Handle group vs individual user
        if user_email.startswith("group:"):
            return self._update_group_permission(
                request, item_uuid, item_type, user_email, new_permission
            )
        return self._update_individual_permission(
            request, item_uuid, item_type, user_email, new_permission
        )

    def _process_removal(
        self,
        request: HttpRequest,
        item_uuid: UUID,
        item_type: ItemType,
        user_email: str,
    ) -> dict:
        """Process a single user removal."""
        if user_email.startswith("group:"):
            return self._remove_group_access(request, item_uuid, item_type, user_email)
        return self._remove_individual_access(request, item_uuid, item_type, user_email)

    def _update_individual_permission(
        self,
        request: HttpRequest,
        item_uuid: UUID,
        item_type: ItemType,
        user_email: str,
        new_permission: PermissionLevel,
    ) -> dict:
        """Update permission for an individual user."""
        try:
            user_to_update = User.objects.get(email=user_email)
            share_permission = self._get_existing_user_permission(
                user_to_update, item_uuid, item_type, request.user
            )

            if not share_permission:
                return {
                    "success": False,
                    "error": (
                        f"User {user_email} is not shared with this {item_type.lower()}"
                    ),
                }
            old_permission = share_permission.permission_level
            share_permission.permission_level = new_permission
            share_permission.is_enabled = True  # Re-enable if it was disabled
            share_permission.save()

            return {  # noqa: TRY300
                "success": True,
                "message": (
                    f"Updated {user_email} permission from {old_permission} "
                    f"to {new_permission}"
                ),
            }

        except User.DoesNotExist as err:
            error_msg = f"User with email {user_email} not found"
            raise ShareOperationError(
                error_msg, status_code=status.HTTP_400_BAD_REQUEST
            ) from err

    def _update_group_permission(
        self,
        request: HttpRequest,
        item_uuid: UUID,
        item_type: ItemType,
        group_identifier: str,
        new_permission: PermissionLevel,
    ) -> dict:
        """Update permission for a group."""
        try:
            group_uuid = group_identifier.split(":")[1]
            group = ShareGroup.objects.get(
                uuid=group_uuid, owner=request.user, is_deleted=False
            )

            group_permissions = UserSharePermission.objects.filter(
                item_uuid=item_uuid,
                item_type=item_type,
                share_groups=group,
                is_deleted=False,
                is_enabled=True,
            )

            if not group_permissions.exists():
                return {
                    "success": False,
                    "error": f"Group is not shared with this {item_type.lower()}",
                }
            updated_count = 0
            for permission in group_permissions:
                permission.permission_level = new_permission
                permission.save()
                updated_count += 1

            return {  # noqa: TRY300
                "success": True,
                "message": (
                    f"Updated {updated_count} group members to {new_permission} "
                    "permission"
                ),
            }

        except ShareGroup.DoesNotExist as err:
            error_msg = "Group not found or you don't own it"
            raise ShareOperationError(
                error_msg, status_code=status.HTTP_404_NOT_FOUND
            ) from err

    def _remove_individual_access(
        self,
        request: HttpRequest,
        item_uuid: UUID,
        item_type: ItemType,
        user_email: str,
    ) -> dict:
        """Remove access for an individual user."""
        try:
            user_to_remove = User.objects.get(email=user_email)
            share_permission = self._get_existing_user_permission(
                user_to_remove, item_uuid, item_type, request.user
            )

            if not share_permission:
                return {
                    "success": False,
                    "error": (
                        f"User {user_email} is not shared with this {item_type.lower()}"
                    ),
                }

            share_permission.is_enabled = False
            share_permission.save()

            return {
                "success": True,
                "message": f"Removed {user_email} from {item_type.lower()} sharing",
            }

        except User.DoesNotExist:
            return {
                "success": False,
                "error": f"User with email {user_email} not found",
            }

    def _remove_group_access(
        self,
        request: HttpRequest,
        item_uuid: UUID,
        item_type: ItemType,
        group_identifier: str,
    ) -> dict:
        """Remove access for a group."""
        try:
            group_uuid = group_identifier.split(":")[1]
            group = ShareGroup.objects.get(
                uuid=group_uuid, owner=request.user, is_deleted=False
            )

            group_permissions = UserSharePermission.objects.filter(
                item_uuid=item_uuid,
                item_type=item_type,
                share_groups=group,
                is_deleted=False,
                is_enabled=True,
            )

            if not group_permissions.exists():
                return {
                    "success": False,
                    "error": f"Group is not shared with this {item_type.lower()}",
                }

            removed_count = 0
            for permission in group_permissions:
                permission.share_groups.remove(group)
                permission.update_enabled_status()
                permission.message = "Unshared from group"
                permission.save()
                removed_count += 1

            return {
                "success": True,
                "message": (
                    f"Removed {removed_count} group members from "
                    f"{item_type.lower()} sharing"
                ),
            }

        except ShareGroup.DoesNotExist:
            return {"success": False, "error": "Group not found or you don't own it"}

    def _add_users_to_item(
        self,
        item_uuid: UUID,
        item_type: ItemType,
        users: dict,  # {email: permission_level}
        request_user: User,
        message: str,
    ) -> tuple[list[str], list[str]]:
        """
        Add users and groups to item sharing.
        Args:
            item_uuid: The UUID of the item to share
            item_type: The type of item to share
            users: Dictionary mapping user emails to permission levels
            request_user: The user sharing the item
        Returns:
            A tuple containing a list of shared users and a list of errors
        """
        shared_users: list[str] = []
        errors: list[str] = []

        for email, permission_level in users.items():
            if email.startswith("group:"):
                group_shared_users, group_errors = self._add_group_to_item(
                    email, item_uuid, item_type, request_user, message, permission_level
                )
                shared_users.extend(group_shared_users)
                errors.extend(group_errors)
            else:
                user_shared, user_error = self._add_individual_user_to_item(
                    email, item_uuid, item_type, request_user, message, permission_level
                )
                if user_shared:
                    shared_users.append(user_shared)
                if user_error:
                    errors.append(user_error)

        return shared_users, errors


user_share_item_view = ShareItemView.as_view()


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


def _get_captures_for_template(
    captures: QuerySet[Capture] | list[Capture] | Page[Capture],
    request: HttpRequest,
) -> list[dict[str, Any]]:
    """Get enhanced captures for the template."""
    enhanced_captures = []
    for capture in captures:
        # Use composite serialization to handle multi-channel captures properly
        capture_data = serialize_capture_or_composite(capture)

        # Add ownership flags for template display
        capture_data["is_owner"] = capture.owner == request.user
        capture_data["is_shared_with_me"] = capture.owner != request.user
        capture_data["owner_name"] = (
            capture.owner.name if capture.owner.name else "Owner"
        )
        capture_data["owner_email"] = capture.owner.email if capture.owner.email else ""

        # Add the original model instance for template use
        capture_data["capture"] = capture

        # Add shared users data for share modal
        if user_has_access_to_item(request.user, capture.uuid, ItemType.CAPTURE):
            # Get shared users and groups using the new model
            shared_permissions = (
                UserSharePermission.objects.filter(
                    item_uuid=capture.uuid,
                    item_type=ItemType.CAPTURE,
                    is_deleted=False,
                    is_enabled=True,
                )
                .select_related("shared_with")
                .prefetch_related("share_groups__members")
            )

            shared_users = []
            group_permissions = {}

            for perm in shared_permissions:
                if perm.share_groups.exists():
                    # Group member - collect by group
                    for group in perm.share_groups.all():
                        group_uuid = str(group.uuid)
                        if group_uuid not in group_permissions:
                            group_permissions[group_uuid] = {
                                "name": group.name,
                                "email": f"group:{group_uuid}",
                                "type": "group",
                                "members": [],
                                "permission_level": perm.permission_level,
                                "owner": group.owner.name,
                                "owner_email": group.owner.email,
                                "is_group_owner": group.owner == request.user,
                            }
                        group_permissions[group_uuid]["members"].append(
                            {
                                "name": perm.shared_with.name,
                                "email": perm.shared_with.email,
                            }
                        )
                else:
                    # Individual user
                    shared_users.append(
                        {
                            "name": perm.shared_with.name,
                            "email": perm.shared_with.email,
                            "type": "user",
                            "permission_level": perm.permission_level,
                        }
                    )

            # Add groups with member counts
            for group_data in group_permissions.values():
                group_data["member_count"] = len(group_data["members"])
                shared_users.append(group_data)
            capture_data["shared_users"] = shared_users
        else:
            capture_data["shared_users"] = []

        enhanced_captures.append(capture_data)

    return enhanced_captures


# API performance constant: maximum number of captures to return in API responses
API_CAPTURES_LIMIT = 25


def _get_user_captures_querysets(
    user: User,
) -> tuple[QuerySet[Capture], QuerySet[Capture]]:
    """Get owned and shared capture querysets for a user."""
    # Get captures owned by the user
    owned_captures = user.captures.filter(is_deleted=False)

    # Get captures shared with the user using the new UserSharePermission model
    shared_permissions = UserSharePermission.objects.filter(
        shared_with=user,
        item_type=ItemType.CAPTURE,
        is_deleted=False,
        is_enabled=True,
    ).values_list("item_uuid", flat=True)

    shared_captures = Capture.objects.filter(
        uuid__in=shared_permissions, is_deleted=False
    ).exclude(owner=user)

    return owned_captures, shared_captures


def _apply_frequency_filters_to_list(  # noqa: C901
    captures_list: list[Capture],
    min_freq: str | float | None,
    max_freq: str | float | None,
) -> list[Capture]:
    """Apply frequency filters to a list of captures."""
    if not captures_list or (not min_freq and not max_freq):
        return captures_list

    try:
        # Convert list to queryset for bulk frequency loading
        temp_qs = Capture.objects.filter(uuid__in=[c.uuid for c in captures_list])
        # Bulk load frequency metadata
        frequency_data = Capture.bulk_load_frequency_metadata(temp_qs)

        # Parse frequency values
        min_freq_str = str(min_freq).strip() if min_freq else ""
        max_freq_str = str(max_freq).strip() if max_freq else ""

        try:
            min_freq_val = float(min_freq_str) if min_freq_str else None
        except ValueError:
            min_freq_val = None

        try:
            max_freq_val = float(max_freq_str) if max_freq_str else None
        except ValueError:
            max_freq_val = None

        if min_freq_val is None and max_freq_val is None:
            return captures_list

        # Filter captures by frequency range
        filtered_captures: list[Capture] = []
        for capture in captures_list:
            capture_uuid = str(capture.uuid)
            freq_info = frequency_data.get(capture_uuid, {})
            center_freq_hz = freq_info.get("center_frequency")

            if center_freq_hz is None:
                continue

            try:
                center_freq_hz = float(center_freq_hz)
            except (ValueError, TypeError):
                continue

            center_freq_ghz = center_freq_hz / 1e9

            if min_freq_val is not None and center_freq_ghz < min_freq_val:
                continue
            if max_freq_val is not None and center_freq_ghz > max_freq_val:
                continue

            filtered_captures.append(capture)

    except (DatabaseError, AttributeError) as e:
        log.warning(f"Error in frequency filtering: {e}", exc_info=True)
        # Continue with unfiltered list on error
        return captures_list

    else:
        return filtered_captures


def _apply_sorting_to_list(
    captures_list: list[Capture],
    sort_by: str,
    sort_order: str,
) -> list[Capture]:
    """Apply sorting to a list of captures."""
    if not sort_by or not captures_list:
        return captures_list

    reverse = sort_order == "desc"
    try:
        allowed_sort_fields: set[str] = {
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
        }
        if sort_by in allowed_sort_fields:
            captures_list = sorted(
                captures_list,
                key=lambda c: (
                    getattr(c, sort_by, None) is None,
                    getattr(c, sort_by, ""),
                ),
                reverse=reverse,
            )
    except (TypeError, AttributeError) as e:
        log.warning(f"Sorting failed: {e}")

    return captures_list


def _get_filtered_and_sorted_captures(
    user: User,
    params: dict[str, Any],
    limit: int | None = None,
) -> list[Capture]:
    """
    Get filtered and sorted captures for a user based on parameters.

    Args:
        user:   The user to get captures for
        params: Dictionary of filter parameters
        limit:  Optional limit to apply to each queryset before union

    Returns:
        List of filtered, sorted, and deduplicated Capture objects
    """
    # Get owned and shared captures
    owned_captures, shared_captures = _get_user_captures_querysets(user)

    # Apply basic filters to each queryset
    owned_captures = _apply_basic_filters(
        qs=owned_captures,
        search=params["search"],
        date_start=params["date_start"],
        date_end=params["date_end"],
        cap_type=params["cap_type"],
    )
    shared_captures = _apply_basic_filters(
        qs=shared_captures,
        search=params["search"],
        date_start=params["date_start"],
        date_end=params["date_end"],
        cap_type=params["cap_type"],
    )

    # Apply limit to each queryset before union to reduce memory usage
    if limit is not None:
        # Add buffer to ensure we have enough after filtering/deduplication
        queryset_limit = int(limit * 1.5)  # 50% buffer
        owned_captures = owned_captures[:queryset_limit]
        shared_captures = shared_captures[:queryset_limit]

    # Union the querysets (all basic filters already applied)
    qs = owned_captures.union(shared_captures)

    # Convert to list (single DB query for union)
    captures_list: list[Capture] = list(qs)

    # Apply frequency filters to the combined list
    captures_list = _apply_frequency_filters_to_list(
        captures_list, params["min_freq"], params["max_freq"]
    )

    # Apply sorting to the combined list (union doesn't preserve order)
    captures_list = _apply_sorting_to_list(
        captures_list, params["sort_by"], params["sort_order"]
    )

    # Deduplicate composite captures
    unique_captures = deduplicate_composite_captures(captures_list)

    # Apply final limit if specified (after deduplication)
    if limit is not None:
        unique_captures = unique_captures[:limit]

    return unique_captures


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

        # Get filtered and sorted captures
        unique_captures = _get_filtered_and_sorted_captures(request.user, params)

        # Paginate the unique captures
        paginator = Paginator(unique_captures, params["items_per_page"])
        try:
            page_obj = paginator.page(params["page"])
        except (EmptyPage, PageNotAnInteger):
            page_obj = paginator.page(1)

        # Update the page_obj with enhanced captures
        page_obj.object_list = _get_captures_for_template(page_obj, request)

        # Get visualization compatibility data
        visualization_compatibility = get_visualization_compatibility()

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
                "visualization_compatibility": visualization_compatibility,
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

        try:
            # Extract and validate parameters
            params = self._extract_request_params(request)

            # Get filtered and sorted captures with API limit applied before union
            captures_list = _get_filtered_and_sorted_captures(
                request.user, params, limit=API_CAPTURES_LIMIT
            )

            try:
                captures_data = _get_captures_for_template(captures_list, request)
                # remove the Capture model instance from each
                #   capture_data dict for JSON serialization
                for capture_data in captures_data:
                    capture_data.pop("capture", None)
            except Exception as e:
                log.exception(f"Error in _get_captures_for_template: {e}")
                msg = f"Error getting capture data: {e!s}"
                raise ValueError(msg) from e

            response_data = {
                "captures": captures_data,
                "has_results": len(captures_data) > 0,
                "total_count": len(captures_data),
            }
            return JsonResponse(response_data)

        except (ValueError, TypeError) as e:
            error_msg = str(e)
            log.warning(
                f"Invalid parameter in captures API request: {error_msg}",
                exc_info=True,
            )
            return JsonResponse(
                {"error": f"Invalid search parameters: {error_msg}"},
                status=400,
            )
        except DatabaseError:
            log.exception("Database error in captures API request")
            return JsonResponse({"error": "Database error occurred"}, status=500)


user_capture_list_view = ListCapturesView.as_view()
user_captures_api_view = CapturesAPIView.as_view()


class KeywordAutocompleteAPIView(Auth0LoginRequiredMixin, View):
    """Handle API requests for keyword autocomplete suggestions."""

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """
        Return keyword suggestions based on search query.

        Returns up to 10 unique keyword suggestions that match the query
        anywhere in the keyword.
        """
        query = request.GET.get("q", "").strip()

        if not query:
            return JsonResponse({"suggestions": []})

        try:
            # Search for keywords that contain the query anywhere (case-insensitive)
            keywords = Keyword.objects.filter(
                name__icontains=query,
                is_deleted=False,
            ).values_list("name", flat=True)[:10]

            return JsonResponse({"suggestions": list(keywords)})

        except DatabaseError:
            log.exception("Database error in keyword autocomplete")
            return JsonResponse({"error": "Database error occurred"}, status=500)


keyword_autocomplete_api_view = KeywordAutocompleteAPIView.as_view()


class GroupCapturesView(
    Auth0LoginRequiredMixin, FormSearchMixin, FileTreeMixin, TemplateView
):
    template_name = "users/group_captures.html"

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
        return JsonResponse({"error": form.errors}, status=400)

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
        return JsonResponse({"error": form.errors}, status=400)

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
                dataset_uuid,
            )
            if validation_result:
                return validation_result

            if dataset_uuid_str:
                try:
                    dataset_uuid = UUID(dataset_uuid_str)
                except ValueError:
                    messages.error(request, "Invalid dataset UUID.")
                    return redirect("users:dataset_list")
                # Handle dataset editing
                return self._handle_dataset_edit(request, dataset_form, dataset_uuid)
            # Handle dataset creation
            return self._handle_dataset_creation(request, dataset_form)

        except (DatabaseError, IntegrityError) as e:
            log.exception("Database error in dataset creation")
            return JsonResponse(
                {"success": False, "errors": {"non_field_errors": [str(e)]}},
                status=500,
            )

    def _validate_dataset_form(
        self,
        request: HttpRequest,
        dataset_form: DatasetInfoForm,
        dataset_uuid: str | None = None,
    ) -> JsonResponse | None:
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
                if not dataset_form.is_valid():
                    return JsonResponse(
                        {"success": False, "errors": dataset_form.errors},
                        status=400,
                    )
            # If user can't edit metadata, skip form validation
        else:
            # For new dataset creation, always validate form
            if not dataset_form.is_valid():
                return JsonResponse(
                    {"success": False, "errors": dataset_form.errors},
                    status=400,
                )

            # Get selected assets
            selected_captures, selected_files = self._get_asset_selections(request)

            # Validate that at least one capture or file is selected
            if len(selected_captures) == 0 and len(selected_files) == 0:
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

    def _handle_dataset_edit(self, request, dataset_form: DatasetInfoForm, dataset_uuid: UUID) -> JsonResponse:
        """Handle dataset editing with asset management."""

        # Get dataset
        dataset = get_object_or_404(Dataset, uuid=dataset_uuid, owner=request.user)

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
            self._create_or_update_dataset(request, dataset_form, dataset)

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

    def _get_asset_selections(
        self,
        request: HttpRequest,
        dataset_uuid: str | None = None,
    ) -> tuple[list[str], list[str]]:
        """
        Get selected assets from the request.
        This function is used to get the selected assets on creation only.
        """
        if not dataset_uuid:
            selected_captures = request.POST.get("selected_captures", "").split(",")
            selected_files = request.POST.get("selected_files", "").split(",")
            return selected_captures, selected_files
        return [], []

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


def _apply_basic_filters(
    qs: QuerySet[Capture],
    search: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    cap_type: str | None = None,
) -> QuerySet[Capture]:
    """Apply basic filters: search, date range, and capture type."""
    if search:
        # First get the base queryset with direct field matches
        base_filter = (
            Q(name__icontains=search)
            | Q(channel__icontains=search)
            | Q(index_name__icontains=search)
            | Q(capture_type__icontains=search)
            | Q(uuid__icontains=search)
        )

        # Then add any captures where the display value matches
        display_matches = [
            capture.pk
            for capture in qs
            if search.lower() in capture.get_capture_type_display().lower()
        ]

        if display_matches:
            base_filter |= Q(pk__in=display_matches)

        qs = qs.filter(base_filter)

    if date_start:
        qs = qs.filter(created_at__gte=date_start)
    if date_end:
        qs = qs.filter(created_at__lte=date_end)
    if cap_type:
        qs = qs.filter(capture_type=cap_type)

    return qs


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

        try:
            is_public_value = json.loads(request.POST.get("is_public"))
        except json.JSONDecodeError:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Could not determine dataset visibility.",
                },
                status=400,
            )

        error_message = self._handle_400_errors(
            dataset,
            status_value,
            is_public_value=is_public_value,
        )
        if error_message:
            return JsonResponse({"success": False, "error": error_message}, status=400)

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
    ) -> str:
        """Handle status change."""

        # Initialize error message
        error_message = None

        # Validate that at least one field is being updated
        if not status_value and is_public_value is None:
            error_message = "No fields to update."
        # Validate status value
        if status_value and status_value not in [
            DatasetStatus.DRAFT,
            DatasetStatus.FINAL,
        ]:
            error_message = "Invalid status value."

        # Update status if provided and dataset is not already final
        if status_value:
            if (
                dataset.status == DatasetStatus.FINAL
                and status_value == DatasetStatus.DRAFT
            ):
                error_message = "Cannot change published dataset status back to Draft."

        if dataset.is_public and is_public_value is False:
            error_message = "Cannot change public dataset visibility back to Private."

        return error_message


user_publish_dataset_view = PublishDatasetView.as_view()


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
            log.exception(f"Error reading file: {temp_zip.file_path}")
            return JsonResponse({"error": "Error reading file."}, status=500)


user_temporary_zip_download_view = TemporaryZipDownloadView.as_view()


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

    def post(
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


class DatasetDetailsView(Auth0LoginRequiredMixin, FileTreeMixin, View):
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


class RenderHTMLFragmentView(Auth0LoginRequiredMixin, View):
    """Generic view to render any HTML fragment from a Django template."""

    def post(self, request: HttpRequest) -> JsonResponse:
        """
        Render HTML fragment using server-side templates.

        Expects JSON body with:
        ```json
        {
            "template": "users/components/my_component.html",
            "context": {
                "key": "value",
                ...
            }
        }
        ```
        Returns:
            JsonResponse with rendered HTML
        """
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        template_name = data.get("template")
        context = data.get("context", {})

        if not template_name:
            return JsonResponse({"error": "Template name is required"}, status=400)

        # Security: Only allow templates from users/components/ directory
        if not template_name.startswith("users/components/"):
            log.warning(f"Invalid template path: {template_name}")
            return JsonResponse(
                {"error": "Cannot render component."},
                status=400,
            )

        try:
            html = render_html_fragment(
                template_name=template_name,
                context=context,
                request=request,
            )

            return JsonResponse({"html": html})
        except Exception as e:  # noqa: BLE001
            log.exception(f"Error rendering template {data.get('template', 'unknown')}")
            return JsonResponse({"error": str(e)}, status=500)


render_html_fragment_view = RenderHTMLFragmentView.as_view()


class ShareGroupListView(Auth0LoginRequiredMixin, UserSearchMixin, View):
    """
    View to handle ShareGroup management functionality.

    This view allows users to:
    - View their owned ShareGroups
    - Create new ShareGroups
    - Add/remove members from ShareGroups
    - Delete ShareGroups
    """

    template_name = "users/share_group_list.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Display the ShareGroup management page."""
        # Check if this is an AJAX request for group members
        group_uuid = request.GET.get("group_uuid")
        search_query = request.GET.get("q")

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            if not group_uuid:
                return JsonResponse({"error": "Group not found."}, status=400)

            if search_query:
                return self._search_users_for_group(request, group_uuid, search_query)
            return self._get_group_members(request, group_uuid)

        return self._display_share_groups_page(request)

    def _search_users_for_group(
        self, request: HttpRequest, group_uuid: str, search_query: str
    ) -> HttpResponse:
        """Search users for a specific group."""
        try:
            group = request.user.owned_share_groups.get(
                uuid=group_uuid, is_deleted=False
            )
            users_in_group = group.members.values_list("id", flat=True)

            return self.search_users(
                request=request,
                exclude_user_ids=users_in_group,
                include_groups=False,
            )
        except ShareGroup.DoesNotExist:
            return JsonResponse({"error": "ShareGroup not found"}, status=404)

    def _display_share_groups_page(self, request: HttpRequest) -> HttpResponse:
        """Display the main share groups page."""
        share_groups = (
            request.user.owned_share_groups.filter(is_deleted=False)
            .prefetch_related("members")
            .order_by("-created_at")
        )

        context = {
            "share_groups": share_groups,
        }

        return render(request, self.template_name, context)

    def _get_group_members(self, request: HttpRequest, group_uuid: str) -> JsonResponse:
        """Get current members of a ShareGroup."""
        try:
            share_group = request.user.owned_share_groups.get(
                uuid=group_uuid, is_deleted=False
            )

            members = share_group.members.all().values("email", "name")
            member_list = [
                {"email": member["email"], "name": member["name"]} for member in members
            ]

            return JsonResponse(
                {"success": True, "members": member_list, "count": len(member_list)}
            )
        except ShareGroup.DoesNotExist:
            return JsonResponse({"error": "ShareGroup not found"}, status=404)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Handle ShareGroup operations (create, update, delete)."""
        action = request.POST.get("action")
        if not action:
            return JsonResponse({"error": "Action is required"}, status=400)

        action_handlers = {
            "create": self._create_share_group,
            "add_members": self._add_members_to_group,
            "remove_members": self._remove_members_from_group,
            "delete_group": self._delete_share_group,
            "get_shared_assets": self._get_shared_assets_for_group_request,
        }

        handler = action_handlers.get(action)
        if handler:
            return handler(request)
        return JsonResponse({"error": "Invalid action"}, status=400)

    def _create_share_group(self, request: HttpRequest) -> JsonResponse:
        """Create a new ShareGroup."""
        name = request.POST.get("name", "").strip()

        if not name:
            return JsonResponse({"error": "Group name is required"}, status=400)

        # Check if group name already exists for this user
        if request.user.owned_share_groups.filter(name=name, is_deleted=False).exists():
            return JsonResponse(
                {"error": "A group with this name already exists"}, status=400
            )

        try:
            share_group = ShareGroup.objects.create(name=name, owner=request.user)

            return JsonResponse(
                {
                    "success": True,
                    "message": f'ShareGroup "{name}" created successfully',
                    "group": {
                        "uuid": str(share_group.uuid),
                        "name": share_group.name,
                        "created_at": share_group.created_at.isoformat(),
                        "member_count": 0,
                    },
                }
            )
        except (ValueError, IntegrityError) as e:
            return JsonResponse({"error": f"Failed to create group: {e!s}"}, status=500)

    def _add_members_to_group(self, request: HttpRequest) -> JsonResponse:
        """Add members to a ShareGroup."""
        group_uuid = request.POST.get("group_uuid")
        user_emails_str = request.POST.get("user_emails", "").strip()

        if not group_uuid or not user_emails_str:
            return JsonResponse(
                {"error": "Group UUID and user emails are required"}, status=400
            )

        try:
            share_group = request.user.owned_share_groups.get(
                uuid=group_uuid, is_deleted=False
            )
        except ShareGroup.DoesNotExist:
            return JsonResponse({"error": "ShareGroup not found"}, status=404)

        # Get shared assets that will be accessible to new group members
        # (commented out as not currently used)

        # Parse and validate user emails
        user_emails = [
            email.strip() for email in user_emails_str.split(",") if email.strip()
        ]
        added_users, errors = self._process_user_addition(
            request=request,
            share_group=share_group,
            user_emails=user_emails,
            request_user=request.user,
        )

        return JsonResponse(
            {
                "success": True,
                "message": (
                    f'Added {len(added_users)} members to group "{share_group.name}"'
                ),
                "added_users": added_users,
                "errors": errors,
                "member_count": share_group.members.count(),
            }
        )

    def _process_user_addition(
        self,
        request: HttpRequest,
        share_group: ShareGroup,
        user_emails: list[str],
        request_user: User,
    ) -> tuple[list[str], list[str]]:
        """Process adding users to a group. Returns (added_users, errors)."""
        added_users = []
        errors = []

        for email in user_emails:
            try:
                user = User.objects.get(email=email, is_approved=True)

                if user == request_user:
                    errors.append(f"You cannot add yourself to a group ({email})")
                    continue

                if share_group.members.filter(id=user.id).exists():
                    errors.append(f"User {email} is already a member of this group")
                    continue

                share_group.members.add(user)
                added_users.append(email)

                # get the user_object from the email
                user_object = User.objects.get(email=email)
                message = (
                    f"You have been added to the group {share_group.name} "
                    f"by {request.user.name}"
                )

                self._share_items_with_users_in_group_on_add(
                    request=request,
                    group=share_group,
                    user=user_object,
                    message=message,
                )
            except User.DoesNotExist:
                errors.append(f"User with email {email} not found or not approved")

        return added_users, errors

    def _share_items_with_users_in_group_on_add(
        self,
        request: HttpRequest,
        group: ShareGroup,
        user: User,
        message: str,
    ) -> None:
        """Share items to new members of group on add"""

        # find share permissions for group members
        shared_items = (
            UserSharePermission.objects.filter(
                share_groups=group,
                is_deleted=False,
                is_enabled=True,
            )
            .values_list("item_uuid", "item_type")
            .distinct()
        )
        # create share permissions for new member
        for item_uuid, item_type in shared_items:
            update_or_create_user_group_share_permissions(
                request_user=request.user,
                group=group,
                share_user=user,
                item_uuid=item_uuid,
                item_type=item_type,
                message=message,
            )

    def _remove_members_from_group(self, request: HttpRequest) -> JsonResponse:
        """Remove members from a ShareGroup."""
        group_uuid = request.POST.get("group_uuid")
        user_emails_str = request.POST.get("user_emails", "").strip()

        if not group_uuid or not user_emails_str:
            return JsonResponse(
                {"error": "Group UUID and user emails are required"}, status=400
            )

        try:
            share_group = request.user.owned_share_groups.get(
                uuid=group_uuid, is_deleted=False
            )
        except ShareGroup.DoesNotExist:
            return JsonResponse({"error": "ShareGroup not found"}, status=404)

        # Parse user emails
        user_emails = [
            email.strip() for email in user_emails_str.split(",") if email.strip()
        ]
        removed_users, errors = self._process_user_removal(share_group, user_emails)

        return JsonResponse(
            {
                "success": True,
                "message": (
                    f"Removed {len(removed_users)} members from group "
                    f'"{share_group.name}"'
                ),
                "removed_users": removed_users,
                "errors": errors,
                "member_count": share_group.members.count(),
            }
        )

    def _process_user_removal(
        self, share_group: ShareGroup, user_emails: list[str]
    ) -> tuple[list[str], list[str]]:
        """Process removing users from a group. Returns (removed_users, errors)."""
        removed_users = []
        errors = []

        for email in user_emails:
            try:
                user = User.objects.get(email=email)

                if share_group.members.filter(id=user.id).exists():
                    share_group.members.remove(user)

                    # Update share permissions for this user
                    self._update_user_share_permissions_on_removal(user, share_group)

                    removed_users.append(email)
                else:
                    errors.append(f"User {email} is not a member of this group")

            except User.DoesNotExist:
                errors.append(f"User with email {email} not found")

        return removed_users, errors

    def _get_shared_assets_for_group(
        self, share_group: ShareGroup
    ) -> list[dict[str, Any]]:
        """Get list of shared assets that are accessible to group members."""
        # Find all share permissions where this group is associated
        share_permissions = (
            UserSharePermission.objects.filter(
                share_groups=share_group,
                is_deleted=False,
                is_enabled=True,
            )
            .select_related("owner")
            .distinct("item_uuid", "item_type")
        )
        shared_assets = []
        for permission in share_permissions:
            try:
                # Get the actual item based on type
                if permission.item_type == "dataset":
                    item = Dataset.objects.get(uuid=permission.item_uuid)
                elif permission.item_type == "capture":
                    item = Capture.objects.get(uuid=permission.item_uuid)
                else:
                    continue  # Skip unknown item types

                shared_assets.append(
                    {
                        "uuid": str(item.uuid),
                        "name": getattr(item, "name", str(item)),
                        "type": permission.item_type,
                        "owner_name": permission.owner.name,
                        "owner_email": permission.owner.email,
                    }
                )
            except (Dataset.DoesNotExist, Capture.DoesNotExist):
                # Skip if item no longer exists
                continue

        # Sort assets: datasets first (alphabetically), then captures (alphabetically)
        shared_assets.sort(
            key=lambda asset: (asset["type"] != "dataset", asset["name"].lower())
        )

        return shared_assets

    def _update_user_share_permissions_on_removal(
        self, user: User, share_group: ShareGroup
    ) -> None:
        """Update share permissions when a user is removed from a group."""
        # Find all share permissions where this user was shared via this group
        share_permissions = UserSharePermission.objects.filter(
            shared_with=user,
            share_groups=share_group,
            is_deleted=False,
            is_enabled=True,
        )

        # For each permission, remove the group association and update enabled status
        for permission in share_permissions:
            permission.share_groups.remove(share_group)
            permission.update_enabled_status()

    def _get_shared_assets_for_group_request(
        self, request: HttpRequest
    ) -> JsonResponse:
        """Get shared assets for a group (for display in modal)."""
        group_uuid = request.POST.get("group_uuid")

        if not group_uuid:
            return JsonResponse({"error": "Group UUID is required"}, status=400)

        try:
            share_group = request.user.owned_share_groups.get(
                uuid=group_uuid, is_deleted=False
            )
        except ShareGroup.DoesNotExist:
            return JsonResponse({"error": "ShareGroup not found"}, status=404)

        shared_assets = self._get_shared_assets_for_group(share_group)

        return JsonResponse({"success": True, "shared_assets": shared_assets})

    def _delete_share_group(self, request: HttpRequest) -> JsonResponse:
        """Delete a ShareGroup (soft delete)."""
        group_uuid = request.POST.get("group_uuid")

        if not group_uuid:
            return JsonResponse({"error": "Group UUID is required"}, status=400)

        try:
            share_group = request.user.owned_share_groups.get(
                uuid=group_uuid, is_deleted=False
            )
        except ShareGroup.DoesNotExist:
            return JsonResponse({"error": "ShareGroup not found"}, status=404)

        try:
            share_group.soft_delete()
            return JsonResponse(
                {
                    "success": True,
                    "message": f'ShareGroup "{share_group.name}" deleted successfully',
                }
            )
        except (ValueError, IntegrityError) as e:
            return JsonResponse({"error": f"Failed to delete group: {e!s}"}, status=500)


user_share_group_list_view = ShareGroupListView.as_view()


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
            from sds_gateway.api_methods.utils.metadata_schemas import infer_index_name  # noqa: I001

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


user_check_file_exists_view = CheckFileExistsView.as_view()


class SPXDACDatasetAltView(Auth0LoginRequiredMixin, View):
    """View for the SpectrumX Student Data Competition page."""

    template_name = "pages/spx_dac_dataset_alt.html"

    def get(self, request, *args, **kwargs):
        """Display the student data competition page and automatically share dataset."""
        dataset_id = settings.SPX_DAC_DATASET_ID
        if not dataset_id:
            log.warning("SPX_DAC_DATASET_ID not configured")
        else:
            try:
                dataset_uuid = UUID(dataset_id)
                # Get the dataset to find its owner
                try:
                    dataset = Dataset.objects.get(uuid=dataset_uuid, is_deleted=False)
                except Dataset.DoesNotExist:
                    log.warning(f"SpX-DAC dataset {dataset_id} not found")
                    dataset = None

                # Check if user is already the owner
                if dataset and dataset.owner != request.user:
                    # Check if permission already exists
                    existing_permission = UserSharePermission.objects.filter(
                        owner=dataset.owner,
                        shared_with=request.user,
                        item_type=ItemType.DATASET,
                        item_uuid=dataset_uuid,
                        is_deleted=False,
                    ).first()

                    if not existing_permission:
                        # Create share permission with VIEWER role
                        UserSharePermission.objects.create(
                            owner=dataset.owner,
                            shared_with=request.user,
                            item_type=ItemType.DATASET,
                            item_uuid=dataset_uuid,
                            message="Automatically shared for NSF SpectrumX "
                            "Data and Algorithm Competition (SpX-DAC)",
                            permission_level=PermissionLevel.VIEWER,
                            is_enabled=True,
                        )
                        log.info(
                            "Automatically shared SpX-DAC dataset "
                            f"with user {request.user.email}"
                        )
                    elif not existing_permission.is_enabled:
                        # Re-enable if it was previously disabled
                        existing_permission.is_enabled = True
                        existing_permission.save()
                        log.info(
                            "Re-enabled SpX-DAC dataset "
                            f"share for user {request.user.email}"
                        )
            except ValueError as e:
                log.warning(f"Invalid SpX-DAC dataset ID format: {e}")

        context = {
            "s3_bucket_url": settings.SPX_DAC_DATASET_S3_URL,
            "dataset_id": dataset_id or "458c3f72-8d7e-49cc-9be3-ed0b0cd7e03d",
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """Handle API key generation via AJAX."""
        # Check if user has reached the maximum number of active API keys
        api_keys = UserAPIKey.objects.filter(user=request.user).exclude(
            source=KeySources.SVIBackend
        )
        active_api_key_count = get_active_api_key_count(api_keys)
        if active_api_key_count >= MAX_API_KEY_COUNT:
            return JsonResponse(
                {
                    "success": False,
                    "error": "You have reached the maximum number of API keys "
                    f"({MAX_API_KEY_COUNT}). Please revoke an existing key before "
                    "creating a new one.",
                },
                status=400,
            )

        # Get the name from the form (optional)
        api_key_name = request.POST.get("api_key_name", "SpX-DAC Competition")
        api_key_description = request.POST.get(
            "api_key_description",
            "Generated for NSF SpectrumX Data and Algorithm Competition (SpX-DAC)",
        )

        try:
            # Create an API key for the user
            _, raw_key = UserAPIKey.objects.create_key(
                name=api_key_name,
                description=api_key_description,
                user=request.user,
                source=KeySources.SDSWebUI,
                expiry_date=None,
            )
            return JsonResponse({"success": True, "api_key": raw_key})
        except Exception:  # noqa: BLE001
            log.exception("Error generating API key for student competition")
            return JsonResponse(
                {
                    "success": False,
                    "error": "Failed to generate API key. Please try again.",
                },
                status=500,
            )


spx_dac_dataset_alt_view = SPXDACDatasetAltView.as_view()
