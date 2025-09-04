"""Capture access utility functions for the SDS Gateway API."""

from sds_gateway.api_methods.models import Capture, ItemType, user_has_access_to_item, File


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
    # Check if user owns the capture directly
    if capture.owner == user:
        return True
    
    # Check if capture is directly shared with the user
    if user_has_access_to_item(user, capture.uuid, ItemType.CAPTURE):
        return True
    
    # Check if capture is part of a dataset that is shared with the user
    if capture.dataset:
        if user_has_access_to_item(user, capture.dataset.uuid, ItemType.DATASET):
            return True
    
    return False


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
    # Check if user owns the file directly
    if file.owner == user:
        return True
    
    # Check if file is part of a capture that is shared with the user
    if file.capture:
        if user_has_access_to_capture(user, file.capture):
            return True
    
    # Check if file is part of a dataset that is shared with them
    if file.dataset:
        if user_has_access_to_item(user, file.dataset.uuid, ItemType.DATASET):
            return True
    
    return False