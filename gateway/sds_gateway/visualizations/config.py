"""
Visualization configuration and compatibility rules.
"""

from sds_gateway.api_methods.models import CaptureType

# Visualization compatibility configuration
VISUALIZATION_COMPATIBILITY = {
    "waterfall": {
        "supported_capture_types": [CaptureType.DigitalRF],
        "description": "View signal data as a scrolling waterfall display with periodogram",
        "icon": "bi-water",
        "color": "primary",
        "url_pattern": "/visualizations/waterfall/{capture_uuid}/",
    },
    "spectrogram": {
        "supported_capture_types": [CaptureType.DigitalRF],
        "description": "Visualize signal strength across frequency and time",
        "icon": "bi-graph-up",
        "color": "success",
        "url_pattern": "/visualizations/spectrogram/{capture_uuid}/",
    },
}


def get_available_visualizations(capture_type: CaptureType) -> dict:
    """
    Get available visualizations for a given capture type.

    Args:
        capture_type: The capture type (e.g., CaptureType.DigitalRF, CaptureType.SigMF, CaptureType.RadioHound)

    Returns:
        Dict of available visualizations with their configurations
    """
    available = {}

    for viz_type, config in VISUALIZATION_COMPATIBILITY.items():
        if capture_type in config["supported_capture_types"]:
            available[viz_type] = config.copy()
            # Add the visualization type key
            available[viz_type]["type"] = viz_type

    return available


def get_all_visualization_types() -> dict:
    """
    Get all available visualization types with their configurations.

    Returns:
        Dict of all visualization types
    """
    return VISUALIZATION_COMPATIBILITY.copy()
