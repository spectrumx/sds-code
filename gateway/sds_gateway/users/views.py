import datetime
import json
import logging
import uuid
from pathlib import Path
from typing import Any
from typing import cast

from django.contrib import messages
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import EmptyPage
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
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import TemplateView
from django.views.generic import UpdateView
from rest_framework import status

from sds_gateway.api_methods.helpers.file_helpers import (
    check_file_contents_exist_helper,
)
from sds_gateway.api_methods.helpers.file_helpers import create_capture_helper_simple
from sds_gateway.api_methods.helpers.file_helpers import upload_file_helper_simple
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import KeySources
from sds_gateway.api_methods.models import ShareGroup
from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.tasks import is_user_locked
from sds_gateway.api_methods.tasks import notify_shared_users
from sds_gateway.api_methods.tasks import send_item_files_email
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user
from sds_gateway.users.forms import CaptureSearchForm
from sds_gateway.users.forms import DatasetInfoForm
from sds_gateway.users.forms import FileSearchForm
from sds_gateway.users.mixins import ApprovedUserRequiredMixin
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.mixins import FileTreeMixin
from sds_gateway.users.mixins import FormSearchMixin
from sds_gateway.users.mixins import UserSearchMixin
from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey
from sds_gateway.users.utils import deduplicate_composite_captures
from sds_gateway.users.utils import update_or_create_user_group_share_permissions
from sds_gateway.visualizations.config import get_visualization_compatibility

# Constants
MAX_API_KEY_COUNT = 10

