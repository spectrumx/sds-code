/**
 * Waterfall Controls Manager
 * Manages UI controls and event handling
 */

import { WATERFALL_WINDOW_SIZE } from "./constants.js";

class WaterfallControls {
	constructor(onSliceChange) {
		this.onSliceChange = onSliceChange;
		this.isPlaying = false;
		this.playbackInterval = null;
		this.playbackSpeed = 1; // fps
		this.currentSliceIndex = 0;
		this.totalSlices = 0;
		this.waterfallWindowStart = 0;
		this.hoveredSliceIndex = null;

		// Constants
		this.WATERFALL_WINDOW_SIZE = WATERFALL_WINDOW_SIZE;

		// Bind methods to preserve context
		this.handlePlayPause = this.handlePlayPause.bind(this);
		this.handleDownload = this.handleDownload.bind(this);
		this.handleSliceChange = this.handleSliceChange.bind(this);
		this.handleSliceIndexInputChange =
			this.handleSliceIndexInputChange.bind(this);
		this.handleSliceIndexInputKeyDown =
			this.handleSliceIndexInputKeyDown.bind(this);
		this.handleDecrementSlice = this.handleDecrementSlice.bind(this);
		this.handleIncrementSlice = this.handleIncrementSlice.bind(this);
		this.handleScrollUp = this.handleScrollUp.bind(this);
		this.handleScrollDown = this.handleScrollDown.bind(this);
		this.handlePlaybackSpeedChange = this.handlePlaybackSpeedChange.bind(this);
		this.handleColorMapChange = this.handleColorMapChange.bind(this);
		this.handleKeyDown = this.handleKeyDown.bind(this);
	}

	/**
	 * Set up event listeners for controls
	 */
	setupEventListeners() {
		// Play/Pause button
		const playPauseBtn = document.getElementById("playPauseBtn");
		if (playPauseBtn) {
			playPauseBtn.addEventListener("click", this.handlePlayPause);
		}

		// Download button
		const downloadBtn = document.getElementById("downloadBtn");
		if (downloadBtn) {
			downloadBtn.addEventListener("click", this.handleDownload);
		}

		// Slice slider
		const sliceSlider = document.getElementById("currentSlice");
		if (sliceSlider) {
			sliceSlider.addEventListener("input", this.handleSliceChange);
		}

		// Increment/Decrement slice buttons
		const decrementBtn = document.getElementById("decrementSlice");
		if (decrementBtn) {
			decrementBtn.addEventListener("click", this.handleDecrementSlice);
		}

		const incrementBtn = document.getElementById("incrementSlice");
		if (incrementBtn) {
			incrementBtn.addEventListener("click", this.handleIncrementSlice);
		}

		// Slice index input field
		const sliceIndexInput = document.getElementById("sliceIndexInput");
		if (sliceIndexInput) {
			sliceIndexInput.addEventListener(
				"change",
				this.handleSliceIndexInputChange,
			);
			sliceIndexInput.addEventListener(
				"keydown",
				this.handleSliceIndexInputKeyDown,
			);
		}

		// Playback speed
		const speedSelect = document.getElementById("playbackSpeed");
		if (speedSelect) {
			speedSelect.addEventListener("change", this.handlePlaybackSpeedChange);
		}

		// Color map
		const colorSelect = document.getElementById("colorMap");
		if (colorSelect) {
			colorSelect.addEventListener("change", this.handleColorMapChange);
		}

		// Scroll indicator buttons
		const scrollUpBtn = document.getElementById("scrollUpBtn");
		if (scrollUpBtn) {
			scrollUpBtn.addEventListener("click", this.handleScrollUp);
		}

		const scrollDownBtn = document.getElementById("scrollDownBtn");
		if (scrollDownBtn) {
			scrollDownBtn.addEventListener("click", this.handleScrollDown);
		}

		// Keyboard navigation
		document.addEventListener("keydown", this.handleKeyDown);
	}

	/**
	 * Update the slice slider with total slices
	 */
	updateSliceSlider() {
		const slider = document.getElementById("currentSlice");
		const counter = document.getElementById("sliceCounter");
		const minLabel = document.getElementById("sliceMinLabel");
		const maxLabel = document.getElementById("sliceMaxLabel");

		if (slider) {
			slider.max = Math.max(0, this.totalSlices - 1);
			slider.value = 0;
		}

		if (counter) {
			counter.textContent = `0 / ${this.totalSlices}`;
		}

		// Update min/max labels (convert from 0-based to 1-based for display)
		if (minLabel) {
			minLabel.textContent = "1";
		}

		if (maxLabel) {
			maxLabel.textContent = this.totalSlices.toString();
		}

		// Update button states
		this.updateSliceButtons();
		this.updateSliceIndexInput();
		this.ensureSliceVisible();
		this.updateScrollIndicators();
	}

