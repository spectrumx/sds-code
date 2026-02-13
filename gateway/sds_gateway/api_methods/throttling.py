"""Throttle classes for expensive API endpoints."""

from rest_framework.throttling import UserRateThrottle


class VisStreamThrottle(UserRateThrottle):
    """
    Rate limit for visualization streaming endpoints (e.g. waterfall_slices_stream).
    Uses scope 'vis_stream' from REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].
    """

    scope = "vis_stream"