# Add logger for debugging
logger = logging.getLogger(__name__)


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
        item_uuid = kwargs.get("item_uuid")
        item_type = kwargs.get("item_type")

        # Validate item type
        if item_type not in self.ITEM_MODELS:
            return JsonResponse(
                {"error": "Invalid item type"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate item UUID
        if not item_uuid:
            return JsonResponse(
                {"error": "Item UUID is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get the item to check existing shared users
        try:
            model_class = self.ITEM_MODELS[item_type]
            # Verify the item exists and user owns it
            model_class.objects.get(uuid=item_uuid, owner=request.user)

            # Get exclusion lists for search
            excluded_user_ids, excluded_group_ids = self._get_exclusion_lists(
                request.user, item_uuid, item_type
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
        self, user: User, item_uuid: str, item_type: str
    ) -> tuple[list[int], list[str]]:
        """Get lists of user IDs and group UUIDs to exclude from search results."""
        # Get individual users already shared with this item
        shared_user_ids = list(
            UserSharePermission.objects.filter(
                item_uuid=item_uuid,
                item_type=item_type,
                owner=user,
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
                owner=user,
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

    def _add_users_to_item(
        self,
        item_uuid: str,
        item_type: ItemType,
        user_emails_str: str,
        request_user: User,
        message: str = "",
    ) -> tuple[list[str], list[str]]:
        """
        Add users and groups to item sharing using UserSharePermission
        and return (shared_users, errors).

        Args:
            item_uuid: The UUID of the item to share
            item_type: The type of item to share from ItemType enum
            user_emails_str: A comma-separated string of user
            emails or group identifiers to share with
            request_user: The user sharing the item
            message: A message to share with the users

        Returns:
            A tuple containing a list of shared users and a list of errors
        """
        if not user_emails_str:
            return [], []

        identifiers = [
            identifier.strip()
            for identifier in user_emails_str.split(",") if identifier.strip()
        ]

        shared_users = []
        errors = []

        for identifier in identifiers:
            if identifier.startswith("group:"):
                group_shared_users, group_errors = self._add_group_to_item(
                    identifier, item_uuid, item_type, request_user, message
                )
                shared_users.extend(group_shared_users)
                errors.extend(group_errors)
            else:
                user_shared, user_error = self._add_individual_user_to_item(
                    identifier, item_uuid, item_type, request_user, message
                )
                if user_shared:
                    shared_users.append(user_shared)
                if user_error:
                    errors.append(user_error)

        return shared_users, errors

    def _add_group_to_item(
        self,
        group_identifier: str,
        item_uuid: str,
        item_type: ItemType,
        request_user: User,
        message: str,
    ) -> tuple[list[str], list[str]]:
        """Add a group to item sharing."""
        group_uuid = group_identifier.split(":")[1]  # Remove "group:" prefix
        shared_users = []
        errors = []

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
                )
                shared_users.append(member.email)

        except ShareGroup.DoesNotExist:
            errors.append("Group not found or you don't own it")

        return shared_users, errors

    def _add_individual_user_to_item(
        self,
        email: str,
        item_uuid: str,
        item_type: ItemType,
        request_user: User,
        message: str,
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
                # Re-enable the existing disabled permission
                existing_permission.is_enabled = True
                existing_permission.message = message
                existing_permission.save()
                return email, None

            # Create the share permission
            UserSharePermission.objects.create(
                owner=request_user,
                shared_with=user_to_share_with,
                item_type=item_type,
                item_uuid=item_uuid,
                message=message,
                is_enabled=True,
            )
        except User.DoesNotExist:
            return None, f"User with email {email} not found or not approved"
        else:
            return email, None

    def _get_existing_user_permission(
        self, user: User, item_uuid: str, item_type: ItemType, request_user: User
    ) -> UserSharePermission | None:
        """Get existing share permission for a user and item."""
        return UserSharePermission.objects.filter(
            item_uuid=item_uuid,
            item_type=item_type,
            owner=request_user,
            shared_with=user,
            is_deleted=False,
        ).first()

    def _remove_users_from_item(
        self,
        item_uuid: str,
        item_type: str,
        users_to_remove: list[str],
        request_user: User,
    ) -> tuple[list[str], list[str]]:
        """
        Remove users and groups from item sharing using UserSharePermission
        and return (removed_users, errors).

        Args:
            item_uuid: The UUID of the item to share
            item_type: The type of item to share from ItemType enum
            users_to_remove: A list of user emails or group identifiers to remove
            request_user: The user removing the users

        Returns:
            A tuple containing a list of removed users and a list of errors
        """
        removed_users = []
        errors = []

        for identifier in users_to_remove:
            if identifier.startswith("group:"):
                group_removed_users, group_errors = self._remove_group_from_item(
                    identifier, item_uuid, item_type, request_user
                )
                removed_users.extend(group_removed_users)
                errors.extend(group_errors)
            else:
                user_removed, user_error = self._remove_individual_user_from_item(
                    identifier, item_uuid, item_type, request_user
                )
                if user_removed:
                    removed_users.append(user_removed)
                if user_error:
                    errors.append(user_error)

        return removed_users, errors

    def _remove_group_from_item(
        self, group_identifier: str, item_uuid: str, item_type: str, request_user: User
    ) -> tuple[list[str], list[str]]:
        """Remove a group from item sharing."""
        group_uuid = group_identifier.split(":")[1]  # Remove "group:" prefix
        removed_users: list[str] = []
        errors: list[str] = []

        try:
            group = ShareGroup.objects.get(
                uuid=group_uuid, owner=request_user, is_deleted=False
            )

            group_name = group.name

            # Check if any group members are actually shared with this item
            group_member_permissions = UserSharePermission.objects.filter(
                item_uuid=item_uuid,
                item_type=item_type,
                owner=request_user,
                share_groups=group,
                is_deleted=False,
                is_enabled=True,
            )

            if not group_member_permissions.exists():
                errors.append(
                    f"{item_type.capitalize()} is not shared with group: {group_name}"
                )
                return removed_users, errors

            # Disable all individual permissions for group members
            for permission in group_member_permissions:
                permission.share_groups.remove(group)
                permission.update_enabled_status()
                permission.message = "Unshared from group"
                permission.save()

            removed_users.extend(
                member.shared_with.email for member in group_member_permissions
            )

        except ShareGroup.DoesNotExist:
            errors.append(f"Group '{group_name}' not found or you don't own it")

        return removed_users, errors

    def _remove_individual_user_from_item(
        self, email: str, item_uuid: str, item_type: str, request_user: User
    ) -> tuple[str | None, str | None]:
        """
        Remove an individual user from item sharing.
        Returns (removed_user, error).
        """
        try:
            user_to_remove = User.objects.get(email=email)

            # Check if the user is actually shared with this item
            share_permission = UserSharePermission.objects.filter(
                item_uuid=item_uuid,
                item_type=item_type,
                owner=request_user,
                shared_with=user_to_remove,
                is_deleted=False,
            ).first()

            if not share_permission or not share_permission.is_enabled:
                return (
                    None,
                    f"{item_type.capitalize()} is not shared with user: {email}",
                )

            # Disable the share permission instead of soft deleting
            share_permission.is_enabled = False
            share_permission.save()
        except User.DoesNotExist:
            return None, f"User with email {email} not found"
        else:
            return email, None

    def _build_response(
        self,
        item_type: str,
        shared_users: list[str],
        removed_users: list[str],
        errors: list[str],
    ) -> JsonResponse:
        """
        Build the response message based on the results.

        Args:
            item_type: The type of item to share from ItemType enum
            shared_users: A list of user emails that were shared
            removed_users: A list of user emails that were removed
            errors: A list of error messages

        Returns:
            A JSON response containing the response message
        """
        response_parts = []
        if shared_users:
            response_parts.append(
                f"{item_type.capitalize()} shared with {', '.join(shared_users)}"
            )
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
        self,
        request: HttpRequest,
        item_uuid: str,
        item_type: ItemType,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        """
        Share an item with another user using the generalized permission system.

        Args:
            request: The HTTP request object
            item_uuid: The UUID of the item to share
            item_type: The type of item to share from ItemType enum

        Returns:
            A JSON response containing the response message
        """
        # Validate request
        validation_error = self._validate_share_request(request, item_uuid, item_type)
        if validation_error:
            return validation_error

        # Get form data
        user_emails_str = request.POST.get("user-search", "").strip()
        message = request.POST.get("notify_message", "").strip() or ""

        # Parse users to remove
        try:
            users_to_remove = self._parse_remove_users(request)
        except ValueError:
            return JsonResponse({"error": "Invalid remove_users format"}, status=400)

        # Handle adding new users
        shared_users, add_errors = self._add_users_to_item(
            item_uuid, item_type, user_emails_str, request.user, message
        )

        # Handle removing users
        removed_users, remove_errors = self._remove_users_from_item(
            item_uuid, item_type, users_to_remove, request.user
        )

        # Combine all errors
        errors = add_errors + remove_errors

        # Notify shared users if requested
        self._notify_shared_users_if_requested(
            request, item_uuid, item_type, shared_users, message
        )

        # Build and return response
        return self._build_response(item_type, shared_users, removed_users, errors)

    def _validate_share_request(
        self, request: HttpRequest, item_uuid: str, item_type: ItemType
    ) -> JsonResponse | None:
        """
        Validate the share request.
        Returns error response if invalid, None if valid.
        """
        # Validate item type
        if item_type not in self.ITEM_MODELS:
            return JsonResponse({"error": "Invalid item type"}, status=400)

        # Verify the item exists and user owns it
        try:
            model_class = self.ITEM_MODELS[item_type]
            model_class.objects.get(uuid=item_uuid, owner=request.user)
        except model_class.DoesNotExist:
            return JsonResponse(
                {"error": f"{item_type.capitalize()} not found"}, status=404
            )

        return None

    def _notify_shared_users_if_requested(
        self,
        request: HttpRequest,
        item_uuid: str,
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

    def delete(
        self,
        request: HttpRequest,
        item_uuid: str,
        item_type: str,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        """Remove a user from item sharing using the generalized permission system.

        Args:
            request: The HTTP request object
            item_uuid: The UUID of the item to share
            item_type: The type of item to share from ItemType enum

        Returns:
            A JSON response containing the response message
        """
        # Validate request
        validation_error = self._validate_share_request(request, item_uuid, item_type)
        if validation_error:
            return validation_error

        # Get the user email from the request
        user_email = request.POST.get("user_email", "").strip()

        if not user_email:
            return JsonResponse({"error": "User email is required"}, status=400)

        try:
            # Find the user to remove
            user_to_remove = User.objects.get(email=user_email)

            # Check if the user is actually shared with this item
            share_permission = UserSharePermission.objects.filter(
                item_uuid=item_uuid,
                item_type=item_type,
                owner=request.user,
                shared_with=user_to_remove,
                is_deleted=False,
            ).first()

            if not share_permission or not share_permission.is_enabled:
                return JsonResponse(
                    {
                        "error": (
                            f"User {user_email} is not shared with this "
                            f"{item_type.lower()}"
                        )
                    },
                    status=400,
                )

            # Disable the share permission instead of soft deleting
            share_permission.is_enabled = False
            share_permission.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Removed {user_email} from {item_type.lower()} sharing",
                }
            )

        except User.DoesNotExist:
            return JsonResponse(
                {"error": f"User with email {user_email} not found"}, status=400
            )


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


def _get_captures_for_template(
    captures: QuerySet[Capture],
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
        if capture.owner == request.user:
            # Get shared users and groups using the new model
            shared_permissions = (
                UserSharePermission.objects.filter(
                    item_uuid=capture.uuid,
                    item_type=ItemType.CAPTURE,
                    owner=request.user,
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

        # Get captures owned by the user
        owned_captures = request.user.captures.filter(is_deleted=False)

        # Get captures shared with the user using the new UserSharePermission model
        shared_permissions = UserSharePermission.objects.filter(
            shared_with=request.user,
            item_type=ItemType.CAPTURE,
            is_deleted=False,
            is_enabled=True,
        ).values_list("item_uuid", flat=True)

        shared_captures = Capture.objects.filter(
            uuid__in=shared_permissions, is_deleted=False
        ).exclude(owner=request.user)

        # Combine owned and shared captures
        qs = owned_captures.union(shared_captures)

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
        logger = logging.getLogger(__name__)

        try:
            # Extract and validate parameters
            params = self._extract_request_params(request)

            # Get captures owned by the user
            owned_captures = Capture.objects.filter(
                owner=request.user, is_deleted=False
            )

            # Get captures shared with the user using the new UserSharePermission model
            shared_permissions = UserSharePermission.objects.filter(
                shared_with=request.user,
                item_type=ItemType.CAPTURE,
                is_deleted=False,
                is_enabled=True,
            ).values_list("item_uuid", flat=True)

            shared_captures = Capture.objects.filter(
                uuid__in=shared_permissions, is_deleted=False
            ).exclude(owner=request.user)

            # Combine owned and shared captures
            qs = owned_captures.union(shared_captures)

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

            captures_data = _get_captures_for_template(captures_list, request)

            response_data = {
                "captures": captures_data,
                "has_results": len(captures_data) > 0,
                "total_count": len(captures_data),
            }
            return JsonResponse(response_data)

        except (ValueError, TypeError) as e:
            logger.warning("Invalid parameter in captures API request: %s", e)
            return JsonResponse({"error": "Invalid search parameters"}, status=400)
        except DatabaseError:
            logger.exception("Database error in captures API request")
            return JsonResponse({"error": "Database error occurred"}, status=500)


user_capture_list_view = ListCapturesView.as_view()
user_captures_api_view = CapturesAPIView.as_view()


class GroupCapturesView(
    Auth0LoginRequiredMixin, FormSearchMixin, FileTreeMixin, TemplateView
):
    template_name = "users/group_captures.html"

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
            # Validate form and get selected items
            validation_result = self._validate_dataset_form(request)
            if validation_result:
                return validation_result

            dataset_form, selected_captures, selected_files = (
                self._get_form_and_selections(request)
            )

            # Create or update dataset
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

        except (DatabaseError, IntegrityError) as e:
            logger.exception("Database error in dataset creation")
            return JsonResponse(
                {"success": False, "errors": {"non_field_errors": [str(e)]}},
                status=500,
            )

    def _validate_dataset_form(self, request) -> JsonResponse | None:
        """Validate the dataset form and return error response if invalid."""
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

        return None

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
            dataset.authors = [dataset_form.cleaned_data["author"]]
            dataset.status = dataset_form.cleaned_data["status"]
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
                status=dataset_form.cleaned_data["status"],
                owner=request.user,
            )

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
            files = File.objects.filter(uuid__in=selected_files)
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
        """Handle GET request for dataset list."""
        sort_by, sort_order = self._get_sort_parameters(request)
        order_by = self._build_order_by(sort_by, sort_order)

        owned_datasets = self._get_owned_datasets(request.user, order_by)
        shared_datasets = self._get_shared_datasets(request.user, order_by)

        datasets_with_shared_users = []
        datasets_with_shared_users.extend(
            self._prepare_owned_datasets(owned_datasets, request.user)
        )
        datasets_with_shared_users.extend(
            self._prepare_shared_datasets(shared_datasets)
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
        return user.datasets.filter(is_deleted=False).all().order_by(order_by)

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
            .order_by(order_by)
        )

    def _prepare_owned_datasets(
        self, datasets: QuerySet[Dataset], user: User
    ) -> list[dict]:
        """Prepare owned datasets with shared user information."""
        result = []
        for dataset in datasets:
            # Use serializer for API fields, but keep the original model for template
            dataset_data = DatasetGetSerializer(dataset).data
            shared_users = self._get_shared_users_for_dataset(dataset, user)

            dataset_data.update(
                {
                    "shared_users": shared_users,
                    "is_owner": True,
                    "is_shared_with_me": False,
                    "owner_name": dataset.owner.name or "Owner",
                    "owner_email": dataset.owner.email or "",
                    # Add the original model instance for template use
                    "dataset": dataset,
                }
            )
            result.append(dataset_data)
        return result

    def _prepare_shared_datasets(self, datasets: QuerySet[Dataset]) -> list[dict]:
        """Prepare shared datasets with shared user information."""
        result = []
        for dataset in datasets:
            dataset_data = DatasetGetSerializer(dataset).data
            shared_users = self._get_shared_users_for_dataset(dataset, dataset.owner)

            dataset_data.update(
                {
                    "shared_users": shared_users,
                    "is_owner": False,
                    "is_shared_with_me": True,
                    "owner_name": dataset.owner.name or "Owner",
                    "owner_email": dataset.owner.email or "",
                    # Add the original model instance for template use
                    "dataset": dataset,
                }
            )
            result.append(dataset_data)
        return result

    def _get_shared_users_for_dataset(
        self, dataset: Dataset, owner: User
    ) -> list[dict]:
        """Get shared users and groups for a dataset."""
        shared_permissions = (
            UserSharePermission.objects.filter(
                item_uuid=dataset.uuid,
                item_type=ItemType.DATASET,
                owner=owner,
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
                self._process_group_permission(perm, group_permissions)
            else:
                self._process_individual_permission(perm, shared_users)

        # Add groups with member counts
        for group_data in group_permissions.values():
            group_data["member_count"] = len(group_data["members"])
            shared_users.append(group_data)

        return shared_users

    def _process_group_permission(
        self, perm: UserSharePermission, group_permissions: dict
    ) -> None:
        """Process a group permission and update group_permissions dict."""
        for group in perm.share_groups.all():
            group_uuid = str(group.uuid)
            if group_uuid not in group_permissions:
                group_permissions[group_uuid] = {
                    "name": group.name,
                    "email": f"group:{group_uuid}",
                    "type": "group",
                    "members": [],
                    "permission_level": perm.permission_level,
                }
            group_permissions[group_uuid]["members"].append(
                {
                    "name": perm.shared_with.name,
                    "email": perm.shared_with.email,
                }
            )

    def _process_individual_permission(
        self, perm: UserSharePermission, shared_users: list
    ) -> None:
        """Process an individual permission and update shared_users list."""
        user_data = {
            "name": perm.shared_with.name,
            "email": perm.shared_with.email,
            "type": "user",
        }
        if hasattr(perm, "permission_level"):
            user_data["permission_level"] = perm.permission_level
        shared_users.append(user_data)

    def _paginate_datasets(self, datasets: list[dict], request: HttpRequest) -> Any:
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
            Q(channel__icontains=search)
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
        item_uuid: str,
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
        try:
            model_class = self.ITEM_MODELS[item_type]
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
        dataset_uuid = request.GET.get("dataset_uuid")

        if not dataset_uuid:
            return JsonResponse({"error": "Dataset UUID is required"}, status=400)

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
        except Exception:
            logger.exception("Error retrieving dataset details")
            return JsonResponse({"error": "Internal server error"}, status=500)


user_dataset_details_view = DatasetDetailsView.as_view()


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
            logger.error(
                "upload_chunk_files and relative_paths have different lengths: "
                "%d vs %d",
                len(upload_chunk_files),
                len(relative_paths),
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
                logger.info(
                    "Skipping empty file: %s (likely a placeholder for skipped file)",
                    filename,
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
                    logger.error(error_msg)
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
            from sds_gateway.api_methods.utils.metadata_schemas import infer_index_name

            capture_data["index_name"] = infer_index_name(capture_data["capture_type"])

            # Use the helper function to create the capture
            responses, capture_errors = create_capture_helper_simple(
                request, capture_data
            )
        except (ValueError, TypeError, AttributeError) as exc:
            logger.exception("Data validation error creating capture")
            return None, f"Data validation error: {exc}"
        except (ConnectionError, TimeoutError) as exc:
            logger.exception("Network error creating capture")
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
                logger.warning(
                    "Unexpected response format: %s",
                    response.data,
                )
                return (
                    None,
                    f"Unexpected response format: {response.data}",
                )
            # Capture creation failed
            error_msg = capture_errors[0] if capture_errors else "Unknown error"
            logger.error(
                "Failed to create capture: %s",
                error_msg,
            )
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
            logger.info(
                "Creating captures - has_required_fields: %s, capture_type: %s, "
                "channels: %s, scan_group: %s",
                has_required_fields,
                capture_type,
                channels,
                scan_group,
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
                logger.error("Capture creation errors: %s", capture_errors)
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
            logger.info(
                "Upload request - files count: %s, all_relative_paths count: %s, "
                "all_files_empty: %s, capture_type: %s, channels: %s, scan_group: %s",
                len(upload_chunk_files) if upload_chunk_files else 0,
                len(all_relative_paths) if all_relative_paths else 0,
                all_files_empty,
                capture_type,
                channels,
                scan_group,
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
                logger.info(
                    "Skipping capture creation due to file upload errors: %s",
                    file_errors,
                )
            else:
                logger.info(
                    "Skipping capture creation for chunk %s of %s",
                    chunk_number,
                    total_chunks,
                )

            # Log file upload errors if they occurred
            if file_errors and not all_files_empty:
                logger.error(
                    "File upload errors occurred. Errors: %s",
                    file_errors,
                )

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
            logger.warning(
                "Data validation error in UploadCaptureView.post: %s", str(e)
            )
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
            logger.exception("Network error in UploadCaptureView.post")
            return JsonResponse(
                {
                    "success": False,
                    "error": "Network connection error",
                    "error_code": "NETWORK_ERROR",
                    "message": f"Network error: {e!s}",
                },
                status=503,
            )
        except Exception as e:
            logger.exception("Unexpected error in UploadCaptureView.post")
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


user_check_file_exists_view = CheckFileExistsView.as_view()
