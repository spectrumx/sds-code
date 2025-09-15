"""Spectrogram processing logic for visualizations."""

import tempfile
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from loguru import logger
from scipy.signal import ShortTimeFFT
from scipy.signal.windows import gaussian

from .utils import validate_digitalrf_data


def _generate_spectrogram_plot(
    spectrogram, extent, center_freq, channel, colormap, dimensions
):
    """Generate the matplotlib plot for the spectrogram."""
    # Create figure with requested dimensions or default
    if dimensions and "width" in dimensions and "height" in dimensions:
        # Convert pixels to inches (assuming 100 DPI for conversion)
        width_inches = dimensions["width"] / 100.0
        height_inches = dimensions["height"] / 100.0
        logger.info(
            f"Using requested dimensions: "
            f"{dimensions['width']}x{dimensions['height']} pixels"
            f"({width_inches:.1f}x{height_inches:.1f} inches)"
        )
    else:
        # Use default dimensions
        width_inches = 10.0
        height_inches = 6.0
        logger.info(
            f"Using default dimensions: {width_inches:.1f}x{height_inches:.1f} inches"
        )

    figure, axes = plt.subplots(figsize=(width_inches, height_inches))

    # Set title
    title = f"Spectrogram - Channel {channel}"
    if center_freq != 0:
        title += f" (Center: {center_freq / 1e6:.2f} MHz)"
    axes.set_title(title, fontsize=14)

    # Set axis labels
    axes.set_xlabel("Time (s)", fontsize=12)
    axes.set_ylabel("Frequency (Hz)", fontsize=12)

    # Plot spectrogram
    spectrogram_db = 10 * np.log10(np.fmax(spectrogram, 1e-12))
    image = axes.imshow(
        spectrogram_db,
        origin="lower",
        aspect="auto",
        extent=extent,
        cmap=colormap,
    )

    # Add colorbar
    figure.colorbar(
        image,
        label="Power Spectral Density (dB)",
    )

    # Adjust layout
    figure.tight_layout()

    return figure


def generate_spectrogram_from_drf(
    drf_path: Path, channel: str, processing_parameters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Generate a spectrogram from DigitalRF data.

    Args:
        drf_path: Path to the DigitalRF directory
        channel: Channel name to process
        processing_parameters: Dict containing spectrogram parameters
            (fft_size, std_dev, hop_size, colormap)

    Returns:
        Dict with status and spectrogram data
    """
    logger.info(f"Generating spectrogram from DigitalRF data for channel {channel}")

    # Spectrogram parameters - use passed parameters or defaults
    if processing_parameters is None:
        processing_parameters = {}

    fft_size = processing_parameters.get("fft_size", 1024)
    std_dev = processing_parameters.get("std_dev", 100)
    hop_size = processing_parameters.get("hop_size", 500)
    colormap = processing_parameters.get("colormap", "magma")
    dimensions = processing_parameters.get("dimensions", {})

    # Validate DigitalRF data and get validated parameters
    params = validate_digitalrf_data(drf_path, channel, fft_size)

    # Extract values from validated parameters
    reader = params.reader
    start_sample = params.start_sample
    total_samples = params.total_samples
    sample_rate = params.sample_rate
    center_freq = params.center_freq

    logger.info(
        f"Using spectrogram parameters: fft_size={params.fft_size}, "
        f"std_dev={std_dev}, hop_size={hop_size}, colormap={colormap}, "
        f"dimensions={dimensions}"
    )

    # Generate spectrogram using matplotlib
    try:
        mpl.use("Agg")  # Use non-interactive backend
    except ImportError as e:
        error_msg = f"Required libraries for spectrogram generation not available: {e}"
        logger.error(error_msg)
        raise

    data_array = reader.read_vector(start_sample, total_samples, channel, 0)

    # Create Gaussian window
    gaussian_window = gaussian(params.fft_size, std=std_dev, sym=True)

    # Create ShortTimeFFT object
    short_time_fft = ShortTimeFFT(
        gaussian_window,
        hop=hop_size,
        fs=sample_rate,
        mfft=params.fft_size,
        fft_mode="centered",
    )

    # Generate spectrogram
    spectrogram = short_time_fft.spectrogram(data_array)

    extent = short_time_fft.extent(total_samples)

    # Generate the spectrogram plot
    figure = _generate_spectrogram_plot(
        spectrogram, extent, center_freq, channel, colormap, dimensions
    )

    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
        figure.savefig(tmp_file.name, dpi=150, bbox_inches="tight")
        image_path = tmp_file.name

    # Clean up matplotlib figure
    plt.close(figure)

    # Create metadata
    metadata = {
        "center_frequency": params.center_freq,
        "sample_rate": params.sample_rate,
        "min_frequency": params.min_frequency,
        "max_frequency": params.max_frequency,
        "total_samples": params.total_samples,
        "samples_processed": params.total_samples,
        "fft_size": params.fft_size,
        "window_std_dev": std_dev,
        "hop_size": hop_size,
        "colormap": colormap,
        "dimensions": dimensions,
        "channel": params.channel,
    }

    return {
        "status": "success",
        "message": "Spectrogram generated successfully",
        "image_path": image_path,
        "metadata": metadata,
    }
