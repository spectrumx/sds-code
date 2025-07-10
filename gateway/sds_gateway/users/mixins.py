from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models import QuerySet
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import File
from sds_gateway.users.models import User
from sds_gateway.users.utils import deduplicate_composite_captures
from sds_gateway.users.utils import serialize_composite_capture_for_display

# Constants
MIN_SEARCH_QUERY_LENGTH = 2


class ApprovedUserRequiredMixin(AccessMixin):
    """Verify that the current user is approved."""

    def dispatch(self, request, *args, **kwargs) -> HttpResponseRedirect:
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_approved:
            messages.error(
                request=request,
                message=_(
                    "Your account is not approved to use API features. "
                    "Please contact the administrator.",
                ),
            )
            return redirect(reverse("home"))
        return super().dispatch(request, *args, **kwargs)


class Auth0LoginRequiredMixin(LoginRequiredMixin):
    """Custom mixin that redirects to Auth0 login instead of the default login page"""

    def get_login_url(self) -> str:
        return reverse("auth0_login")


class UserSearchMixin:
    """Mixin to handle user search functionality for sharing."""

    def search_users(self, request) -> JsonResponse:
        """Search for users by name or email."""
        query = request.GET.get("q", "").strip()
        limit = min(int(request.GET.get("limit", 10)), 20)  # Max 20 results

        if not query or len(query) < MIN_SEARCH_QUERY_LENGTH:
            return JsonResponse(
                {"error": "Search query must be at least 2 characters long"}, status=400
            )

        # Search for users by name or email, excluding the current user
        users = User.objects.filter(
            Q(name__icontains=query) | Q(email__icontains=query),
            is_approved=True,  # Only show approved users
        ).exclude(id=request.user.id)[:limit]

        # Serialize users for response
        users_data = [
            {
                "name": user.name,
                "email": user.email,
            }
            for user in users
        ]

        return JsonResponse(users_data, safe=False)


class FormSearchMixin:
    """Mixin for search form in group captures view"""

    def search_captures(self, search_data, request) -> list[Capture]:
        queryset = Capture.objects.filter(
            owner=request.user,
            is_deleted=False,
        )

        # Build a Q object for complex queries
        q_objects = Q()

        if search_data.get("directory"):
            q_objects &= Q(top_level_dir__icontains=search_data["directory"])
        if search_data.get("capture_type"):
            q_objects &= Q(capture_type=search_data["capture_type"])
        if search_data.get("scan_group"):
            q_objects &= Q(scan_group__icontains=search_data["scan_group"])
        if search_data.get("channel"):
            q_objects &= Q(channel__icontains=search_data["channel"])

        queryset = queryset.filter(q_objects).order_by("-created_at")

        # Use utility function to deduplicate composite captures
        return deduplicate_composite_captures(list(queryset))

    def search_files(
        self, search_data: dict[str, Any], request
    ) -> QuerySet[File, File]:
        # Only show files that are not associated with a capture
        queryset = File.objects.filter(
            owner=request.user,
            capture__isnull=True,
            is_deleted=False,
        )

        if search_data.get("file_name"):
            queryset = queryset.filter(Q(name__icontains=search_data["file_name"]))
        if search_data.get("directory"):
            queryset = queryset.filter(Q(directory__icontains=search_data["directory"]))
        if search_data.get("file_extension"):
            queryset = queryset.filter(Q(name__endswith=search_data["file_extension"]))

        return queryset.order_by("-created_at")

    def serialize_item(
        self,
        item: Capture | File,
        relative_path: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(item, Capture):
            # Use utility function for consistent composite capture serialization
            return serialize_composite_capture_for_display(item)
        if isinstance(item, File):
            return {
                "id": item.uuid,
                "name": item.name,
                "media_type": item.media_type,
                "size": item.size,
                "relative_path": relative_path,
            }

        # this should never happen
        return {}

    def get_paginated_response(
        self, queryset, request, page_size=10, page_param="page"
    ) -> dict[str, Any]:
        paginator = Paginator(queryset, page_size)
        page = paginator.get_page(request.GET.get(page_param, 1))

        return {
            "results": [self.serialize_item(item) for item in page],
            "pagination": {
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
                "number": page.number,
                "num_pages": paginator.num_pages,
            },
        }
