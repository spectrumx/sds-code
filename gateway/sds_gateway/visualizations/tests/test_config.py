"""Tests for visualization configuration."""

from django.test import TestCase

from sds_gateway.api_methods.models import CaptureType
from sds_gateway.visualizations.config import VISUALIZATION_COMPATIBILITY
from sds_gateway.visualizations.config import get_all_visualization_types
from sds_gateway.visualizations.config import get_available_visualizations


class VisualizationConfigTestCases(TestCase):
    """Test cases for visualization configuration."""

    def test_visualization_compatibility_structure(self):
        """Test that visualization compatibility has the expected structure."""
        assert "waterfall" in VISUALIZATION_COMPATIBILITY
        assert "spectrogram" in VISUALIZATION_COMPATIBILITY

        # Check that supported_capture_types uses enum values
        waterfall_config = VISUALIZATION_COMPATIBILITY["waterfall"]
        assert isinstance(waterfall_config["supported_capture_types"], list)
        assert CaptureType.DigitalRF in waterfall_config["supported_capture_types"]

        spectrogram_config = VISUALIZATION_COMPATIBILITY["spectrogram"]
        assert isinstance(spectrogram_config["supported_capture_types"], list)
        assert CaptureType.DigitalRF in spectrogram_config["supported_capture_types"]

    def test_get_available_visualizations_with_drf(self):
        """Test getting available visualizations for DigitalRF capture type."""
        available = get_available_visualizations(CaptureType.DigitalRF)

        assert "waterfall" in available
        assert "spectrogram" in available

        # Check that the returned configs have the type field added
        assert available["waterfall"]["type"] == "waterfall"
        assert available["spectrogram"]["type"] == "spectrogram"

    def test_get_available_visualizations_with_other_types(self):
        """Test getting available visualizations for other capture types."""
        # RadioHound should not have any visualizations currently
        available_rh = get_available_visualizations(CaptureType.RadioHound)
        assert available_rh == {}

        # SigMF should not have any visualizations currently
        available_sigmf = get_available_visualizations(CaptureType.SigMF)
        assert available_sigmf == {}

    def test_get_all_visualization_types(self):
        """Test getting all visualization types."""
        all_types = get_all_visualization_types()

        assert "waterfall" in all_types
        assert "spectrogram" in all_types

        # Should be a copy, not the original
        assert all_types is not VISUALIZATION_COMPATIBILITY
        assert all_types == VISUALIZATION_COMPATIBILITY
