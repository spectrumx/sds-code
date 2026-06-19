"""DRF permissions for API key scoping."""

from rest_framework.permissions import BasePermission

from sds_gateway.api_methods.models import KeySources
from sds_gateway.users.models import UserAPIKey


class IsFederationSyncKey(BasePermission):
    """Allow only federation sync service API keys."""

    message = "Federation sync API key required."

    def has_permission(self, request, view) -> bool:
        key = request.auth
        return isinstance(key, UserAPIKey) and key.source == KeySources.FederationSync


class DisallowFederationSyncKey(BasePermission):
    """Block federation sync keys from non-federation API routes.

    Applied globally via REST_FRAMEWORK DEFAULT_PERMISSION_CLASSES.
    """

    message = "This API key is restricted to federation export endpoints."

    def has_permission(self, request, view) -> bool:
        key = request.auth
        return not (
            isinstance(key, UserAPIKey) and key.source == KeySources.FederationSync
        )
