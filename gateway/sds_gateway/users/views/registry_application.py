from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import DetailView
from django.views.generic import ListView

from sds_gateway.api_methods.federation.registry_application_challenge import (
    applicant_can_manage_challenge,
)
from sds_gateway.api_methods.federation.registry_application_challenge import (
    reissue_registry_challenge,
)
from sds_gateway.api_methods.federation.registry_application_challenge import (
    withdraw_registry_application,
)
from sds_gateway.api_methods.federation.registry_application_review import (
    approve_registry_application,
)
from sds_gateway.api_methods.federation.registry_application_review import (
    reject_registry_application,
)
from sds_gateway.api_methods.federation.registry_application_verify import (
    verify_registry_application,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    generate_registry_challenge_token,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import ChallengeMethod
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus
from sds_gateway.users.forms import RegistryApplicationForm
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.mixins import RegistryIntakeRequiredMixin

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest
    from django.http import HttpResponse

_REGISTRY_CHALLENGE_SESSION_PREFIX = "registry_challenge_token:"


def _challenge_session_key(application_pk: str) -> str:
    return f"{_REGISTRY_CHALLENGE_SESSION_PREFIX}{application_pk}"


def stash_challenge_token_for_display(
    request: HttpRequest, application: RegistryApplication, raw: str
) -> None:
    """Show the raw token once on the next detail page load, then discard."""
    request.session[_challenge_session_key(str(application.pk))] = raw
    request.session.modified = True


def pop_challenge_token_for_display(
    request: HttpRequest, application: RegistryApplication
) -> str | None:
    return request.session.pop(_challenge_session_key(str(application.pk)), None)


def registry_applications_for_user(user) -> QuerySet[RegistryApplication]:
    """Applicants see their own rows; staff can open any application for review."""
    base = RegistryApplication.objects.select_related("contact", "reviewed_by")
    if user.is_staff:
        return base.all()
    return base.filter(contact=user)


def get_registry_application_for_user(user, pk: str) -> RegistryApplication:
    return get_object_or_404(registry_applications_for_user(user), pk=pk)


def _submit_registry_application(
    request: HttpRequest, form: RegistryApplicationForm
) -> HttpResponse | None:
    """Create application on valid form.

    Return redirect response or None if the form was updated with errors.
    """
    if not form.is_valid():
        return None

    raw_challenge = generate_registry_challenge_token()
    try:
        application = RegistryApplication.objects.create(
            fqdn=form.cleaned_data["fqdn"],
            display_name=form.cleaned_data["display_name"],
            proposed_site_name=form.cleaned_data["proposed_site_name"],
            contact=request.user,
            contact_email=request.user.email or "",
            challenge_token_hash=hash_registry_challenge_token(raw_challenge),
            status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
            challenge_method=ChallengeMethod.WELL_KNOWN_JSON.value,
        )
    except IntegrityError:
        form.add_error(
            "fqdn",
            "An active registry application already exists for this FQDN.",
        )
        return None

    stash_challenge_token_for_display(request, application, raw_challenge)
    messages.success(
        request,
        (
            "Application created. Copy your verification token on the next screen—"
            "it is shown only once."
        ),
    )
    return redirect("users:registry_application_detail", pk=application.pk)


class RegistryApplicationView(
    RegistryIntakeRequiredMixin, Auth0LoginRequiredMixin, View
):
    """Legacy apply URL: opens the create modal on the list page."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return redirect(f"{reverse('users:registry_application_list')}?new=1")

    def post(self, request: HttpRequest) -> HttpResponse:
        form = RegistryApplicationForm(request.POST)
        response = _submit_registry_application(request, form)
        if response is not None:
            return response
        list_view = RegistryApplicationListView()
        list_view.setup(request)
        list_view.object_list = list_view.get_queryset()
        context = list_view.get_context_data(form=form, open_apply_modal=True)
        return list_view.render_to_response(context)


class RegistryApplicationDetailView(
    RegistryIntakeRequiredMixin, Auth0LoginRequiredMixin, DetailView
):
    """Application status and one-time challenge token display."""

    model = RegistryApplication
    template_name = "users/registry_application_detail.html"
    context_object_name = "application"

    def get_queryset(self) -> QuerySet[RegistryApplication]:
        return registry_applications_for_user(self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        application = self.object
        assert application is not None
        context["challenge_token_once"] = pop_challenge_token_for_display(
            self.request,
            application,
        )
        context["well_known_url"] = (
            f"https://{application.fqdn}/.well-known/sds-federation.json"
        )
        context["challenge_expired"] = (
            applicant_can_manage_challenge(application)
            and application.challenge_expires_at <= timezone.now()
        )
        context["can_applicant_manage"] = (
            application.contact_id == self.request.user.pk
            and applicant_can_manage_challenge(application)
        )
        context["can_verify_domain"] = context["can_applicant_manage"]
        context["can_staff_review"] = (
            self.request.user.is_staff
            and application.status == RegistryApplicationStatus.PENDING_APPROVAL.value
        )
        context["is_staff_viewer"] = self.request.user.is_staff
        return context


class RegistryApplicationReissueChallengeView(
    RegistryIntakeRequiredMixin, Auth0LoginRequiredMixin, View
):
    """Applicant: issue a new verification token for this application."""

    def post(self, request: HttpRequest, pk: str) -> HttpResponse:
        application = get_registry_application_for_user(request.user, pk)
        if application.contact_id != request.user.id:
            messages.error(request, "Only the applicant can request a new challenge.")
            return redirect("users:registry_application_detail", pk=application.pk)
        result = reissue_registry_challenge(application)
        if result.ok and result.raw_token:
            stash_challenge_token_for_display(request, application, result.raw_token)
            messages.success(request, result.message)
        elif result.ok:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)
        return redirect("users:registry_application_detail", pk=application.pk)


class RegistryApplicationWithdrawView(
    RegistryIntakeRequiredMixin, Auth0LoginRequiredMixin, View
):
    """Applicant: withdraw and release the FQDN for a new application."""

    def post(self, request: HttpRequest, pk: str) -> HttpResponse:
        application = get_registry_application_for_user(request.user, pk)
        if application.contact_id != request.user.id:
            messages.error(request, "Only the applicant can withdraw this application.")
            return redirect("users:registry_application_detail", pk=application.pk)
        result = withdraw_registry_application(application)
        if result.ok:
            messages.success(request, result.message)
            return redirect("users:registry_application_list")
        messages.error(request, result.message)
        return redirect("users:registry_application_detail", pk=application.pk)


class RegistryApplicationVerifyView(
    RegistryIntakeRequiredMixin, Auth0LoginRequiredMixin, View
):
    """Run domain verification for the applicant's well-known endpoint."""

    def post(self, request: HttpRequest, pk: str) -> HttpResponse:
        application = get_registry_application_for_user(request.user, pk)
        if application.contact_id != request.user.id:
            messages.error(request, "Only the applicant can run domain verification.")
            return redirect("users:registry_application_detail", pk=application.pk)
        result = verify_registry_application(application)
        if result.ok:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)
        return redirect("users:registry_application_detail", pk=application.pk)


