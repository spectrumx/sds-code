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
				const captureName = button.getAttribute("data-capture-name");

				if (!this.permissions.canDownload()) {
					this.showToast(
						"You don't have permission to download this capture",
						"warning",
					);
					return;
				}

				this.handleCaptureDownload(captureUuid, captureName, button);
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
		var startTimeEntry = document.getElementById('startTimeEntry');
		var endTimeEntry = document.getElementById('endTimeEntry');
		var rangeHintEl = document.getElementById('temporalRangeHint');
		var webDownloadModal = document.getElementById('webDownloadModal');
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
		if (webDownloadModal) webDownloadModal.dataset.durationMs = String(Math.round(durationMs));
		if (rangeHintEl) rangeHintEl.textContent = '0 – ' + Math.round(durationMs) + ' ms';
		if (sliderEl.noUiSlider) {
			sliderEl.noUiSlider.destroy();
		}
		if (rangeLabel) rangeLabel.textContent = '—';
		if (totalFilesLabel) totalFilesLabel.textContent = '0 files';
		if (totalSizeLabel) totalSizeLabel.textContent = formatBytes(totalSize);
		if (dateTimeLabel) dateTimeLabel.textContent = '—';
		if (startTimeInput) startTimeInput.value = '';
		if (endTimeInput) endTimeInput.value = '';
		if (startTimeEntry) startTimeEntry.value = '';
		if (endTimeEntry) endTimeEntry.value = '';
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
			if (startTimeEntry) startTimeEntry.value = String(Math.round(startMs));
			if (endTimeEntry) endTimeEntry.value = String(Math.round(endMs));
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
		var startVal = '0';
		var endVal = String(durationMs);
		if (startTimeInput) startTimeInput.value = startVal;
		if (endTimeInput) endTimeInput.value = endVal;
		if (startTimeEntry) startTimeEntry.value = startVal;
		if (endTimeEntry) endTimeEntry.value = endVal;

		function syncSliderFromEntries() {
			if (!sliderEl.noUiSlider || !startTimeEntry || !endTimeEntry) return;
			var s = startTimeEntry.value.trim();
			var e = endTimeEntry.value.trim();
			var startMs = s === '' ? 0 : parseInt(s, 10);
			var endMs = e === '' ? durationMs : parseInt(e, 10);
			if (!Number.isFinite(startMs)) startMs = 0;
			if (!Number.isFinite(endMs)) endMs = durationMs;
			startMs = Math.max(0, Math.min(startMs, durationMs));
			endMs = Math.max(0, Math.min(endMs, durationMs));
			if (startMs >= endMs) endMs = Math.min(startMs + fileCadenceMs, durationMs);
			sliderEl.noUiSlider.set([startMs, endMs]);
		}
		if (startTimeEntry) startTimeEntry.addEventListener('change', syncSliderFromEntries);
		if (endTimeEntry) endTimeEntry.addEventListener('change', syncSliderFromEntries);
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
		if (!confirmBtn) return;

		// Remove any existing event listeners
		const newConfirmBtn = confirmBtn.cloneNode(true);
		confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

		newConfirmBtn.onclick = async () => {
			// Close modal first
			this.closeCustomModal("downloadModal");

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
	 * Handle capture download
	 * @param {string} captureUuid - Capture UUID
	 * @param {string} captureName - Capture name
	 * @param {Element} button - Download button element
	 */
	async handleCaptureDownload(captureUuid, captureName, button) {
		// Use the web download modal (same as datasets)
		if (!window.showWebDownloadModal) {
			console.error("Web download modal not available");
			this.showToast("Download functionality not available", "error");
			return;
		}

		// Update modal content for capture
		const modalTitleElement = document.getElementById("webDownloadModalLabel");
		const modalNameElement = document.getElementById("webDownloadDatasetName");
		const confirmBtn = document.getElementById("confirmWebDownloadBtn");

		if (modalTitleElement) {
			await window.DOMUtils.renderContent(modalTitleElement, {
				icon: "download",
				text: "Download Capture",
			});
		}

		if (modalNameElement) {
			modalNameElement.textContent = captureName || "Unnamed Capture";
		}

		if (confirmBtn) {
			// Update button text for capture
			await window.DOMUtils.renderContent(confirmBtn, {
				icon: "download",
				text: "Yes, Download Capture",
			});

			// Update the dataset UUID to capture UUID for the API call
			confirmBtn.dataset.datasetUuid = captureUuid;
			confirmBtn.dataset.datasetName = captureName;

			// Override the API endpoint for captures by temporarily modifying the fetch URL
			const originalFetch = window.fetch;
			window.fetch = (url, options) => {
				const modifiedUrl = url.includes(
					`/users/download-item/dataset/${captureUuid}/`,
				)
					? `/users/download-item/capture/${captureUuid}/`
					: url;
				return originalFetch(modifiedUrl, options);
			};

			// Restore fetch after modal is hidden
			const modal = document.getElementById("webDownloadModal");
			const restoreFetch = () => {
				window.fetch = originalFetch;
				modal.removeEventListener("hidden.bs.modal", restoreFetch);
			};
			modal.addEventListener("hidden.bs.modal", restoreFetch);
		}

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
	 * Open custom modal
	 * @param {string} modalId - Modal ID
	 */
	openCustomModal(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const bootstrapModal = new bootstrap.Modal(modal);
		bootstrapModal.show();
	}

	/**
	 * Close custom modal
	 * @param {string} modalId - Modal ID
	 */
	closeCustomModal(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const bootstrapModal = bootstrap.Modal.getInstance(modal);
		if (!bootstrapModal) return;

		bootstrapModal.hide();
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
					const captureName = button.getAttribute("data-capture-name");

					if (!this.permissions.canDownload()) {
						this.showToast(
							"You don't have permission to download this capture",
							"warning",
						);
						return;
					}

					this.handleCaptureDownload(captureUuid, captureName, button);
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
