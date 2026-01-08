from typing import Any

from django.db.utils import IntegrityError
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ShareGroup
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.mixins import UserSearchMixin
from sds_gateway.users.models import User
from sds_gateway.users.utils import update_or_create_user_group_share_permissions


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
                    f"by {request_user.name}"
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
