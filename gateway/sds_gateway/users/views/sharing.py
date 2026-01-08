import json
from typing import Any
from uuid import UUID

from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.views import View
from rest_framework import status

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import ShareGroup
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.tasks import notify_shared_users
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.mixins import UserSearchMixin
from sds_gateway.users.models import User
from sds_gateway.users.utils import update_or_create_user_group_share_permissions


class ShareOperationError(Exception):
    """Custom exception for share operation errors with HTTP status codes."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


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
