from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from sds_gateway.api_methods.models import Capture

from .api_views import Colormap
from .api_views import SpectrogramProcessingParams


@dataclass(frozen=True)
class SpectrogramFormContext:
    """Server-provided spectrogram form values for the template."""

    fft_size_options: tuple[int, ...]
    color_map_options: tuple[str, ...]
    default_fft_size: int
    default_std_dev: int
    default_hop_size: int
    default_color_map: str
    std_dev_min: int
    std_dev_max: int
    hop_size_min: int
    hop_size_max: int

    @classmethod
    def build(cls) -> "SpectrogramFormContext":
        return cls(
            fft_size_options=SpectrogramProcessingParams.get_fft_size_options(),
            color_map_options=tuple(colormap.value for colormap in Colormap),
            default_fft_size=SpectrogramProcessingParams.DEFAULT_FFT_SIZE,
            default_std_dev=SpectrogramProcessingParams.DEFAULT_STD_DEV,
            default_hop_size=SpectrogramProcessingParams.DEFAULT_HOP_SIZE,
            default_color_map=SpectrogramProcessingParams.DEFAULT_COLORMAP,
            std_dev_min=SpectrogramProcessingParams.MIN_STD_DEV,
            std_dev_max=SpectrogramProcessingParams.MAX_STD_DEV,
            hop_size_min=SpectrogramProcessingParams.MIN_HOP_SIZE,
            hop_size_max=SpectrogramProcessingParams.MAX_HOP_SIZE,
        )


SPECTROGRAM_FORM_CONTEXT = SpectrogramFormContext.build()


@method_decorator(login_required, name="dispatch")
class WaterfallVisualizationView(LoginRequiredMixin, TemplateView):
    """View for displaying waterfall visualization of a capture."""

    template_name = "visualizations/waterfall.html"

    def get_context_data(self, **kwargs):
        """Get context data for the waterfall visualization."""
        context = super().get_context_data(**kwargs)

        # Get the capture from the URL parameter
        capture_uuid = self.kwargs.get("capture_uuid")
        # TODO: Allow visualization of shared captures
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
        # TODO: Allow visualization of shared captures
        capture = get_object_or_404(
            Capture, uuid=capture_uuid, owner=self.request.user, is_deleted=False
        )

        context["capture"] = capture
        context["spectrogram_form"] = SPECTROGRAM_FORM_CONTEXT
        return context