	/**
	 * Update the slice counter display
	 */
	updateSliceCounter() {
		const counter = document.getElementById("sliceCounter");
		if (counter) {
			counter.textContent = `${this.currentSliceIndex} / ${this.totalSlices}`;
		}
	}

	/**
	 * Ensure the selected slice is visible in the current window
	 */
	ensureSliceVisible() {
		if (this.currentSliceIndex < this.waterfallWindowStart) {
			// Selected slice is below the current window, shift window down
			this.waterfallWindowStart = this.currentSliceIndex;
		} else if (
			this.currentSliceIndex >=
			this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE
		) {
			// Selected slice is above the current window, shift window up
			this.waterfallWindowStart =
				this.currentSliceIndex - this.WATERFALL_WINDOW_SIZE + 1;
		}
		// Ensure window bounds are respected
		this.waterfallWindowStart = Math.max(
			0,
			Math.min(
				this.waterfallWindowStart,
				this.totalSlices - this.WATERFALL_WINDOW_SIZE,
			),
		);
	}

	/**
	 * Update all slice-related UI elements
	 */
	updateSliceUI() {
		this.updateSliceCounter();
		this.updateSliceButtons();
		this.updateSliceIndexInput();
		this.ensureSliceVisible();
		this.updateScrollIndicators();

		// Update slider value
		const slider = document.getElementById("currentSlice");
		if (slider) {
			slider.value = this.currentSliceIndex;
		}
	}

	/**
	 * Update the state of increment/decrement buttons
	 */
	updateSliceButtons() {
		const decrementBtn = document.getElementById("decrementSlice");
		const incrementBtn = document.getElementById("incrementSlice");

		if (decrementBtn) {
			decrementBtn.disabled = this.currentSliceIndex <= 0;
		}

		if (incrementBtn) {
			incrementBtn.disabled = this.currentSliceIndex >= this.totalSlices - 1;
		}
	}

	/**
	 * Update the slice index input field
	 */
	updateSliceIndexInput() {
		const sliceIndexInput = document.getElementById("sliceIndexInput");
		if (sliceIndexInput) {
			// Update min/max values
			sliceIndexInput.min = 1;
			sliceIndexInput.max = this.totalSlices;
			// Update current value (convert from 0-based to 1-based for display)
			sliceIndexInput.value = this.currentSliceIndex + 1;
		}
	}

	/**
	 * Update scroll indicator buttons
	 */
	updateScrollIndicators() {
		const scrollUpBtn = document.getElementById("scrollUpBtn");
		const scrollDownBtn = document.getElementById("scrollDownBtn");
		const scrollIndicatorAbove = document.getElementById(
			"scrollIndicatorAbove",
		);
		const scrollIndicatorBelow = document.getElementById(
			"scrollIndicatorBelow",
		);

		const canScrollUp =
			this.waterfallWindowStart < this.totalSlices - this.WATERFALL_WINDOW_SIZE;
		const canScrollDown = this.waterfallWindowStart > 0;

		// Show/hide indicators based on whether scrolling is possible
		if (scrollIndicatorAbove) {
			scrollIndicatorAbove.classList.toggle("visible", canScrollUp);
		}

		if (scrollIndicatorBelow) {
			scrollIndicatorBelow.classList.toggle("visible", canScrollDown);
		}

		// Update button states
		if (scrollUpBtn) {
			scrollUpBtn.disabled = !canScrollUp;
			scrollUpBtn.classList.toggle("disabled", !canScrollUp);
		}

		if (scrollDownBtn) {
			scrollDownBtn.disabled = !canScrollDown;
			scrollDownBtn.classList.toggle("disabled", !canScrollDown);
		}
	}

