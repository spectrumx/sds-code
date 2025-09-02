#!/usr/bin/env python3
# ruff: noqa: T201, BLE001, F841, EXE001
"""
Example Spectrogram Script

This is an example of how you would add your own spectrogram analysis script
to the ~/scripts directory after running copy_to_home.py.

This script demonstrates basic spectrogram generation and can be customized
for your specific RF data analysis needs.

Note: This is an educational example script, so print statements are intentional.
"""

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import ShortTimeFFT
from scipy.signal.windows import gaussian


def generate_example_spectrogram():
    """Generate an example spectrogram for demonstration."""

    print("🎯 Generating Example Spectrogram...")

    # Generate sample complex RF data
    sample_rate = 1e6  # 1 MHz
    duration = 1.0  # 1 second
    num_samples = int(sample_rate * duration)

    # Create time array
    t = np.linspace(0, duration, num_samples)

    # Generate sample signal (two frequency components)
    signal = (
        np.sin(2 * np.pi * 100e3 * t)  # 100 kHz
        + 0.5 * np.sin(2 * np.pi * 300e3 * t)  # 300 kHz
        + 0.3 * np.random.randn(num_samples)
        + 1j * 0.3 * np.random.randn(num_samples)
    )  # Noise

    print(f"   Sample rate: {sample_rate / 1e6:.1f} MHz")
    print(f"   Duration: {duration} seconds")
    print(f"   Samples: {num_samples:,}")

    # Generate spectrogram
    fft_size = 1024
    hop_size = 256
    window = gaussian(fft_size, std=fft_size // 8, sym=True)

    stfft = ShortTimeFFT(
        window, hop=hop_size, fs=sample_rate, mfft=fft_size, fft_mode="centered"
    )
    spectrogram = stfft.spectrogram(signal)

    print(f"   Spectrogram shape: {spectrogram.shape}")

    # Convert to dB
    spectrogram_db = 10 * np.log10(np.maximum(spectrogram, 1e-12))

    # Create plot
    fig, ax = plt.subplots(figsize=(12, 8))

    # Get time and frequency extents
    extent = stfft.extent(num_samples)
    time_extent = extent[:2]
    freq_extent = extent[2:]

    # Plot spectrogram
    im = ax.imshow(
        spectrogram_db, origin="lower", aspect="auto", extent=extent, cmap="magma"
    )

    # Add labels and title
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title("Example Spectrogram - Two Frequency Components + Noise")

    # Format frequency axis
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x / 1e3:.0f}k"))
    ax.set_ylabel("Frequency (kHz)")

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Power Spectral Density (dB)")

    plt.tight_layout()

    print("   ✅ Spectrogram generated successfully!")
    print("   📊 Displaying plot...")

    plt.show()

    return fig, spectrogram_db


def save_spectrogram_data(spectrogram, filename="example_spectrogram.npy"):
    """Save the spectrogram data for later use."""

    try:
        np.save(filename, spectrogram)
        print(f"   💾 Saved spectrogram data to: {filename}")
    except Exception as e:
        print(f"   ❌ Error saving data: {e}")


def main():
    """Main function to run the example."""

    print("=" * 60)
    print("Example Spectrogram Script")
    print("=" * 60)
    print()
    print("This script demonstrates how to add your own spectrogram")
    print("analysis tools to the ~/scripts directory.")
    print()

    try:
        # Generate spectrogram
        fig, spectrogram = generate_example_spectrogram()

        # Save data
        save_spectrogram_data(spectrogram)

        print("\n🎉 Example completed successfully!")
        print("\n💡 Customization ideas:")
        print("   • Modify the signal generation for your data")
        print("   • Adjust FFT parameters (size, hop, window)")
        print("   • Add more analysis functions")
        print("   • Integrate with your RF data sources")
        print("   • Save this script to ~/scripts/ for reuse")

    except Exception as e:
        print(f"\n❌ Error running example: {e}")
        print("💡 Make sure you have the required packages:")
        print("   pip install numpy matplotlib scipy")


if __name__ == "__main__":
    main()
