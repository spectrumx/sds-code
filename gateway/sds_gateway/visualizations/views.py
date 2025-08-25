from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from sds_gateway.api_methods.models import Capture


@method_decorator(login_required, name="dispatch")
class WaterfallVisualizationView(LoginRequiredMixin, TemplateView):
    """View for displaying waterfall visualization of a capture."""

    template_name = "visualizations/waterfall.html"

    def get_context_data(self, **kwargs):
        """Get context data for the waterfall visualization."""
        context = super().get_context_data(**kwargs)

        # Get the capture from the URL parameter
        capture_uuid = self.kwargs.get("capture_uuid")
        capture = get_object_or_404(
            Capture, uuid=capture_uuid, owner=self.request.user, is_deleted=False
        )

        context["capture"] = capture
        return context


@method_decorator(login_required, name="dispatch")
class SpectrogramVisualizationView(LoginRequiredMixin, TemplateView):
    """View for displaying spectrogram visualization of a capture."""

    template_name = "visualizations/spectrogram.html"

    def get_context_data(self, **kwargs):
        """Get context data for the spectrogram visualization."""
        context = super().get_context_data(**kwargs)

        # Get the capture from the URL parameter
        capture_uuid = self.kwargs.get("capture_uuid")
        capture = get_object_or_404(
            Capture, uuid=capture_uuid, owner=self.request.user, is_deleted=False
        )

        context["capture"] = capture
        return context