	/**
	 * Start playback animation
	 */
	startPlayback() {
		if (this.isPlaying) return;

		this.isPlaying = true;
		const playPauseBtn = document.getElementById("playPauseBtn");
		if (playPauseBtn) {
			playPauseBtn.innerHTML = '<i class="bi bi-pause-fill"></i> Pause';
			playPauseBtn.classList.remove("btn-outline-primary");
			playPauseBtn.classList.add("btn-primary");
		}

		// Use requestAnimationFrame for better timing
		let lastFrameTime = performance.now();
		const frameInterval = 1000 / this.playbackSpeed; // Convert fps to milliseconds

		const animate = (currentTime) => {
			if (!this.isPlaying) return;

			const deltaTime = currentTime - lastFrameTime;

			if (deltaTime >= frameInterval) {
				// Move to next slice, but don't loop around
				if (this.currentSliceIndex < this.totalSlices - 1) {
					this.currentSliceIndex++;
				} else {
					// Stop playback when we reach the end
					this.stopPlayback();
					return;
				}

				// Update UI
				const slider = document.getElementById("currentSlice");
				if (slider) {
					slider.value = this.currentSliceIndex;
				}

				// Clear hover state when changing slice during playback
				this.hoveredSliceIndex = null;

				this.updateSliceUI();

				// Call callback for slice change
				if (this.onSliceChange) {
					this.onSliceChange(this.currentSliceIndex, this.waterfallWindowStart);
				}

				lastFrameTime = currentTime;
			}

			// Continue animation loop
			this.playbackInterval = requestAnimationFrame(animate);
		};

		this.playbackInterval = requestAnimationFrame(animate);
	}

	/**
	 * Stop playback animation
	 */
	stopPlayback() {
		if (!this.isPlaying) return;

		this.isPlaying = false;
		if (this.playbackInterval) {
			cancelAnimationFrame(this.playbackInterval);
			this.playbackInterval = null;
		}

		const playPauseBtn = document.getElementById("playPauseBtn");
		if (playPauseBtn) {
			playPauseBtn.innerHTML = '<i class="bi bi-play-fill"></i> Play';
			playPauseBtn.classList.remove("btn-primary");
			playPauseBtn.classList.add("btn-outline-primary");
		}
	}

	/**
	 * Event handlers
	 */
	handlePlayPause() {
		if (this.isPlaying) {
			this.stopPlayback();
		} else {
			this.startPlayback();
		}
	}

	handleDownload() {
		this.emitEvent("download", {});
	}

	handleSliceChange(event) {
		const newIndex = Number.parseInt(event.target.value);
		if (newIndex !== this.currentSliceIndex) {
			this.currentSliceIndex = newIndex;
			this.hoveredSliceIndex = null;

			this.updateSliceUI();

			if (this.onSliceChange) {
				this.onSliceChange(this.currentSliceIndex, this.waterfallWindowStart);
			}
		}
	}

	handleSliceIndexInputChange(event) {
		const newIndex = Number.parseInt(event.target.value) - 1; // Convert from 1-based to 0-based
		if (
			!Number.isNaN(newIndex) &&
			newIndex >= 0 &&
			newIndex < this.totalSlices &&
			newIndex !== this.currentSliceIndex
		) {
			this.currentSliceIndex = newIndex;
			this.hoveredSliceIndex = null;

			this.updateSliceUI();

			if (this.onSliceChange) {
				this.onSliceChange(this.currentSliceIndex, this.waterfallWindowStart);
			}
		} else {
			// Reset to current value if invalid
			this.updateSliceIndexInput();
		}
	}

	handleSliceIndexInputKeyDown(event) {
		switch (event.key) {
			case "ArrowDown":
			case "ArrowLeft":
				event.preventDefault();
				this.handleDecrementSlice();
				break;
			case "ArrowUp":
			case "ArrowRight":
				event.preventDefault();
				this.handleIncrementSlice();
				break;
			case "Enter":
				event.preventDefault();
				event.target.blur(); // Commit the change
				break;
		}
	}

	handleDecrementSlice() {
		if (this.currentSliceIndex > 0) {
			this.currentSliceIndex--;
			// Clear hover state when changing slice
			this.hoveredSliceIndex = null;

			this.updateSliceUI();

			if (this.onSliceChange) {
				this.onSliceChange(this.currentSliceIndex, this.waterfallWindowStart);
			}
		}
	}

	handleIncrementSlice() {
		if (this.currentSliceIndex < this.totalSlices - 1) {
			this.currentSliceIndex++;
			// Clear hover state when changing slice
			this.hoveredSliceIndex = null;

			this.updateSliceUI();

			if (this.onSliceChange) {
				this.onSliceChange(this.currentSliceIndex, this.waterfallWindowStart);
			}
		}
	}

