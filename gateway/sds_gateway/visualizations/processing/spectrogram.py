"""Spectrogram processing logic for visualizations."""

import tempfile
from pathlib import Path

import h5py
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from digital_rf import DigitalRFReader
from loguru import logger
from scipy.signal import ShortTimeFFT
from scipy.signal.windows import gaussian


def generate_spectrogram_from_drf(
    drf_path: Path, channel: str, processing_type: str
) -> dict:
    """Generate a spectrogram from DigitalRF data.

    Args:
        drf_path: Path to the DigitalRF directory
        channel: Channel name to process
        processing_type: Type of processing (spectrogram)

    Returns:
        Dict with status and spectrogram data
    """
    logger.info(f"Generating spectrogram from DigitalRF data for channel {channel}")

    try:
        # Initialize DigitalRF reader
        reader = DigitalRFReader(str(drf_path))
        channels = reader.get_channels()

        if not channels:
            error_msg = "No channels found in DigitalRF data"
            raise ValueError(error_msg)  # noqa: TRY301

        if channel not in channels:
            error_msg = (
                f"Channel {channel} not found in DigitalRF data. "
                f"Available channels: {channels}"
            )
            raise ValueError(error_msg)  # noqa: TRY301

        # Get sample bounds
        bounds = reader.get_bounds(channel)
        if bounds is None:
            error_msg = "Could not get sample bounds for channel"
            raise ValueError(error_msg)  # noqa: TRY301

        start_sample, end_sample = bounds
        if start_sample is None or end_sample is None:
            error_msg = "Invalid sample bounds for channel"
            raise ValueError(error_msg)  # noqa: TRY301
        total_samples = end_sample - start_sample

        # Get metadata from DigitalRF properties
        drf_props_path = drf_path / channel / "drf_properties.h5"
        with h5py.File(drf_props_path, "r") as f:
            sample_rate_numerator = f.attrs.get("sample_rate_numerator")
            sample_rate_denominator = f.attrs.get("sample_rate_denominator")
            if sample_rate_numerator is None or sample_rate_denominator is None:
                error_msg = "Sample rate information missing from DigitalRF properties"
                raise ValueError(error_msg)  # noqa: TRY301
            sample_rate = float(sample_rate_numerator) / float(sample_rate_denominator)

        # Get center frequency from metadata
        center_freq = 0.0
        try:
            # Try to get center frequency from metadata
            metadata_dict = reader.read_metadata(
                start_sample, min(1000, end_sample - start_sample), channel
            )
            if metadata_dict and "center_freq" in metadata_dict:
                center_freq = float(metadata_dict["center_freq"])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not read center frequency from metadata: {e}")

        # Calculate frequency range
        freq_span = sample_rate
        min_frequency = center_freq - freq_span / 2
        max_frequency = center_freq + freq_span / 2

        # Spectrogram parameters
        fft_size = 1024  # Default FFT size
        std_dev = 100  # Default window standard deviation
        hop_size = 500  # Default hop size
        colormap = "magma"  # Default colormap

        # Generate spectrogram using matplotlib
        try:
            mpl.use("Agg")  # Use non-interactive backend
        except ImportError as e:
            error_msg = (
                f"Required libraries for spectrogram generation not available: {e}"
            )
            raise

        # Read a subset of data for spectrogram generation
        # Limit to first 100k samples to avoid memory issues
        max_samples_for_spectrogram = min(total_samples, 100000)
        data_array = reader.read_vector(
            start_sample, max_samples_for_spectrogram, channel, 0
        )

        # Create Gaussian window
        gaussian_window = gaussian(fft_size, std=std_dev, sym=True)

        # Create ShortTimeFFT object
        short_time_fft = ShortTimeFFT(
            gaussian_window,
            hop=hop_size,
            fs=sample_rate,
            mfft=fft_size,
            fft_mode="centered",
        )

        # Generate spectrogram
        spectrogram = short_time_fft.spectrogram(data_array)

        # Create the spectrogram figure
        extent = short_time_fft.extent(max_samples_for_spectrogram)
        time_min, time_max = extent[:2]

        # Create figure
        figure, axes = plt.subplots(figsize=(10, 6))

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

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            figure.savefig(tmp_file.name, dpi=150, bbox_inches="tight")
            image_path = tmp_file.name

        # Clean up matplotlib figure
        plt.close(figure)

        # Create metadata
        metadata = {
            "center_frequency": center_freq,
            "sample_rate": sample_rate,
            "min_frequency": min_frequency,
            "max_frequency": max_frequency,
            "total_samples": total_samples,
            "samples_processed": max_samples_for_spectrogram,
            "fft_size": fft_size,
            "window_std_dev": std_dev,
            "hop_size": hop_size,
            "colormap": colormap,
            "channel": channel,
            "processing_parameters": {
                "fft_size": fft_size,
                "std_dev": std_dev,
                "hop_size": hop_size,
                "colormap": colormap,
            },
        }

        return {  # noqa: TRY300
            "status": "success",
            "message": "Spectrogram generated successfully",
            "image_path": image_path,
            "metadata": metadata,
        }

    except Exception as e:
        logger.exception(f"Error generating spectrogram from DigitalRF: {e}")
        raise
