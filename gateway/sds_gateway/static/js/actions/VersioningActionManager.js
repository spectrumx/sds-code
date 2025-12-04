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
		this.currentUserId = config.currentUserId;
		this.isOwner = config.isOwner;
		this.initializeEventListeners();
	}

	/**
	 * Initialize event listeners
	 */
	initializeEventListeners() {
		// Initialize version creation button
		this.initializeVersionCreationButton();
	}

	initializeVersionCreationButton() {
		const versionCreationButton = document.getElementById("versionCreationButton");
		if (versionCreationButton) {
			versionCreationButton.addEventListener("click", this.handleVersionCreation.bind(this));
		}
	}

	handleVersionCreation() {
		// show loading state
		window.DOMUtils.showModalLoading("versioningModal");
		
        // disable button
		versionCreationButton.disabled = true;

		// run API call to create a new version of the dataset
		window.APIClient.post("/users/dataset-versioning/", {
			dataset_uuid: this.datasetUuid,
		}).then((response) => {
			if (response.success) {
				// close modal
				window.DOMUtils.closeModal("versioningModal");
				// show success message
				window.DOMUtils.showAlert(`Dataset version updated to v${response.version} successfully`, "success");
				// refresh dataset list
				window.location.reload();
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