	handleScrollUp() {
		// Move the window up to show more recent slices
		const newWindowStart = Math.min(
			this.totalSlices - this.WATERFALL_WINDOW_SIZE,
			this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE,
		);
		if (newWindowStart !== this.waterfallWindowStart) {
			this.waterfallWindowStart = newWindowStart;
			// Keep the selected slice in the same relative position if possible
			if (this.currentSliceIndex < this.waterfallWindowStart) {
				this.currentSliceIndex = this.waterfallWindowStart;
			} else if (
				this.currentSliceIndex >=
				this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE
			) {
				this.currentSliceIndex =
					this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE - 1;
			}
			// Clear hover state when scrolling
			this.hoveredSliceIndex = null;

			this.updateSliceUI();

			if (this.onSliceChange) {
				this.onSliceChange(this.currentSliceIndex, this.waterfallWindowStart);
			}
		}
	}

	handleScrollDown() {
		// Move the window down to show older slices
		const newWindowStart = Math.max(
			0,
			this.waterfallWindowStart - this.WATERFALL_WINDOW_SIZE,
		);
		if (newWindowStart !== this.waterfallWindowStart) {
			this.waterfallWindowStart = newWindowStart;
			// Keep the selected slice in the same relative position if possible
			if (this.currentSliceIndex < this.waterfallWindowStart) {
				this.currentSliceIndex = this.waterfallWindowStart;
			} else if (
				this.currentSliceIndex >=
				this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE
			) {
				this.currentSliceIndex =
					this.waterfallWindowStart + this.WATERFALL_WINDOW_SIZE - 1;
			}
			// Clear hover state when scrolling
			this.hoveredSliceIndex = null;

			this.updateSliceUI();

			if (this.onSliceChange) {
				this.onSliceChange(this.currentSliceIndex, this.waterfallWindowStart);
			}
		}
	}

	handlePlaybackSpeedChange(event) {
		this.playbackSpeed = Number.parseFloat(event.target.value);
		// Clear hover state when changing playback speed
		this.hoveredSliceIndex = null;
		if (this.isPlaying) {
			this.stopPlayback();
			this.startPlayback();
		}
	}

	handleColorMapChange(event) {
		const colorMap = event.target.value;
		this.emitEvent("colorMapChanged", { colorMap });
	}

	/**
	 * Handle keyboard navigation
	 */
	handleKeyDown(event) {
		// Only handle arrow keys when not in an input field
		if (event.target.tagName === "INPUT" || event.target.tagName === "SELECT") {
			return;
		}

		switch (event.key) {
			case "ArrowDown":
			case "ArrowLeft":
				event.preventDefault();
				this.handleDecrementSlice();
				break;
			case "ArrowUp":
			case "ArrowRight":
				event.preventDefault();
				this.handleIncrementSlice();
				break;
			case "PageUp":
				event.preventDefault();
				this.handleScrollUp();
				break;
			case "PageDown":
				event.preventDefault();
				this.handleScrollDown();
				break;
		}
	}

	/**
	 * Set total slices
	 */
	setTotalSlices(totalSlices) {
		this.totalSlices = totalSlices;
		this.updateSliceSlider();
	}

	/**
	 * Set current slice index
	 */
	setCurrentSliceIndex(index) {
		if (index !== this.currentSliceIndex) {
			this.currentSliceIndex = index;
			this.updateSliceUI();
		}
	}

	/**
	 * Set waterfall window start
	 */
	setWaterfallWindowStart(start) {
		if (start !== this.waterfallWindowStart) {
			this.waterfallWindowStart = start;
			this.updateScrollIndicators();
		}
	}

	/**
	 * Set hovered slice index
	 */
	setHoveredSliceIndex(index) {
		this.hoveredSliceIndex = index;
	}

	/**
	 * Simple event system for communication
	 */
	emitEvent(eventName, data) {
		const event = new CustomEvent(`waterfall:${eventName}`, {
			detail: data,
			bubbles: true,
		});
		document.dispatchEvent(event);
	}

	/**
	 * Cleanup resources
	 */
	destroy() {
		this.stopPlayback();
		document.removeEventListener("keydown", this.handleKeyDown);
	}
}

// Make the class globally available
window.WaterfallControls = WaterfallControls;
