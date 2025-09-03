/**
 * Spectrogram Renderer Component
 * Handles the rendering and display of spectrogram data on canvas
 */

import { CANVAS_DIMENSIONS } from "./constants.js";

export class SpectrogramRenderer {
	constructor(canvasId = "spectrogramCanvas") {
		this.canvasId = canvasId;
		this.canvas = null;
		this.ctx = null;
		this.imageData = null;
		this.isInitialized = false;
	}

	/**
	 * Initialize the canvas and context
	 */
	initializeCanvas() {
		try {
			this.canvas = document.getElementById(this.canvasId);

			if (!this.canvas) {
				console.error(`Canvas with ID '${this.canvasId}' not found`);
				return false;
			}

			this.ctx = this.canvas.getContext("2d");

			// Set canvas dimensions
			this.canvas.width = CANVAS_DIMENSIONS.width;
			this.canvas.height = CANVAS_DIMENSIONS.height;

			// Set canvas style for responsive behavior
			this.canvas.style.maxWidth = "100%";
			this.canvas.style.maxHeight = "100%";

			this.isInitialized = true;
			this.clearCanvas();
			return true;
		} catch (error) {
			console.error("Failed to initialize canvas:", error);
			return false;
		}
	}

	/**
	 * Clear the canvas
	 */
	clearCanvas() {
		if (!this.isReady()) return;

		this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

		// Draw a placeholder background
		this.ctx.fillStyle = "#f8f9fa";
		this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
	}

	/**
	 * Render spectrogram data from image blob
	 */
	async renderFromImageBlob(imageBlob) {
		if (!this.isReady()) {
			console.error("Canvas not ready");
			return false;
		}

		try {
			// Clear canvas first to ensure old content is removed
			this.clearCanvas();
			console.log("Canvas cleared, starting image load...");
			
			// Create image from blob
			const image = new Image();
			const imageUrl = URL.createObjectURL(imageBlob);
			console.log("Created image URL:", imageUrl);

			return new Promise((resolve, reject) => {
				image.onload = () => {
					try {
						console.log("Image loaded successfully, dimensions:", image.width, "x", image.height);
						this.renderImage(image);
						URL.revokeObjectURL(imageUrl);
						console.log("Image rendered to canvas");
						resolve(true);
					} catch (error) {
						console.error("Error rendering image:", error);
						URL.revokeObjectURL(imageUrl);
						reject(error);
					}
				};

				image.onerror = (error) => {
					console.error("Image load error:", error);
					URL.revokeObjectURL(imageUrl);
					reject(new Error("Failed to load image"));
				};

				image.src = imageUrl;
			});
		} catch (error) {
			console.error("Error rendering spectrogram from blob:", error);
			return false;
		}
	}

	/**
	 * Render image to canvas with proper scaling
	 */
	renderImage(image) {
		if (!this.isReady()) return;

		console.log("Rendering image to canvas, canvas size:", this.canvas.width, "x", this.canvas.height);

		// Clear canvas
		this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

		// Calculate scaling to fit image within canvas while maintaining aspect ratio
		const scale = Math.min(
			this.canvas.width / image.width,
			this.canvas.height / image.height,
		);

		const scaledWidth = image.width * scale;
		const scaledHeight = image.height * scale;

		// Center the image on canvas
		const x = (this.canvas.width - scaledWidth) / 2;
		const y = (this.canvas.height - scaledHeight) / 2;

		console.log("Image scaling - original:", image.width, "x", image.height, "scaled:", scaledWidth, "x", scaledHeight, "position:", x, y);

		// Draw the image
		this.ctx.drawImage(image, x, y, scaledWidth, scaledHeight);

		// Store the rendered image data for potential export
		this.imageData = this.ctx.getImageData(
			0,
			0,
			this.canvas.width,
			this.canvas.height,
		);
		
		console.log("Image drawn to canvas successfully");
	}

	/**
	 * Export the current canvas as a blob
	 */
	exportAsBlob(mimeType = "image/png", quality = 0.9) {
		if (!this.isReady() || !this.imageData) {
			return null;
		}

		return new Promise((resolve) => {
			this.canvas.toBlob(resolve, mimeType, quality);
		});
	}

	/**
	 * Get canvas dimensions
	 */
	getCanvasDimensions() {
		return {
			width: this.canvas.width,
			height: this.canvas.height,
		};
	}

	/**
	 * Resize canvas to new dimensions
	 */
	resizeCanvas(width, height) {
		if (!this.isReady()) return;

		this.canvas.width = width;
		this.canvas.height = height;

		// Redraw if we have image data
		if (this.imageData) {
			this.ctx.putImageData(this.imageData, 0, 0);
		} else {
			this.clearCanvas();
		}
	}

	/**
	 * Check if renderer is properly initialized
	 */
	isRendererInitialized() {
		return this.isInitialized;
	}

	/**
	 * Check if canvas is ready for rendering
	 */
	isReady() {
		return this.isInitialized && this.ctx !== null && this.canvas !== null;
	}

	/**
	 * Check if canvas element exists in DOM
	 */
	canvasExists() {
		return document.getElementById(this.canvasId) !== null;
	}

	/**
	 * Wait for canvas to be available in DOM
	 */
	async waitForCanvas(timeout = 5000) {
		const startTime = Date.now();

		while (!this.canvasExists() && Date.now() - startTime < timeout) {
			await new Promise((resolve) => setTimeout(resolve, 100));
		}

		return this.canvasExists();
	}

	/**
	 * Destroy the renderer and clean up resources
	 */
	destroy() {
		if (this.imageData) {
			this.imageData = null;
		}

		if (this.ctx) {
			this.ctx = null;
		}

		this.isInitialized = false;
	}
}
