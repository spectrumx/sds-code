from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models import QuerySet
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)


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

        # Only show one composite per top_level_dir, and all single captures
        seen_top_level_dirs = set()
        unique_captures = []
        composite_groups: dict[
            str, list[Capture]
        ] = {}  # Track all captures in each composite group

        # First pass: group composite captures by top_level_dir
        for capture in queryset:
            if capture.is_multi_channel:
                if capture.top_level_dir not in composite_groups:
                    composite_groups[capture.top_level_dir] = []
                composite_groups[capture.top_level_dir].append(capture)
            else:
                unique_captures.append(capture)

        # Second pass: for each composite group,
        # add only the base capture (first by created_at)
        for top_level_dir, captures in composite_groups.items():
            if top_level_dir not in seen_top_level_dirs:
                # Sort by created_at to get the base capture (first one)
                base_capture = sorted(captures, key=lambda c: c.created_at)[0]
                unique_captures.append(base_capture)
                seen_top_level_dirs.add(top_level_dir)

        return unique_captures

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
            # Use composite capture serialization to get proper details
            serialized_data = serialize_capture_or_composite(item)

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
                }
            # This is a single capture
            return {
                "id": serialized_data["uuid"],
                "type": serialized_data["capture_type_display"],
                "directory": serialized_data["top_level_dir"].split("/")[-1],
                "channel": serialized_data.get("channel", "") or "-",
                "scan_group": serialized_data.get("scan_group", "") or "-",
                "created_at": serialized_data["created_at"],
            }
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
