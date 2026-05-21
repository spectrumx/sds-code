/**
 * Versioning Action Manager
 * Handles version creation and managing dataset versions
 */
class VersioningActionManager extends ModalManager {
	/**
	 * Initialize versioning action manager
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		super();
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
		this.initializeCopySharedUsersCheckbox();
	}

	initializeVersionCreationButton() {
		const versionCreationButton = document.getElementById(
			`createVersionBtn-${this.datasetUuid}`,
		);
		const copySharedUsersCheckbox = document.getElementById(
			`copySharedUsers-${this.datasetUuid}`,
		);
		if (versionCreationButton) {
			// Prevent duplicate event listeners
			if (versionCreationButton.dataset.versionSetup === "true") {
				return;
			}

			versionCreationButton.dataset.versionSetup = "true";
			versionCreationButton.addEventListener("click", (event) =>
				this.handleVersionCreation(
					event,
					versionCreationButton,
					copySharedUsersCheckbox,
				),
			);
		}
	}

	handleVersionCreation(event, versionCreationButton, copySharedUsersCheckbox) {
		event.preventDefault();
		event.stopPropagation();

		// Prevent double-submission
		if (versionCreationButton.dataset.processing === "true") {
			return;
		}

		// Mark as processing
		versionCreationButton.dataset.processing = "true";

		// show loading state
		void ModalManager.showModalLoading(this.modalId);

		// disable button
		versionCreationButton.disabled = true;

		// run API call to create a new version of the dataset
		window.APIClient.post("/users/dataset-versioning/", {
			dataset_uuid: this.datasetUuid,
			copy_shared_users: copySharedUsersCheckbox?.checked ?? false,
		})
			.then((response) => {
				if (response.success) {
					const modalEl = document.getElementById(this.modalId);
					const onHidden = async () => {
						if (modalEl) {
							modalEl.removeEventListener("hidden.bs.modal", onHidden);
						}
						void window.DOMUtils?.showMessage?.(
							`Dataset version updated to v${response.version} successfully`,
							{
								variant: "success",
								placement: "toast",
								presentation: "toast",
							},
						);
						if (
							window.listRefreshManager &&
							typeof window.listRefreshManager.loadTable === "function"
						) {
							try {
								await window.listRefreshManager.loadTable();
							} catch (refreshErr) {
								console.error(
									"VersioningActionManager: list refresh failed after version create",
									refreshErr,
								);
							}
						} else {
							console.warn("listRefreshManager not available, reloading page");
							window.location.reload();
						}
					};
					if (modalEl) {
						modalEl.addEventListener("hidden.bs.modal", onHidden);
					}
					this.closeModal(this.modalId);
					if (!modalEl) {
						onHidden();
					}
				} else {
					// show error message and error message from response
					void window.DOMUtils?.showMessage?.(
						response.error || "Failed to create dataset version",
						{
							variant: "danger",
							placement: "toast",
							presentation: "toast",
						},
					);
				}
			})
			.catch((error) => {
				// show error message and error message from error
				void window.DOMUtils?.showMessage?.(
					error.message || "Failed to create dataset version",
					{
						variant: "danger",
						placement: "toast",
						presentation: "toast",
					},
				);
			})
			.finally(() => {
				// Re-enable button and clear processing flag
				versionCreationButton.disabled = false;
				versionCreationButton.dataset.processing = "false";
			});
	}

	initializeCopySharedUsersCheckbox() {
		const copySharedUsersCheckbox = document.getElementById(
			`copySharedUsers-${this.datasetUuid}`,
		);
		if (copySharedUsersCheckbox) {
			copySharedUsersCheckbox.addEventListener("change", (event) =>
				this.showCopySharedUsersWarning(event),
			);
		}
	}

	showCopySharedUsersWarning(event) {
		const copySharedUsersWarning = document.getElementById(
			`copySharedUsersWarning-${this.datasetUuid}`,
		);

		if (copySharedUsersWarning) {
			if (event.target.checked) {
				copySharedUsersWarning.classList.remove("display-none");
			} else {
				copySharedUsersWarning.classList.add("display-none");
			}
		}
	}
}

// Make class available globally
window.VersioningActionManager = VersioningActionManager;

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
	module.exports = { VersioningActionManager };
}
