/** Capture type dropdown for upload modal. Migrated from deprecated/files-ui.js */
/**
 * Capture Type Selection Handler
 * Manages capture type dropdown and conditional form fields
 */
class CaptureTypeSelector {
	constructor() {
		this.boundHandlers = new Map(); // Track event handlers for cleanup
		this.initializeElements();
		this.setupEventListeners();
	}

	initializeElements() {
		this.captureTypeSelect = document.getElementById("captureTypeSelect");
		this.channelInputGroup = document.getElementById("channelInputGroup");
		this.scanGroupInputGroup = document.getElementById("scanGroupInputGroup");
		this.captureChannelsInput = document.getElementById("captureChannelsInput");
		this.captureScanGroupInput = document.getElementById(
			"captureScanGroupInput",
		);
		this.uploadModal = document.getElementById("uploadCaptureModal");

		// Log which elements were found for debugging
		console.log("CaptureTypeSelector elements found:", {
			captureTypeSelect: !!this.captureTypeSelect,
			channelInputGroup: !!this.channelInputGroup,
			scanGroupInputGroup: !!this.scanGroupInputGroup,
			captureChannelsInput: !!this.captureChannelsInput,
			captureScanGroupInput: !!this.captureScanGroupInput,
			uploadModal: !!this.uploadModal,
		});
	}

	setupEventListeners() {
		// Ensure boundHandlers is initialized
		if (!this.boundHandlers) {
			this.boundHandlers = new Map();
		}

		if (this.captureTypeSelect) {
			const changeHandler = (e) => this.handleTypeChange(e);
			this.boundHandlers.set(this.captureTypeSelect, changeHandler);
			this.captureTypeSelect.addEventListener("change", changeHandler);
		}

		if (this.uploadModal) {
			const hiddenHandler = () => this.resetForm();
			this.boundHandlers.set(this.uploadModal, hiddenHandler);
			this.uploadModal.addEventListener("hidden.bs.modal", hiddenHandler);
		}
	}

	handleTypeChange(event) {
		const selectedType = event.target.value;

		// Validate capture type
		if (!this.validateCaptureType(selectedType)) {
			ErrorHandler.showError(
				"Invalid capture type selected",
				"capture-type-validation",
			);
			return;
		}

		// Hide both input groups initially
		this.hideInputGroups();

		// Clear required attributes
		this.clearRequiredAttributes();

		// Show appropriate input group based on selection
		if (selectedType === "drf") {
			this.showChannelInput();
		} else if (selectedType === "rh") {
			this.showScanGroupInput();
		}
	}

	hideInputGroups() {
		if (this.channelInputGroup) {
			this.channelInputGroup.classList.add("hidden-input-group");
		}
		if (this.scanGroupInputGroup) {
			this.scanGroupInputGroup.classList.add("hidden-input-group");
		}
	}

	clearRequiredAttributes() {
		if (this.captureChannelsInput) {
			this.captureChannelsInput.removeAttribute("required");
		}
		if (this.captureScanGroupInput) {
			this.captureScanGroupInput.removeAttribute("required");
		}
	}

	showChannelInput() {
		if (this.channelInputGroup) {
			this.channelInputGroup.classList.remove("hidden-input-group");
		}
		if (this.captureChannelsInput) {
			this.captureChannelsInput.setAttribute("required", "required");
		}
	}

	showScanGroupInput() {
		if (this.scanGroupInputGroup) {
			this.scanGroupInputGroup.classList.remove("hidden-input-group");
		}
		// scan_group is optional for RadioHound captures, so no required attribute
	}

	// Input validation methods
	validateCaptureType(type) {
		const validTypes = ["drf", "rh"];
		return validTypes.includes(type);
	}

	validateChannelInput(channels) {
		if (!channels || typeof channels !== "string") return false;
		// Basic validation for channel input (can be enhanced based on requirements)
		return channels.trim().length > 0 && channels.length <= 1000;
	}

	validateScanGroupInput(scanGroup) {
		if (!scanGroup || typeof scanGroup !== "string") return false;
		// Basic validation for scan group input
		return scanGroup.trim().length > 0 && scanGroup.length <= 255;
	}

	sanitizeInput(input) {
		if (!input || typeof input !== "string") return "";
		// Remove potentially dangerous characters
		return input.replace(/[<>:"/\\|?*]/g, "_").trim();
	}

	// Memory management and cleanup
	cleanup() {
		// Remove all bound event handlers
		for (const [element, handler] of this.boundHandlers) {
			if (element?.removeEventListener) {
				element.removeEventListener("change", handler);
				element.removeEventListener("hidden.bs.modal", handler);
			}
		}
		this.boundHandlers.clear();
		console.log("CaptureTypeSelector cleanup completed");
	}

	resetForm() {
		// Reset the form
		const form = document.getElementById("uploadCaptureForm");
		if (form) {
			form.reset();
		}

		// Hide input groups
		this.hideInputGroups();

		// Clear required attributes
		this.clearRequiredAttributes();

		// Clear global variables if they exist
		this.cleanupGlobalState();
	}

	// Better global state management
	cleanupGlobalState() {
		const globalVars = ["filesToSkip", "fileCheckResults", "selectedFiles"];

		for (const varName of globalVars) {
			if (window[varName]) {
				if (typeof window[varName].clear === "function") {
					window[varName].clear();
				} else if (Array.isArray(window[varName])) {
					window[varName].length = 0;
				} else {
					window[varName] = null;
				}
				console.log(`Cleaned up global variable: ${varName}`);
			}
		}
	}
}

if (typeof window !== "undefined") {
	window.CaptureTypeSelector = CaptureTypeSelector;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { CaptureTypeSelector };
}

