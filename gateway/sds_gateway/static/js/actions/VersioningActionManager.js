/**
 * Versioning Action Manager
 * Handles version creation and managing dataset versions
 */
class VersioningActionManager {
	/**
	 * Initialize versioning action manager
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.permissions = config.permissions;
		this.datasetUuid = config.datasetUuid;
		this.initializeEventListeners();
		this.modalId = `versioningModal-${this.datasetUuid}`;
	}

	/**
	 * Initialize event listeners
	 */
	initializeEventListeners() {
		// Initialize version creation button
		this.initializeVersionCreationButton();
	}

	initializeVersionCreationButton() {
		const versionCreationButton = document.getElementById(`createVersionBtn-${this.datasetUuid}`);
		if (versionCreationButton) {
			versionCreationButton.addEventListener(
				"click",
				(event) => this.handleVersionCreation(
					event,
					versionCreationButton,
				),
			);
		}
	}

	handleVersionCreation(event, versionCreationButton) {
		event.preventDefault();
		event.stopPropagation();

		// show loading state
		window.DOMUtils.showModalLoading(this.modalId);
		
        // disable button
		versionCreationButton.disabled = true;

		// run API call to create a new version of the dataset
		window.APIClient.post("/users/dataset-versioning/", {
			dataset_uuid: this.datasetUuid,
		}).then((response) => {
			if (response.success) {
				// close modal
				window.DOMUtils.closeModal(this.modalId);
				// show success message
				window.DOMUtils.showAlert(`Dataset version updated to v${response.version} successfully`, "success");
				// refresh dataset list
				window.ListRefreshManager.loadTable();
			} else {
				// show error message and error message from response
				window.DOMUtils.showAlert(response.error || "Failed to create dataset version", "error");
			}
		}).catch((error) => {
			// show error message and error message from error
			window.DOMUtils.showAlert(error.message || "Failed to create dataset version", "error");
		});
	}
}

// Make class available globally
window.VersioningActionManager = VersioningActionManager;

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
	module.exports = { VersioningActionManager };
}