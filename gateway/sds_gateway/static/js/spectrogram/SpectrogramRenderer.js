/**
 * Spectrogram Renderer Component
 * Handles the rendering and display of spectrogram data
 */

export class SpectrogramRenderer {
	constructor(imageId = "spectrogramImage") {
		this.imageId = imageId;
		this.imageElement = null;
		this.currentImageUrl = null;
	}

	/**
	 * Initialize the image element
	 */
	initializeImage() {
		this.imageElement = document.getElementById(this.imageId);
		if (!this.imageElement) {
			console.error(`Image element with ID '${this.imageId}' not found`);
			return false;
		}
		return true;
	}

	/**
	 * Clear the image display
	 */
	clearImage() {
		if (!this.imageElement) return;

		this.imageElement.classList.add("d-none");
		this.imageElement.src = "";

		if (this.currentImageUrl) {
			URL.revokeObjectURL(this.currentImageUrl);
			this.currentImageUrl = null;
		}
	}

	/**
	 * Render spectrogram data from image blob
	 */
	async renderFromImageBlob(imageBlob) {
		if (!this.imageElement) {
			console.error("Image element not available");
			return false;
		}

		try {
			this.clearImage();

			const imageUrl = URL.createObjectURL(imageBlob);
			this.currentImageUrl = imageUrl;

			return new Promise((resolve, reject) => {
				this.imageElement.onload = () => {
					this.imageElement.classList.remove("d-none");
					resolve(true);
				};

				this.imageElement.onerror = () => {
					URL.revokeObjectURL(imageUrl);
					reject(new Error("Failed to load image"));
				};

				this.imageElement.src = imageUrl;
			});
		} catch (error) {
			console.error("Error rendering spectrogram:", error);
			return false;
		}
	}

	/**
	 * Get display dimensions (actual rendered size)
	 */
	getDisplayDimensions() {
		if (!this.imageElement) {
			return null;
		}

		const imageContainer = this.imageElement.parentElement;
		if (!imageContainer) {
			return null;
		}

		let width, height;

		if (imageContainer.offsetWidth && imageContainer.offsetHeight) {
			width = imageContainer.offsetWidth;
			height = imageContainer.offsetHeight;
		} else {
			width = imageContainer.naturalWidth;
			height = imageContainer.naturalHeight;
		}

		if (width === 0 || height === 0) {
			return null;
		}

		return {
			width: width,
			height: height,
		};
	}

	/**
	 * Export the current image as a blob
	 */
	async exportAsBlob() {
		if (!this.imageElement || !this.imageElement.src) {
			return null;
		}

		try {
			const response = await fetch(this.imageElement.src);
			return await response.blob();
		} catch (error) {
			console.error("Error exporting image:", error);
			return null;
		}
	}

	/**
	 * Clean up resources
	 */
	destroy() {
		if (this.currentImageUrl) {
			URL.revokeObjectURL(this.currentImageUrl);
			this.currentImageUrl = null;
		}
		this.imageElement = null;
	}
}
