/**
 * Files UI Components
 * Manages capture type selection and page initialization
 */

/**
 * Capture Type Selection Handler
 * Manages capture type dropdown and conditional form fields
 */
class CaptureTypeSelector {
	constructor() {
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
		if (this.captureTypeSelect) {
			this.captureTypeSelect.addEventListener("change", (e) =>
				this.handleTypeChange(e),
			);
		}

		if (this.uploadModal) {
			this.uploadModal.addEventListener("hidden.bs.modal", () =>
				this.resetForm(),
			);
		}
	}

	handleTypeChange(event) {
		const selectedType = event.target.value;

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
		if (window.filesToSkip) {
			window.filesToSkip.clear();
		}
		if (window.fileCheckResults) {
			window.fileCheckResults.clear();
		}
	}
}

/**
 * Files Page Initialization
 * Initializes modal managers, capture handlers, and user search components
 */
class FilesPageInitializer {
	constructor() {
		this.initializeComponents();
	}

	initializeComponents() {
		this.initializeModalManager();
		this.initializeCapturesTableManager();
		this.initializeUserSearchHandlers();
	}

	initializeModalManager() {
		// Initialize ModalManager for capture modal
		let modalManager = null;
		if (window.ModalManager) {
			modalManager = new window.ModalManager({
				modalId: "capture-modal",
				modalBodyId: "capture-modal-body",
				modalTitleId: "capture-modal-label",
			});

			this.modalManager = modalManager;
		} else {
			console.warn("ModalManager not available");
		}
	}

	initializeCapturesTableManager() {
		// Initialize CapturesTableManager for capture edit/download functionality
		if (window.CapturesTableManager) {
			window.capturesTableManager = new window.CapturesTableManager({
				modalHandler: this.modalManager,
			});
		} else {
			console.warn("CapturesTableManager not available");
		}
	}

	initializeUserSearchHandlers() {
		// Create a UserSearchHandler for each share modal
		const shareModals = document.querySelectorAll(".modal[data-item-uuid]");

		for (const modal of shareModals) {
			this.setupUserSearchHandler(modal);
		}
	}

	setupUserSearchHandler(modal) {
		const itemUuid = modal.getAttribute("data-item-uuid");
		const itemType = modal.getAttribute("data-item-type");

		if (!window.UserSearchHandler) {
			console.warn("UserSearchHandler not available");
			return;
		}

		const handler = new window.UserSearchHandler();
		// Store the handler on the modal element
		modal.userSearchHandler = handler;

		// On modal show, set the item info and call init()
		modal.addEventListener("show.bs.modal", () => {
			if (modal.userSearchHandler) {
				modal.userSearchHandler.setItemInfo(itemUuid, itemType);
				modal.userSearchHandler.init();
			}
		});

		// On modal hide, reset all selections and entered data
		modal.addEventListener("hidden.bs.modal", () => {
			if (modal.userSearchHandler) {
				modal.userSearchHandler.resetAll();
			}
		});
	}

	/**
	 * Get initialized modal manager
	 * @returns {Object|null} - The modal manager instance
	 */
	getModalManager() {
		return this.modalManager;
	}

	/**
	 * Get captures table manager
	 * @returns {Object|null} - The captures table manager instance
	 */
	getCapturesTableManager() {
		return window.capturesTableManager;
	}
}

// Initialize when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
	// Initialize capture type selector and page components
	new CaptureTypeSelector();
	window.filesPageInitializer = new FilesPageInitializer();
});
