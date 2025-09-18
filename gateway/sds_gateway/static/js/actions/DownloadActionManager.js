/**
 * Download Action Manager
 * Handles all download-related actions
 */
class DownloadActionManager {
	/**
	 * Initialize download action manager
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.permissions = config.permissions;
		this.initializeEventListeners();
	}

	/**
	 * Initialize event listeners
	 */
	initializeEventListeners() {
		// Initialize download buttons for datasets
		this.initializeDatasetDownloadButtons();
		
		// Initialize download buttons for captures
		this.initializeCaptureDownloadButtons();
	}

	/**
	 * Initialize dataset download buttons
	 */
	initializeDatasetDownloadButtons() {
		const downloadButtons = document.querySelectorAll(".download-dataset-btn");
		
		downloadButtons.forEach((button) => {
			// Prevent duplicate event listener attachment
			if (button.dataset.downloadSetup === "true") {
				return;
			}
			button.dataset.downloadSetup = "true";

			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();

				const datasetUuid = button.getAttribute("data-dataset-uuid");
				const datasetName = button.getAttribute("data-dataset-name");

				if (!this.permissions.canDownload()) {
					this.showToast("You don't have permission to download this dataset", "warning");
					return;
				}

				this.handleDatasetDownload(datasetUuid, datasetName, button);
			});
		});
	}

	/**
	 * Initialize capture download buttons
	 */
	initializeCaptureDownloadButtons() {
		const downloadButtons = document.querySelectorAll(".download-capture-btn");
		
		downloadButtons.forEach((button) => {
			// Prevent duplicate event listener attachment
			if (button.dataset.downloadSetup === "true") {
				return;
			}
			button.dataset.downloadSetup = "true";

			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();

				const captureUuid = button.getAttribute("data-capture-uuid");
				const captureName = button.getAttribute("data-capture-name");

				if (!this.permissions.canDownload()) {
					this.showToast("You don't have permission to download this capture", "warning");
					return;
				}

				this.handleCaptureDownload(captureUuid, captureName, button);
			});
		});
	}

	/**
	 * Handle dataset download
	 * @param {string} datasetUuid - Dataset UUID
	 * @param {string} datasetName - Dataset name
	 * @param {Element} button - Download button element
	 */
	async handleDatasetDownload(datasetUuid, datasetName, button) {
		// Update modal content
		const modalNameElement = document.getElementById("downloadDatasetName");
		if (modalNameElement) {
			modalNameElement.textContent = datasetName;
		}

		// Show the modal
		this.openCustomModal("downloadModal");

		// Handle confirm download
		const confirmBtn = document.getElementById("confirmDownloadBtn");
		if (confirmBtn) {
			// Remove any existing event listeners
			const newConfirmBtn = confirmBtn.cloneNode(true);
			confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

			newConfirmBtn.onclick = async () => {
				// Close modal first
				this.closeCustomModal("downloadModal");

				// Show loading state
				const originalContent = button.innerHTML;
				button.innerHTML = HTMLInjectionManager.createLoadingSpinner("Processing...");
				button.disabled = true;

				try {
					const response = await APIClient.post(
						`/users/download-item/dataset/${datasetUuid}/`,
						{}
					);

					if (response.success === true) {
						button.innerHTML = '<i class="bi bi-check-circle text-success"></i> Download Requested';
						this.showToast(
							response.message ||
								"Download request submitted successfully! You will receive an email when ready.",
							"success"
						);
					} else {
						button.innerHTML = '<i class="bi bi-exclamation-triangle text-danger"></i> Request Failed';
						this.showToast(
							response.message || "Download request failed. Please try again.",
							"danger"
						);
					}
				} catch (error) {
					console.error("Download error:", error);
					button.innerHTML = '<i class="bi bi-exclamation-triangle text-danger"></i> Request Failed';
					this.showToast(
						error.message || "An error occurred while processing your request.",
						"danger"
					);
				} finally {
					// Reset button after 3 seconds
					setTimeout(() => {
						button.innerHTML = originalContent;
						button.disabled = false;
					}, 3000);
				}
			};
		}
	}

	/**
	 * Handle capture download
	 * @param {string} captureUuid - Capture UUID
	 * @param {string} captureName - Capture name
	 * @param {Element} button - Download button element
	 */
	async handleCaptureDownload(captureUuid, captureName, button) {
		// Use the web download modal (same as datasets)
		if (window.showWebDownloadModal) {
			// Update modal content for capture
			const modalTitleElement = document.getElementById("webDownloadModalLabel");
			const modalNameElement = document.getElementById("webDownloadDatasetName");
			const confirmBtn = document.getElementById("confirmWebDownloadBtn");
			
			if (modalTitleElement) {
				modalTitleElement.innerHTML = '<i class="bi bi-download"></i> Download Capture';
			}
			
			if (modalNameElement) {
				modalNameElement.textContent = captureName || 'Unnamed Capture';
			}
			
			if (confirmBtn) {
				// Update button text for capture
				confirmBtn.innerHTML = '<i class="bi bi-download"></i> Yes, Download Capture';
				
				// Update the dataset UUID to capture UUID for the API call
				confirmBtn.dataset.datasetUuid = captureUuid;
				confirmBtn.dataset.datasetName = captureName;
				
				// Override the API endpoint for captures by temporarily modifying the fetch URL
				const originalFetch = window.fetch;
				window.fetch = function(url, options) {
					if (url.includes(`/users/download-item/dataset/${captureUuid}/`)) {
						url = `/users/download-item/capture/${captureUuid}/`;
					}
					return originalFetch(url, options);
				};
				
				// Restore fetch after modal is hidden
				const modal = document.getElementById('webDownloadModal');
				const restoreFetch = () => {
					window.fetch = originalFetch;
					modal.removeEventListener('hidden.bs.modal', restoreFetch);
				};
				modal.addEventListener('hidden.bs.modal', restoreFetch);
			}
			
			// Show the modal
			window.showWebDownloadModal(captureUuid, captureName);
		} else {
			console.error("Web download modal not available");
			this.showToast("Download functionality not available", "error");
		}
	}

	/**
	 * Open custom modal
	 * @param {string} modalId - Modal ID
	 */
	openCustomModal(modalId) {
		const modal = document.getElementById(modalId);
		if (modal) {
			const bootstrapModal = new bootstrap.Modal(modal);
			bootstrapModal.show();
		}
	}

	/**
	 * Close custom modal
	 * @param {string} modalId - Modal ID
	 */
	closeCustomModal(modalId) {
		const modal = document.getElementById(modalId);
		if (modal) {
			const bootstrapModal = bootstrap.Modal.getInstance(modal);
			if (bootstrapModal) {
				bootstrapModal.hide();
			}
		}
	}

	/**
	 * Show toast notification - Wrapper for global showAlert
	 * @param {string} message - Toast message
	 * @param {string} type - Toast type (success, danger, warning, info)
	 */
	showToast(message, type = "success") {
		// Map DownloadActionManager types to showAlert types
		const mappedType = type === "danger" ? "error" : type;
		
		// Use the global showAlert function from HTMLInjectionManager
		if (window.showAlert) {
			window.showAlert(message, mappedType);
		} else {
			console.error("Global showAlert function not available");
		}
	}

	/**
	 * Initialize download buttons for dynamically loaded content
	 * @param {Element} container - Container element to search within
	 */
	initializeDownloadButtonsForContainer(container) {
		// Initialize dataset download buttons in the container
		const datasetDownloadButtons = container.querySelectorAll(".download-dataset-btn");
		datasetDownloadButtons.forEach((button) => {
			if (!button.dataset.downloadSetup) {
				button.dataset.downloadSetup = "true";
				button.addEventListener("click", (e) => {
					e.preventDefault();
					e.stopPropagation();

					const datasetUuid = button.getAttribute("data-dataset-uuid");
					const datasetName = button.getAttribute("data-dataset-name");

					if (!this.permissions.canDownload()) {
						this.showToast("You don't have permission to download this dataset", "warning");
						return;
					}

					this.handleDatasetDownload(datasetUuid, datasetName, button);
				});
			}
		});

		// Initialize capture download buttons in the container
		const captureDownloadButtons = container.querySelectorAll(".download-capture-btn");
		captureDownloadButtons.forEach((button) => {
			if (!button.dataset.downloadSetup) {
				button.dataset.downloadSetup = "true";
				button.addEventListener("click", (e) => {
					e.preventDefault();
					e.stopPropagation();

					const captureUuid = button.getAttribute("data-capture-uuid");
					const captureName = button.getAttribute("data-capture-name");

					if (!this.permissions.canDownload()) {
						this.showToast("You don't have permission to download this capture", "warning");
						return;
					}

					this.handleCaptureDownload(captureUuid, captureName, button);
				});
			}
		});
	}

	/**
	 * Check if user can download specific item
	 * @param {Object} item - Item object
	 * @returns {boolean} Whether user can download
	 */
	canDownloadItem(item) {
		// Check basic download permission
		if (!this.permissions.canDownload()) {
			return false;
		}

		// Additional item-specific checks can be added here
		// For example, checking if item is public, if user owns it, etc.
		
		return true;
	}

	/**
	 * Cleanup resources
	 */
	cleanup() {
		// Remove event listeners and clean up any resources
		const downloadButtons = document.querySelectorAll(".download-dataset-btn, .download-capture-btn");
		downloadButtons.forEach((button) => {
			button.removeEventListener("click", this.handleDatasetDownload);
			button.removeEventListener("click", this.handleCaptureDownload);
		});
	}
}

// Make class available globally
window.DownloadActionManager = DownloadActionManager;
