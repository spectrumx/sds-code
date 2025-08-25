/**
 * Spectrogram Controls Component
 * Manages the control panel for spectrogram generation settings
 */

import { DEFAULT_SPECTROGRAM_SETTINGS, INPUT_RANGES } from "./constants.js";

export class SpectrogramControls {
	constructor() {
		this.settings = { ...DEFAULT_SPECTROGRAM_SETTINGS };
		this.onSettingsChange = null;
		this.initializeControls();
	}

	/**
	 * Initialize the control panel elements and event listeners
	 */
	initializeControls() {
		this.fftSizeSelect = document.getElementById("fftSize");
		this.stdDevInput = document.getElementById("stdDev");
		this.hopSizeInput = document.getElementById("hopSize");
		this.colorMapSelect = document.getElementById("colorMap");
		this.generateBtn = document.getElementById("generateSpectrogramBtn");

		if (
			!this.fftSizeSelect ||
			!this.stdDevInput ||
			!this.hopSizeInput ||
			!this.colorMapSelect ||
			!this.generateBtn
		) {
			console.error("Required control elements not found");
			return;
		}

		this.setupEventListeners();
		this.updateControlValues();
	}

	/**
	 * Set up event listeners for all controls
	 */
	setupEventListeners() {
		// FFT Size change
		this.fftSizeSelect.addEventListener("change", (e) => {
			this.settings.fftSize = Number.parseInt(e.target.value);
			this.notifySettingsChange();
		});

		// Standard Deviation change
		this.stdDevInput.addEventListener("change", (e) => {
			const value = Number.parseInt(e.target.value);
			if (this.validateInput(value, INPUT_RANGES.stdDev)) {
				this.settings.stdDev = value;
				this.notifySettingsChange();
			} else {
				this.resetInputValue(this.stdDevInput, this.settings.stdDev);
			}
		});

		// Hop Size change
		this.hopSizeInput.addEventListener("change", (e) => {
			const value = Number.parseInt(e.target.value);
			if (this.validateInput(value, INPUT_RANGES.hopSize)) {
				this.settings.hopSize = value;
				this.notifySettingsChange();
			} else {
				this.resetInputValue(this.hopSizeInput, this.settings.hopSize);
			}
		});

		// Color Map change
		this.colorMapSelect.addEventListener("change", (e) => {
			this.settings.colorMap = e.target.value;
			this.notifySettingsChange();
		});

		// Generate button click
		this.generateBtn.addEventListener("click", () => {
			this.onGenerateClick();
		});
	}

	/**
	 * Validate input value against specified range
	 */
	validateInput(value, range) {
		return value >= range.min && value <= range.max;
	}

	/**
	 * Reset input value to last valid setting
	 */
	resetInputValue(input, value) {
		input.value = value;
		this.showValidationError(
			input,
			`Value must be between ${INPUT_RANGES[input.id].min} and ${INPUT_RANGES[input.id].max}`,
		);
	}

	/**
	 * Show validation error for input field
	 */
	showValidationError(input, message) {
		// Remove existing error styling
		input.classList.remove("is-invalid");

		// Remove existing error message
		const existingError = input.parentNode.querySelector(".invalid-feedback");
		if (existingError) {
			existingError.remove();
		}

		// Add error styling and message
		input.classList.add("is-invalid");
		const errorDiv = document.createElement("div");
		errorDiv.className = "invalid-feedback";
		errorDiv.textContent = message;
		input.parentNode.appendChild(errorDiv);

		// Auto-remove error after 3 seconds
		setTimeout(() => {
			input.classList.remove("is-invalid");
			if (errorDiv.parentNode) {
				errorDiv.remove();
			}
		}, 3000);
	}

	/**
	 * Update control values to match current settings
	 */
	updateControlValues() {
		this.fftSizeSelect.value = this.settings.fftSize;
		this.stdDevInput.value = this.settings.stdDev;
		this.hopSizeInput.value = this.settings.hopSize;
		this.colorMapSelect.value = this.settings.colorMap;
	}

	/**
	 * Get current settings
	 */
	getSettings() {
		return { ...this.settings };
	}

	/**
	 * Set settings and update controls
	 */
	setSettings(newSettings) {
		this.settings = { ...newSettings };
		this.updateControlValues();
	}

	/**
	 * Set callback for settings changes
	 */
	setSettingsChangeCallback(callback) {
		this.onSettingsChange = callback;
	}

	/**
	 * Set callback for generate button clicks
	 */
	setGenerateCallback(callback) {
		this.onGenerateClick = callback;
	}

	/**
	 * Notify that settings have changed
	 */
	notifySettingsChange() {
		if (this.onSettingsChange) {
			this.onSettingsChange(this.settings);
		}
	}

	/**
	 * Enable/disable the generate button
	 */
	setGenerateButtonState(enabled) {
		this.generateBtn.disabled = !enabled;
		if (enabled) {
			this.generateBtn.innerHTML =
				'<i class="bi bi-play-fill"></i> Generate Spectrogram';
		} else {
			this.generateBtn.innerHTML =
				'<span class="spinner-border spinner-border-sm me-2" role="status"></span>Generating...';
		}
	}

	/**
	 * Reset controls to default values
	 */
	resetToDefaults() {
		this.settings = { ...DEFAULT_SPECTROGRAM_SETTINGS };
		this.updateControlValues();
		this.notifySettingsChange();
	}
}
