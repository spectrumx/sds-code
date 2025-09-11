"""
Permission checking utilities for the API methods app.

This module provides functions to check user permissions on datasets and captures
based on the new access level system.
"""

from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse

from ..models import UserSharePermission


def require_permission(permission_check_func):
    """
    Decorator to require a specific permission for a view.

    Args:
        permission_check_func: Function that takes (user, item_uuid, item_type)
                              and returns a boolean

    Returns:
        Decorator function
    """

    def decorator(view_func):
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            # Extract item_uuid and item_type from kwargs
            item_uuid = kwargs.get("item_uuid")
            item_type = kwargs.get("item_type")

            if not item_uuid or not item_type:
                return JsonResponse(
                    {"error": "Missing item_uuid or item_type"}, status=400
                )

            # Check if user has the required permission
            if not permission_check_func(request.user, item_uuid, item_type):
                return JsonResponse({"error": "Insufficient permissions"}, status=403)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_view_permission(view_func):
    """Decorator to require view permission for a dataset or capture."""
    return require_permission(UserSharePermission.user_can_view)(view_func)


def require_add_assets_permission(view_func):
    """Decorator to require permission to add assets to a dataset or capture."""
    return require_permission(UserSharePermission.user_can_add_assets)(view_func)


def require_remove_assets_permission(view_func):
    """Decorator to require permission to remove assets from a dataset or capture."""
    return require_permission(UserSharePermission.user_can_remove_assets)(view_func)


def require_edit_dataset_permission(view_func):
    """Decorator to require permission to edit dataset metadata."""
    return require_permission(UserSharePermission.user_can_edit_dataset)(view_func)


def check_asset_ownership_permission(user, asset_owner, item_uuid, item_type):
    """
    Check if a user can modify an asset based on ownership and permissions.

    Args:
        user: The user attempting to modify the asset
        asset_owner: The owner of the asset being modified
        item_uuid: UUID of the dataset/capture containing the asset
        item_type: Type of item (dataset or capture)

    Returns:
        bool: True if user can modify the asset, False otherwise
    """
    # User can always modify their own assets
    if user == asset_owner:
        return True

    # Check if user has permission to remove others' assets
    return UserSharePermission.user_can_remove_others_assets(user, item_uuid, item_type)


def get_user_permission_level(user, item_uuid, item_type):
    """
    Get the permission level for a user on a specific item.

    Args:
        user: The user to check permissions for
        item_uuid: UUID of the item
        item_type: Type of item (dataset or capture)

    Returns:
        str: Permission level ("owner", "co-owner", "contributor", "viewer", or None)
    """
    return UserSharePermission.get_user_permission_level(user, item_uuid, item_type)


def can_user_access_item(user, item_uuid, item_type):
    """
    Check if a user has any access to an item.

    Args:
        user: The user to check access for
        item_uuid: UUID of the item
        item_type: Type of item (dataset or capture)

    Returns:
        bool: True if user has access, False otherwise
    """
    return UserSharePermission.user_can_view(user, item_uuid, item_type)
