from typing import Any

from django.contrib.auth.models import User

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import ShareGroup
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)


def deduplicate_composite_captures(captures: list[Capture]) -> list[Capture]:
    """
    Deduplicate composite captures by top_level_dir, keeping only the base capture
    (first by created_at).

    Args:
        captures: List of Capture objects to deduplicate

    Returns:
        List of unique captures with composite captures deduplicated
    """
    seen_top_level_dirs = set()
    unique_captures = []
    composite_groups: dict[str, list[Capture]] = {}

    # First pass: group composite captures by top_level_dir
    for capture in captures:
        if capture.is_multi_channel:
            if capture.top_level_dir not in composite_groups:
                composite_groups[capture.top_level_dir] = []
            composite_groups[capture.top_level_dir].append(capture)
        else:
            unique_captures.append(capture)

    # Second pass: for each composite group, add only the base capture
    # (first by created_at)
    for top_level_dir, group_captures in composite_groups.items():
        if top_level_dir not in seen_top_level_dirs:
            # Sort by created_at to get the base capture (first one)
            base_capture = sorted(group_captures, key=lambda c: c.created_at)[0]
            unique_captures.append(base_capture)
            seen_top_level_dirs.add(top_level_dir)

    return unique_captures


def serialize_composite_capture_for_display(capture: Capture) -> dict[str, Any]:
    """
    Serialize a capture (single or composite) for display in templates and JavaScript.

    Args:
        capture: Capture object to serialize

    Returns:
        Dictionary with serialized capture data for display
    """
    # Use composite capture serialization to get proper details
    serialized_data = serialize_capture_or_composite(capture)

    # Extract owner information
    owner_data = serialized_data.get("owner", {})
    owner_id = owner_data.get("id") if owner_data else None
    owner_name = owner_data.get("name") if owner_data else None
    owner_email = owner_data.get("email") if owner_data else None

    # Handle composite vs single capture display
    if serialized_data.get("is_multi_channel"):
        # This is a composite capture
        channel_objects = serialized_data.get("channels", [])
        channel_list = ", ".join(
            [channel_obj["channel"] for channel_obj in channel_objects]
        )
        uuid_list = [channel_obj["uuid"] for channel_obj in channel_objects]
        return {
            "id": serialized_data["uuid"],
            "type": serialized_data["capture_type_display"],
            "directory": serialized_data["top_level_dir"].split("/")[-1],
            "channel": channel_list,
            "scan_group": "-",
            "created_at": serialized_data["created_at"],
            "captures_in_composite": uuid_list,
            "is_multi_channel": True,
            "channels": channel_objects,
            "owner_id": owner_id,
            "owner_name": owner_name or owner_email or "Unknown",
            "owner": owner_data,
        }

    # This is a single capture
    return {
        "id": serialized_data["uuid"],
        "type": serialized_data["capture_type_display"],
        "directory": serialized_data["top_level_dir"].split("/")[-1],
        "channel": serialized_data.get("channel", "") or "-",
        "scan_group": serialized_data.get("scan_group", "") or "-",
        "created_at": serialized_data["created_at"],
        "is_multi_channel": False,
        "owner_id": owner_id,
        "owner_name": owner_name or owner_email or "Unknown",
        "owner": owner_data,
    }


def update_or_create_user_group_share_permissions(
    request_user: User,
    group: ShareGroup,
    share_user: User,
    item_uuid: str,
    item_type: ItemType,
    message: str,
    permission_level: str = "viewer",
) -> None:
    """
    Update or add share permissions for a user in a group.

    Args:
        request_user: The User object that is sharing the item
        group: The ShareGroup object
        share_user: The User object that is being shared with
        item_uuid: The UUID of the item to share
        item_type: The type of the item to share
        message: The message to share with the user
        permission_level: The permission level to grant (viewer, contributor, co-owner)

    Returns:
        None
    """
    existing_individual = UserSharePermission.objects.filter(
        owner=request_user,
        shared_with=share_user,
        item_uuid=item_uuid,
        item_type=item_type,
        is_deleted=False,
    ).first()

    if not existing_individual:
        permission = UserSharePermission.objects.create(
            owner=request_user,
            shared_with=share_user,
            item_type=item_type,
            item_uuid=item_uuid,
            message=message,
            permission_level=permission_level,
            is_enabled=True,
        )
        permission.share_groups.add(group)
    else:
        existing_individual.is_enabled = True
        existing_individual.message = message
        existing_individual.permission_level = permission_level
        existing_individual.share_groups.add(group)
        existing_individual.save()
