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

		// Initialize web download modal buttons
		this.initializeWebDownloadButtons();

		// Initialize SDK download modal buttons
		this.initializeSDKDownloadButtons();
	}

	/**
	 * Initialize dataset download buttons
	 */
	initializeDatasetDownloadButtons() {
		const downloadButtons = document.querySelectorAll(".download-dataset-btn");

		for (const button of downloadButtons) {
			// Prevent duplicate event listener attachment
			if (button.dataset.downloadSetup === "true") {
				continue;
			}
			button.dataset.downloadSetup = "true";

			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();

				const datasetUuid = button.getAttribute("data-dataset-uuid");
				const datasetName = button.getAttribute("data-dataset-name");

				if (!this.permissions.canDownload()) {
					this.showToast(
						"You don't have permission to download this dataset",
						"warning",
					);
					return;
				}

				this.handleDatasetDownload(datasetUuid, datasetName, button);
			});
		}
	}

	/**
	 * Initialize capture download buttons
	 */
	initializeCaptureDownloadButtons() {
		const downloadButtons = document.querySelectorAll(".download-capture-btn");

		for (const button of downloadButtons) {
			// Prevent duplicate event listener attachment
			if (button.dataset.downloadSetup === "true") {
				continue;
			}
			button.dataset.downloadSetup = "true";

			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();

				const captureUuid = button.getAttribute("data-capture-uuid");

				if (!this.permissions.canDownload()) {
					this.showToast(
						"You don't have permission to download this capture",
						"warning",
					);
					return;
				}

				this.handleCaptureDownload(captureUuid, button);
			});
		}
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
		window.DOMUtils.openModal("downloadModal");

		// Handle confirm download
		const confirmBtn = document.getElementById("confirmDownloadBtn");
		if (!confirmBtn) return;

		// Remove any existing event listeners
		const newConfirmBtn = confirmBtn.cloneNode(true);
		confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

		newConfirmBtn.onclick = async () => {
			// Close modal first
			window.DOMUtils.closeModal("downloadModal");

			// Show loading state
			const originalContent = button.innerHTML;
			await window.DOMUtils.renderLoading(button, "Processing...", {
				format: "spinner",
				size: "sm",
			});
			button.disabled = true;

			try {
				const response = await window.APIClient.post(
					`/users/download-item/dataset/${datasetUuid}/`,
					{},
				);

				if (response.success === true) {
					await window.DOMUtils.renderContent(button, {
						icon: "check-circle",
						color: "success",
						text: "Download Requested",
					});
					this.showToast(
						response.message ||
							"Download request submitted successfully! You will receive an email when ready.",
						"success",
					);
				} else {
					await window.DOMUtils.renderContent(button, {
						icon: "exclamation-triangle",
						color: "danger",
						text: "Request Failed",
					});
					this.showToast(
						response.message || "Download request failed. Please try again.",
						"danger",
					);
				}
			} catch (error) {
				console.error("Download error:", error);
				await window.DOMUtils.renderContent(button, {
					icon: "exclamation-triangle",
					color: "danger",
					text: "Request Failed",
				});
				this.showToast(
					error.message || "An error occurred while processing your request.",
					"danger",
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

	/**
	 * Handle capture download (modal copy comes from web_download_modal.html)
	 * @param {string} captureUuid - Capture UUID
	 * @param {Element} [button] - Optional row action button for loading state
	 */
	async handleCaptureDownload(captureUuid, button) {
		const modalId = `webDownloadModal-${captureUuid}`;
		const modal = document.getElementById(modalId);
		if (!modal) {
			console.warn(`Web download modal not found for capture ${captureUuid}`);
			return;
		}

		const confirmBtn = document.getElementById(
			`confirmWebDownloadBtn-${captureUuid}`,
		);

		if (!confirmBtn) {
			console.warn(
				`Web download confirm button not found for capture ${captureUuid}`,
			);
			return;
		}

		const newConfirmBtn = confirmBtn.cloneNode(true);
		confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

		const originalRowButtonContent = button?.innerHTML;

		newConfirmBtn.onclick = async () => {
			window.DOMUtils.closeModal(modalId);

			if (button) {
				await window.DOMUtils.renderLoading(button, "Processing...", {
					format: "spinner",
					size: "sm",
				});
				button.disabled = true;
			}

			try {
				const response = await window.APIClient.post(
					`/users/download-item/capture/${captureUuid}/`,
					{},
				);

				if (response.success === true) {
					if (button) {
						await window.DOMUtils.renderContent(button, {
							icon: "check-circle",
							color: "success",
							text: "Download Requested",
						});
					}
					this.showToast(
						response.message ||
							"Download request submitted successfully! You will receive an email when ready.",
						"success",
					);
				} else {
					if (button) {
						await window.DOMUtils.renderContent(button, {
							icon: "exclamation-triangle",
							color: "danger",
							text: "Request Failed",
						});
					}
					this.showToast(
						response.message || "Download request failed. Please try again.",
						"danger",
					);
				}
			} catch (error) {
				console.error("Download error:", error);
				if (button) {
					await window.DOMUtils.renderContent(button, {
						icon: "exclamation-triangle",
						color: "danger",
						text: "Request Failed",
					});
				}
				this.showToast(
					error.message || "An error occurred while processing your request.",
					"danger",
				);
			} finally {
				if (button && originalRowButtonContent !== undefined) {
					setTimeout(() => {
						button.innerHTML = originalRowButtonContent;
						button.disabled = false;
					}, 3000);
				}
			}
		};

		window.DOMUtils.openModal(modalId);
	}

	/**
	 * Initialize web download modal buttons
	 */
	initializeWebDownloadButtons() {
		// Find all web download buttons (by data attribute or class)
		const webDownloadButtons = document.querySelectorAll(
			'[data-action="web-download"], .web-download-btn',
		);

		for (const button of webDownloadButtons) {
			// Prevent duplicate event listener attachment
			if (button.dataset.downloadSetup === "true") {
				continue;
			}
			button.dataset.downloadSetup = "true";

			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();

				const datasetUuid = button.getAttribute("data-dataset-uuid");

				if (!datasetUuid) {
					console.warn("Web download button missing dataset-uuid attribute");
					return;
				}

				this.openWebDownloadModal(datasetUuid);
			});
		}
	}

	/**
	 * Initialize SDK download modal buttons
	 */
	initializeSDKDownloadButtons() {
		// Find all SDK download buttons (by data attribute or class)
		const sdkDownloadButtons = document.querySelectorAll(
			'[data-action="sdk-download"], .sdk-download-btn',
		);

		for (const button of sdkDownloadButtons) {
			// Prevent duplicate event listener attachment
			if (button.dataset.downloadSetup === "true") {
				continue;
			}
			button.dataset.downloadSetup = "true";

			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();

				const datasetUuid = button.getAttribute("data-dataset-uuid");

				if (!datasetUuid) {
					console.warn("SDK download button missing dataset-uuid attribute");
					return;
				}

				this.openSDKDownloadModal(datasetUuid);
			});
		}
	}

	/**
	 * Open web download modal for a specific dataset (labels from web_download_modal.html)
	 * @param {string} datasetUuid - Dataset UUID
	 */
	openWebDownloadModal(datasetUuid) {
		const modalId = `webDownloadModal-${datasetUuid}`;
		const modal = document.getElementById(modalId);
		if (!modal) {
			console.warn(`Web download modal not found for dataset ${datasetUuid}`);
			return;
		}

		const confirmBtn = document.getElementById(
			`confirmWebDownloadBtn-${datasetUuid}`,
		);

		if (!confirmBtn) {
			console.warn(`Confirm button not found for dataset ${datasetUuid}`);
			return;
		}

		// Remove any existing event listeners by cloning
		const newConfirmBtn = confirmBtn.cloneNode(true);
		confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

		// Attach download handler
		newConfirmBtn.onclick = async () => {
			// Close modal first
			window.DOMUtils.closeModal(modalId);

			// Show loading state
			const originalContent = newConfirmBtn.innerHTML;
			await window.DOMUtils.renderLoading(newConfirmBtn, "Processing...", {
				format: "spinner",
				size: "sm",
			});
			newConfirmBtn.disabled = true;

			try {
				const response = await window.APIClient.post(
					`/users/download-item/dataset/${datasetUuid}/`,
					{},
				);

				if (response.success === true) {
					await window.DOMUtils.renderContent(newConfirmBtn, {
						icon: "check-circle",
						color: "success",
						text: "Download Requested",
					});
					this.showToast(
						response.message ||
							"Download request submitted successfully! You will receive an email when ready.",
						"success",
					);
				} else {
					await window.DOMUtils.renderContent(newConfirmBtn, {
						icon: "exclamation-triangle",
						color: "danger",
						text: "Request Failed",
					});
					this.showToast(
						response.message || "Download request failed. Please try again.",
						"danger",
					);
				}
			} catch (error) {
				console.error("Download error:", error);
				await window.DOMUtils.renderContent(newConfirmBtn, {
					icon: "exclamation-triangle",
					color: "danger",
					text: "Request Failed",
				});
				this.showToast(
					error.message || "An error occurred while processing your request.",
					"danger",
				);
			} finally {
				// Reset button after 3 seconds
				setTimeout(() => {
					newConfirmBtn.innerHTML = originalContent;
					newConfirmBtn.disabled = false;
				}, 3000);
			}
		};

		// Use centralized openModal method
		window.DOMUtils.openModal(modalId);
	}

	/**
	 * Open SDK download modal for a specific dataset
	 * @param {string} datasetUuid - Dataset UUID
	 */
	openSDKDownloadModal(datasetUuid) {
		const modalId = `sdkDownloadModal-${datasetUuid}`;
		const modal = document.getElementById(modalId);
		if (!modal) {
			console.warn(`SDK download modal not found for dataset ${datasetUuid}`);
			return;
		}

		// Re-initialize Prism syntax highlighting when modal is shown
		modal.addEventListener(
			"shown.bs.modal",
			() => {
				if (typeof Prism !== "undefined") {
					// Highlight only within this modal
					Prism.highlightAllUnder(modal);
				}
			},
			{ once: true },
		);

		// Use centralized openModal method
		window.DOMUtils.openModal(modalId);
	}

	/**
	 * Show toast notification - Wrapper for global showAlert
	 * @param {string} message - Toast message
	 * @param {string} type - Toast type (success, danger, warning, info)
	 */
	showToast(message, type = "success") {
		// Map DownloadActionManager types to DOMUtils.showAlert types
		const mappedType = type === "danger" ? "error" : type;

		// Use DOMUtils.showAlert for toast notifications
		if (window.DOMUtils) {
			window.DOMUtils.showAlert(message, mappedType);
		} else {
			console.error("DOMUtils not available");
		}
	}

	/**
	 * Initialize download buttons for dynamically loaded content
	 * @param {Element} container - Container element to search within
	 */
	initializeDownloadButtonsForContainer(container) {
		// Initialize dataset download buttons in the container
		const datasetDownloadButtons = container.querySelectorAll(
			".download-dataset-btn",
		);
		for (const button of datasetDownloadButtons) {
			if (!button.dataset.downloadSetup) {
				button.dataset.downloadSetup = "true";
				button.addEventListener("click", (e) => {
					e.preventDefault();
					e.stopPropagation();

					const datasetUuid = button.getAttribute("data-dataset-uuid");
					const datasetName = button.getAttribute("data-dataset-name");

					if (!this.permissions.canDownload()) {
						this.showToast(
							"You don't have permission to download this dataset",
							"warning",
						);
						return;
					}

					this.handleDatasetDownload(datasetUuid, datasetName, button);
				});
			}
		}

		// Initialize capture download buttons in the container
		const captureDownloadButtons = container.querySelectorAll(
			".download-capture-btn",
		);
		for (const button of captureDownloadButtons) {
			if (!button.dataset.downloadSetup) {
				button.dataset.downloadSetup = "true";
				button.addEventListener("click", (e) => {
					e.preventDefault();
					e.stopPropagation();

					const captureUuid = button.getAttribute("data-capture-uuid");

					if (!this.permissions.canDownload()) {
						this.showToast(
							"You don't have permission to download this capture",
							"warning",
						);
						return;
					}

					this.handleCaptureDownload(captureUuid, button);
				});
			}
		}
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
	 * Close a modal by id (delegates to DOMUtils.closeModal)
	 * @param {string} modalId - Modal element id
	 */
	closeCustomModal(modalId) {
		if (window.DOMUtils?.closeModal) {
			window.DOMUtils.closeModal(modalId);
		}
	}

	/**
	 * Cleanup resources
	 */
	cleanup() {
		// Remove event listeners and clean up any resources
		const downloadButtons = document.querySelectorAll(
			".download-dataset-btn, .download-capture-btn",
		);
		for (const button of downloadButtons) {
			button.removeEventListener("click", this.handleDatasetDownload);
			button.removeEventListener("click", this.handleCaptureDownload);
		}
	}
}

// Make class available globally
window.DownloadActionManager = DownloadActionManager;

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
	module.exports = { DownloadActionManager };
}
