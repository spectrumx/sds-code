"""Permissions specific to federation export endpoints."""

from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission

from sds_gateway.api_methods.federation.availability import (
    is_client_ip_allowed_for_federation_export,
)
from sds_gateway.api_methods.federation.availability import is_federation_operational


class FederationNotOperational(APIException):
    status_code = 503
    default_detail = "Federation is not configured or the sync service is unavailable."
    default_code = "federation_unavailable"


class IsFederationOperational(BasePermission):
    """Deny export when federation failed startup / health checks."""

    message = FederationNotOperational.default_detail

    def has_permission(self, request, view) -> bool:
        if not is_federation_operational():
            detail = getattr(settings, "FEDERATION_OPERATIONAL_REASON", "") or (
                FederationNotOperational.default_detail
            )
            raise FederationNotOperational(detail=detail)
        return True


class IsFederationInternalExportClient(BasePermission):
    """Restrict export to internal network clients (sync service on sds-network)."""

    message = "Federation export is only available to internal clients."

    def has_permission(self, request, view) -> bool:
        return is_client_ip_allowed_for_federation_export(request)
