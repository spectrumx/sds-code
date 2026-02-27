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
     * Initialize or update the capture download temporal slider. Call before
     * showing the modal when opening for a capture with known bounds.
     * @param {number} durationMs - Total capture duration in milliseconds
     * @param {number} fileCadenceMs - File cadence in milliseconds (step)
     * @param {Object} opts - Optional: { perDataFileSize, totalSize, dataFilesCount, totalFilesCount, captureStartEpochSec }
     */
	initializeCaptureDownloadSlider(durationMs, fileCadenceMs, opts) {
		opts = opts || {};
		var sliderEl = document.getElementById('temporalFilterSlider');
		var rangeLabel = document.getElementById('temporalFilterRangeLabel');
		var totalFilesLabel = document.getElementById('totalFilesLabel');
		var metadataFilesLabel = document.getElementById('metadataFilesLabel');
		var totalSizeLabel = document.getElementById('totalSizeLabel');
		var dateTimeLabel = document.getElementById('dateTimeLabel');
		var startTimeInput = document.getElementById('startTime');
		var endTimeInput = document.getElementById('endTime');
		if (!sliderEl || typeof noUiSlider === 'undefined') return;
		durationMs = Number(durationMs);
		if (!Number.isFinite(durationMs) || durationMs < 0) durationMs = 0;
		fileCadenceMs = Number(fileCadenceMs);
		if (!Number.isFinite(fileCadenceMs) || fileCadenceMs < 1) fileCadenceMs = 1000;
		var perDataFileSize = Number(opts.perDataFileSize) || 0;
		var totalSize = Number(opts.totalSize) || 0;
		var dataFilesCount = Number(opts.dataFilesCount) || 0;
		var totalFilesCount = Number(opts.totalFilesCount) || 0;
		var dataFilesTotalSize = perDataFileSize * dataFilesCount;
		var metadataFilesTotalSize = totalSize - dataFilesTotalSize;
		var metadataFilesCount = totalFilesCount - dataFilesCount;
		var captureStartEpochSec = Number(opts.captureStartEpochSec);
		if (sliderEl.noUiSlider) {
			sliderEl.noUiSlider.destroy();
		}
		if (rangeLabel) rangeLabel.textContent = '—';
		if (totalFilesLabel) totalFilesLabel.textContent = '0 files';
		if (totalSizeLabel) totalSizeLabel.textContent = formatBytes(totalSize);
		if (dateTimeLabel) dateTimeLabel.textContent = '—';
		if (startTimeInput) startTimeInput.value = '';
		if (endTimeInput) endTimeInput.value = '';
		if (durationMs <= 0) return;
		noUiSlider.create(sliderEl, {
			start: [0, durationMs],
			connect: true,
			step: fileCadenceMs,
			range: { min: 0, max: durationMs },
		});
		sliderEl.noUiSlider.on('update', function(values) {
			var startMs = Number(values[0]);
			var endMs = Number(values[1]);
			// the + 1 is to include the first file in the selection
			// as file cadence is the time between files, not the time of the file
			var filesInSelection = Math.round((endMs - startMs) / fileCadenceMs) + 1;
			if (rangeLabel) {
				rangeLabel.textContent = msToHms(startMs) + ' - ' + msToHms(endMs);
			}
			if (totalFilesLabel) {
				totalFilesLabel.textContent = dataFilesCount > 0
					? filesInSelection + ' of ' + dataFilesCount + ' files'
					: filesInSelection + ' files';
			}
			if (totalSizeLabel) {
				totalSizeLabel.textContent = formatBytes(
					(perDataFileSize * filesInSelection) + metadataFilesTotalSize
				);
			}
			if (dateTimeLabel && Number.isFinite(captureStartEpochSec)) {
				dateTimeLabel.textContent = formatUtcRange(captureStartEpochSec, startMs, endMs);
			}
			if (startTimeInput) startTimeInput.value = String(Math.round(startMs));
			if (endTimeInput) endTimeInput.value = String(Math.round(endMs));
		});
		if (rangeLabel) {
			rangeLabel.textContent = '0:00:00.000 - ' + msToHms(durationMs);
		}
		if (totalFilesLabel) {
			totalFilesLabel.textContent = dataFilesCount > 0
				? dataFilesCount + ' files'
				: '0 files';
		}
		if (metadataFilesLabel) {
			metadataFilesLabel.textContent = metadataFilesCount > 0
				? metadataFilesCount + ' files'
				: '0 files';
		}
		if (dateTimeLabel && Number.isFinite(captureStartEpochSec)) {
			dateTimeLabel.textContent = formatUtcRange(captureStartEpochSec, 0, durationMs);
		}
		if (startTimeInput) startTimeInput.value = '0';
		if (endTimeInput) endTimeInput.value = String(durationMs);
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

		// Initialize temporal slider from button data attributes (clears or builds slider)
		const durationMs = parseInt(button.getAttribute("data-length-of-capture-ms"), 10);
		const fileCadenceMs = parseInt(button.getAttribute("data-file-cadence-ms"), 10);
		const perDataFileSize = parseFloat(button.getAttribute("data-per-data-file-size"), 10);
		const totalSize = parseInt(button.getAttribute("data-total-size"), 10);
		const dataFilesCount = parseInt(button.getAttribute("data-data-files-count"), 10);
		const totalFilesCount = parseInt(button.getAttribute("data-total-files-count"), 10);
		const captureStartEpochSec = parseInt(button.getAttribute("data-capture-start-epoch-sec"), 10);
		this.initializeCaptureDownloadSlider(
			Number.isNaN(durationMs) ? 0 : durationMs,
			Number.isNaN(fileCadenceMs) ? 1000 : fileCadenceMs,
			{
				perDataFileSize: Number.isNaN(perDataFileSize) ? 0 : perDataFileSize,
				totalSize: Number.isNaN(totalSize) ? 0 : totalSize,
				dataFilesCount: Number.isNaN(dataFilesCount) ? 0 : dataFilesCount,
				totalFilesCount: Number.isNaN(totalFilesCount) ? 0 : totalFilesCount,
				captureStartEpochSec: Number.isNaN(captureStartEpochSec) ? undefined : captureStartEpochSec,
			},
		);

		// Show the modal
		this.openCustomModal("webDownloadModal");
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
