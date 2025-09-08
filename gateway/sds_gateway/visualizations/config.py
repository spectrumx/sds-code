"""
Visualization configuration and compatibility rules.
"""

from django.conf import settings


def get_visualization_compatibility():
    """
    Get visualization compatibility configuration.

    Returns:
        Dict of visualization compatibility rules
    """
    # Lazy import to avoid circular import issues
    from sds_gateway.api_methods.models import CaptureType

    compatibility = {
        "waterfall": {
            "supported_capture_types": [CaptureType.DigitalRF.value],
            "description": (
                "View signal data as a scrolling waterfall display with periodogram"
            ),
            "icon": "bi-water",
            "color": "primary",
            "url_pattern": "/visualizations/waterfall/{capture_uuid}/",
        },
    }

    # Add spectrogram only if experimental feature is enabled
    if settings.EXPERIMENTAL_SPECTROGRAM:
        compatibility["spectrogram"] = {
            "supported_capture_types": [CaptureType.DigitalRF.value],
            "description": "Visualize signal strength across frequency and time",
            "icon": "bi-graph-up",
            "color": "success",
            "url_pattern": "/visualizations/spectrogram/{capture_uuid}/",
        }

    return compatibility


def get_available_visualizations(capture_type: str) -> dict:
    """
    Get available visualizations for a given capture type.

    Args:
        capture_type: The capture type

    Returns:
        Dict of available visualizations with their configurations
    """
    available = {}
    compatibility = get_visualization_compatibility()

    for viz_type, config in compatibility.items():
        if capture_type in config["supported_capture_types"]:
            available[viz_type] = config.copy()
            # Add the visualization type key
            available[viz_type]["type"] = viz_type

    return available
