from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


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
