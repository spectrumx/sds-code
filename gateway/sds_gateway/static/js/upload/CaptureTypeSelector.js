/**
 * Capture type dropdown for upload capture modal.
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
			this.handleTypeChange({ target: this.captureTypeSelect });
		}

		if (this.uploadModal) {
			const hiddenHandler = () => this.resetForm();
			this.boundHandlers.set(this.uploadModal, hiddenHandler);
			this.uploadModal.addEventListener("hidden.bs.modal", hiddenHandler);
		}
	}

	handleTypeChange(event) {
		const selectedType = event.target.value;

		if (!selectedType) {
			this.hideInputGroups();
			this.clearRequiredAttributes();
			return;
		}

		if (!this.validateCaptureType(selectedType)) {
			console.warn("Invalid capture type selected:", selectedType);
			this.hideInputGroups();
			this.clearRequiredAttributes();
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

	cleanupGlobalState() {
		window.captureUploadController?.resetSession?.();
	}
}
if (typeof window !== "undefined") {
	window.CaptureTypeSelector = CaptureTypeSelector;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { CaptureTypeSelector };
}