class RegistryApplicationListView(
    RegistryIntakeRequiredMixin, Auth0LoginRequiredMixin, ListView
):
    """List the current user's federation registry applications."""

    model = RegistryApplication
    template_name = "users/registry_application_list.html"
    context_object_name = "applications"
    form_class = RegistryApplicationForm

    def get_queryset(self) -> QuerySet[RegistryApplication]:
        return registry_applications_for_user(self.request.user).order_by("-updated_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form", self.form_class())
        context["open_apply_modal"] = kwargs.get(
            "open_apply_modal",
            self.request.GET.get("new") == "1",
        )
        return context

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = self.form_class(request.POST)
        response = _submit_registry_application(request, form)
        if response is not None:
            return response
        self.object_list = self.get_queryset()
        context = self.get_context_data(form=form, open_apply_modal=True)
        return self.render_to_response(context)


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self) -> bool:
        return self.request.user.is_staff


class RegistryApplicationApproveView(
    RegistryIntakeRequiredMixin,
    Auth0LoginRequiredMixin,
    StaffRequiredMixin,
    View,
):
    """Staff: approve a verified application (sets site_name and approved status)."""

    def post(self, request: HttpRequest, pk: str) -> HttpResponse:
        application = get_registry_application_for_user(request.user, pk)
        site_name = (request.POST.get("site_name") or "").strip() or None
        result = approve_registry_application(
            application,
            request.user,
            site_name=site_name,
        )
        if result.ok:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)
        return redirect("users:registry_application_detail", pk=application.pk)


class RegistryApplicationRejectView(
    RegistryIntakeRequiredMixin,
    Auth0LoginRequiredMixin,
    StaffRequiredMixin,
    View,
):
    """Staff: reject an application awaiting approval."""

    def post(self, request: HttpRequest, pk: str) -> HttpResponse:
        application = get_registry_application_for_user(request.user, pk)
        reason = (request.POST.get("rejected_reason") or "").strip()
        result = reject_registry_application(
            application,
            request.user,
            reason=reason,
        )
        if result.ok:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)
        return redirect("users:registry_application_detail", pk=application.pk)


registry_application_list_view = RegistryApplicationListView.as_view()
registry_application_view = RegistryApplicationView.as_view()
registry_application_detail_view = RegistryApplicationDetailView.as_view()
registry_application_reissue_challenge_view = require_POST(
    RegistryApplicationReissueChallengeView.as_view(),
)
registry_application_withdraw_view = require_POST(
    RegistryApplicationWithdrawView.as_view(),
)
registry_application_verify_view = require_POST(
    RegistryApplicationVerifyView.as_view(),
)
registry_application_approve_view = require_POST(
    RegistryApplicationApproveView.as_view(),
)
registry_application_reject_view = require_POST(
    RegistryApplicationRejectView.as_view(),
)
