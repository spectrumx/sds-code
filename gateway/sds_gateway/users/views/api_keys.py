import datetime
from typing import Any
from uuid import UUID

from django.contrib import messages
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.views import View

from sds_gateway.api_methods.models import KeySources
from sds_gateway.users.mixins import ApprovedUserRequiredMixin
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.models import UserAPIKey

# Constants
MAX_API_KEY_COUNT = 10


def get_active_api_key_count(api_keys) -> int:
    """
    Calculate the number of active (non-revoked and non-expired) API keys.

    Args:
        api_keys: QuerySet of UserAPIKey objects

    Returns:
        int: Number of active API keys
    """
    now = datetime.datetime.now(datetime.UTC)
    return sum(
        1
        for key in api_keys
        if not key.revoked and (not key.expiry_date or key.expiry_date >= now)
    )


def validate_uuid(uuid_string: str) -> bool:
    """Validate if a string is a valid UUID."""
    try:
        UUID(uuid_string)
    except (ValueError, TypeError):
        return False
    else:
        return True


class GenerateAPIKeyView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    template_name = "users/user_api_key.html"

    def get(self, request, *args, **kwargs):
        # Get all API keys for the user (except SVIBackend)
        api_keys = (
            UserAPIKey.objects.filter(user=request.user)
            .exclude(source=KeySources.SVIBackend)
            .order_by("revoked", "-created")
        )  # Active keys first, then by creation date (recent first)
        now = datetime.datetime.now(datetime.UTC)
        active_api_key_count = get_active_api_key_count(api_keys)
        context = {
            "api_key": False,
            "expires_at": None,
            "expired": False,
            "current_api_keys": api_keys,
            "now": now,
            "active_api_key_count": active_api_key_count,
        }
        if not api_keys.exists():
            return render(
                request,
                template_name=self.template_name,
                context=context,
            )

        context.update(
            {
                "api_key": True,  # return True if API key exists
                "current_api_keys": api_keys,
                "now": now,
                "active_api_key_count": active_api_key_count,
            }
        )
        return render(
            request,
            template_name=self.template_name,
            context=context,
        )

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """
        Creates a new API key for the authenticated user without deleting existing keys.
        Enforces the maximum API key count (MAX_API_KEY_COUNT) per user.
        """
        # Check if user has reached the maximum number of active API keys
        api_keys = UserAPIKey.objects.filter(user=request.user).exclude(
            source=KeySources.SVIBackend
        )
        active_api_key_count = get_active_api_key_count(api_keys)
        if active_api_key_count >= MAX_API_KEY_COUNT:
            messages.error(
                request,
                f"You have reached the maximum number of API keys "
                f"({MAX_API_KEY_COUNT}). Please revoke an existing key "
                "before creating a new one.",
            )
            return redirect("users:view_api_key")

        # Get the name and description from the form
        api_key_name = request.POST.get("api_key_name", "")
        api_key_description = request.POST.get("api_key_description", "")
        api_key_expiry_date_str = request.POST.get("api_key_expiry_date", "")

        expiry_date = None
        if api_key_expiry_date_str:
            try:
                expiry_date = datetime.datetime.strptime(
                    api_key_expiry_date_str, "%Y-%m-%d"
                ).replace(tzinfo=datetime.UTC)
            except ValueError:
                messages.error(request, "Invalid expiration date format.")
                return redirect("users:view_api_key")

        # create an API key for the user
        _, raw_key = UserAPIKey.objects.create_key(
            name=api_key_name,
            description=api_key_description,
            user=request.user,
            source=KeySources.SDSWebUI,
            expiry_date=expiry_date,
        )
        request.session["new_api_key"] = raw_key
        return redirect("users:new_api_key")


user_api_key_view = GenerateAPIKeyView.as_view()


class NewAPIKeyView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    template_name = "users/new_api_key.html"

    def get(self, request, *args, **kwargs):
        api_key = request.session.pop("new_api_key", None)
        return render(request, self.template_name, {"api_key": api_key})


new_api_key_view = NewAPIKeyView.as_view()


class RevokeAPIKeyView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        key_id = request.POST.get("key_id")
        api_key = get_object_or_404(UserAPIKey, id=key_id, user=request.user)
        if not api_key.revoked:
            api_key.revoked = True
            api_key.save()
            messages.success(request, "API key revoked successfully.")
        else:
            messages.info(request, "API key is already revoked.")
        return redirect("users:view_api_key")


revoke_api_key_view = RevokeAPIKeyView.as_view()


class GenerateAPIKeyFormView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    template_name = "users/generate_api_key_form.html"

    def get(self, request, *args, **kwargs):
        api_keys = UserAPIKey.objects.filter(user=request.user).exclude(
            source=KeySources.SVIBackend
        )
        active_api_key_count = get_active_api_key_count(api_keys)
        is_allowed_to_generate_key = active_api_key_count < MAX_API_KEY_COUNT
        context = {
            "is_allowed_to_generate_key": is_allowed_to_generate_key,
        }
        return render(request, self.template_name, context)


generate_api_key_form_view = GenerateAPIKeyFormView.as_view()
