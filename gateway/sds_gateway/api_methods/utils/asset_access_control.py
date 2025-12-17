"""Capture access utility functions for the SDS Gateway API."""

from django.db.models import Q

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.models import user_has_access_to_item


def user_has_access_to_capture(user, capture: Capture) -> bool:
    """
    Check if a user has access to a capture.

    A user has access if:
    1. They own the capture directly, OR
    2. The capture is shared with them, OR
    3. The capture is part of a dataset that is shared with them

    Args:
        user: The user to check access for
        capture: The capture to check access for

    Returns:
        bool: True if user has access, False otherwise
    """
    user_has_access_to_capture = user_has_access_to_item(
        user,
        capture.uuid,
        ItemType.CAPTURE,
    )
    user_has_access_to_dataset = capture.datasets.filter(
        Q(owner=user) | Q(shared_with=user),
        is_deleted=False,
    ).exists()
    
    return user_has_access_to_capture or user_has_access_to_dataset


def user_has_access_to_file(user, file: File) -> bool:
    """
    Check if a user has access to a file.

    A user has access if:
    1. They own the file directly, OR
    2. The file is part of a capture that is shared with them, OR
    3. The file is part of a dataset that is shared with them, OR
    4. The file is part of a capture that is part of a shared dataset

    Args:
        user: The user to check access for
        file: The file to check access for

    Returns:
        bool: True if user has access, False otherwise
    """
    user_owns_file = file.owner == user
    user_has_access_to_capture = file.captures.filter(
        Q(owner=user) | Q(shared_with=user),
        is_deleted=False,
    ).exists()
    user_has_access_to_dataset = file.datasets.filter(
        Q(owner=user) | Q(shared_with=user),
        is_deleted=False,
    ).exists()
    
    return user_owns_file or user_has_access_to_capture or user_has_access_to_dataset


def get_accessible_files_queryset(user):
    """
    Get a queryset of files that the user has access to.

    A user has access to files if:
    1. They own the file directly, OR
    2. The file is part of a capture that is shared with them, OR
    3. The file is part of a dataset that is shared with them, OR
    4. The file is part of a capture that is part of a shared dataset

    Args:
        user: The user to check access for

    Returns:
        QuerySet[File]: Queryset of accessible files
    """
    captures_shared_with_user = UserSharePermission.objects.filter(
        item_type=ItemType.CAPTURE, shared_with=user, is_deleted=False, is_enabled=True
    ).values_list("item_uuid", flat=True)

    datasets_shared_with_user = UserSharePermission.objects.filter(
        item_type=ItemType.DATASET, shared_with=user, is_deleted=False, is_enabled=True
    ).values_list("item_uuid", flat=True)

    # Base queryset for non-deleted files
    base_queryset = File.objects.filter(is_deleted=False)

    # Build the access control query using Q objects
    access_query = Q()

    # 1. Files owned by the user
    access_query |= Q(owner=user)

    # 2. Files part of captures that are shared with the user
    capture_shared_query = Q(capture__isnull=False, capture__is_deleted=False) & (
        Q(capture__owner=user)  # Capture owned by user
        |
        # Capture directly shared with user
        Q(capture__uuid__in=captures_shared_with_user)
        |
        # Capture part of dataset that is shared with user
        Q(capture__dataset__isnull=False, capture__dataset__is_deleted=False)
        & (
            Q(capture__dataset__owner=user)  # Dataset owned by user
            |
            # Dataset directly shared with user
            Q(capture__dataset__uuid__in=datasets_shared_with_user)
        )
    )
    access_query |= capture_shared_query

    # 3. Files part of datasets that are shared with the user
    dataset_shared_query = Q(dataset__isnull=False, dataset__is_deleted=False) & (
        Q(dataset__owner=user)  # Dataset owned by user
        |
        # Dataset directly shared with user
        Q(dataset__uuid__in=datasets_shared_with_user)
    )
    access_query |= dataset_shared_query

    return base_queryset.filter(access_query).distinct()


def get_accessible_captures_queryset(user):
    """
    Get a queryset of captures that the user has access to.

    A user has access to captures if:
    1. They own the capture directly, OR
    2. The capture is shared with them, OR
    3. The capture is part of a dataset that is shared with them

    Args:
        user: The user to check access for

    Returns:
        QuerySet[Capture]: Queryset of accessible captures
    """
    captures_shared_with_user = UserSharePermission.objects.filter(
        item_type=ItemType.CAPTURE, shared_with=user, is_deleted=False, is_enabled=True
    ).values_list("item_uuid", flat=True)

    datasets_shared_with_user = UserSharePermission.objects.filter(
        item_type=ItemType.DATASET, shared_with=user, is_deleted=False, is_enabled=True
    ).values_list("item_uuid", flat=True)

    # Base queryset for non-deleted captures
    base_queryset = Capture.objects.filter(is_deleted=False)

    # Build the access control query using Q objects
    access_query = Q()

    # 1. Captures owned by the user
    access_query |= Q(owner=user)

    # 2. Captures directly shared with the user
    access_query |= Q(uuid__in=captures_shared_with_user)

    # 4. Captures part of datasets that are shared with the user
    dataset_shared_query = Q(dataset__isnull=False, dataset__is_deleted=False) & (
        Q(dataset__owner=user)  # Dataset owned by user
        |
        # Dataset directly shared with user
        Q(dataset__uuid__in=datasets_shared_with_user)
    )
    access_query |= dataset_shared_query

    return base_queryset.filter(access_query).distinct()
