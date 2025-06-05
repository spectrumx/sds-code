from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import File


class ApprovedUserRequiredMixin(AccessMixin):
    """Verify that the current user is approved."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_approved:
            messages.error(
                request,
                _(
                    "Your account is not approved to use API features. Please contact the administrator.",  # noqa: E501
                ),
            )
            return redirect(reverse("home"))
        return super().dispatch(request, *args, **kwargs)


class Auth0LoginRequiredMixin(LoginRequiredMixin):
    """Custom mixin that redirects to Auth0 login instead of the default login page"""

    def get_login_url(self):
        return reverse("auth0_login")


class FormSearchMixin:
    """Mixin for search form in group captures view"""

    def search_captures(self, search_data):
        queryset = Capture.objects.filter(owner=self.request.user)

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

        return queryset.filter(q_objects).order_by("-created_at")

    def search_files(self, search_data):
        # Only show files that are not associated with a capture
        queryset = File.objects.filter(
            owner=self.request.user,
            capture__isnull=True,
        )

        if search_data.get("file_name"):
            queryset = queryset.filter(Q(name__icontains=search_data["file_name"]))
        if search_data.get("directory"):
            queryset = queryset.filter(Q(directory__icontains=search_data["directory"]))
        if search_data.get("file_extension"):
            queryset = queryset.filter(Q(name__endswith=search_data["file_extension"]))

        return queryset.order_by("-created_at")

    def serialize_item(self, item):
        if isinstance(item, Capture):
            return {
                "id": item.uuid,
                "capture_type": item.capture_type,
                "top_level_dir": item.top_level_dir,
                "channel": item.channel,
                "scan_group": item.scan_group,
                "created_at": item.created_at.isoformat(),
            }
        if isinstance(item, File):
            return {
                "id": item.uuid,
                "name": item.name,
                "media_type": item.media_type,
                "size": item.size,
                "created_at": item.created_at.isoformat(),
            }
        return {}

    def get_paginated_response(self, queryset, page_size=10, page_param="page"):
        paginator = Paginator(queryset, page_size)
        page = paginator.get_page(self.request.GET.get(page_param, 1))

        return {
            "results": [self.serialize_item(item) for item in page],
            "pagination": {
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
                "number": page.number,
                "num_pages": paginator.num_pages,
            },
        }
