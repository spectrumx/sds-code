/**
 * Download Action Manager
 * Handles all download-related actions
 */

function msToHms(ms) {
	const n = Number(ms);
	if (!Number.isFinite(n) || n < 0) return "0:00:00.000";
	const totalSec = Math.floor(n / 1000);
	const h = Math.floor(totalSec / 3600);
	const m = Math.floor((totalSec % 3600) / 60);
	const s = totalSec % 60;
	const decimalMs = n % 1000;
	const hms = [h, m, s].map((v) => String(v).padStart(2, "0")).join(":");
	return hms + "." + String(decimalMs).padStart(3, "0");
}

function formatBytes(bytes) {
	const n = Number(bytes);
	if (!Number.isFinite(n) || n < 0) return "0 bytes";
	if (n === 0) return "0 bytes";
	const units = ["bytes", "KB", "MB", "GB"];
	let i = 0;
	let v = n;
	while (v >= 1024 && i < units.length - 1) {
		v /= 1024;
		i++;
	}
	return (i === 0 ? v : v.toFixed(2)) + " " + units[i];
}

function formatUtcRange(startEpochSec, startMs, endMs) {
	if (!Number.isFinite(startEpochSec)) return "—";
	const startDate = new Date(startEpochSec * 1000 + startMs);
	const endDate = new Date(startEpochSec * 1000 + endMs);
	const pad2 = (x) => String(x).padStart(2, "0");
	const fmt = (d) =>
		pad2(d.getUTCHours()) +
		":" +
		pad2(d.getUTCMinutes()) +
		":" +
		pad2(d.getUTCSeconds()) +
		" " +
		pad2(d.getUTCMonth() + 1) +
		"/" +
		pad2(d.getUTCDate()) +
		"/" +
		d.getUTCFullYear();
	return fmt(startDate) + " - " + fmt(endDate) + " (UTC)";
}

/** Format ms from capture start as datetime-local value (local time). */
function msToDatetimeLocal(captureStartEpochSec, ms) {
	if (!Number.isFinite(captureStartEpochSec) || !Number.isFinite(ms)) return "";
	const d = new Date(captureStartEpochSec * 1000 + ms);
	const pad2 = (x) => String(x).padStart(2, "0");
	const pad3 = (x) => String(x).padStart(3, "0");
	return (
		d.getFullYear() +
		"-" +
		pad2(d.getMonth() + 1) +
		"-" +
		pad2(d.getDate()) +
		"T" +
		pad2(d.getHours()) +
		":" +
		pad2(d.getMinutes()) +
		":" +
		pad2(d.getSeconds()) +
		"." +
		pad3(d.getMilliseconds())
	);
}

/** Parse datetime-local value to ms from capture start (UTC epoch sec). */
function datetimeLocalToMs(captureStartEpochSec, valueStr) {
	if (!Number.isFinite(captureStartEpochSec) || !valueStr || !valueStr.trim()) return NaN;
	const d = new Date(valueStr.trim());
	if (Number.isNaN(d.getTime())) return NaN;
	return d.getTime() - captureStartEpochSec * 1000;
}

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

		// Web download modal (dataset + capture)
		this.initializeWebDownloadModal();
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
	 * Initialize web download modal: confirm button click and modal hidden handler.
	 * Exposes showWebDownloadModal on window for template callbacks.
	 */
	initializeWebDownloadModal() {
		const webDownloadModal = document.getElementById("webDownloadModal");
		const confirmWebDownloadBtn = document.getElementById("confirmWebDownloadBtn");
		if (!webDownloadModal || !confirmWebDownloadBtn) return;

		confirmWebDownloadBtn.addEventListener("click", () => {
			const itemType = confirmWebDownloadBtn.dataset.itemType || "dataset";
			const uuid = confirmWebDownloadBtn.dataset.itemUuid || confirmWebDownloadBtn.dataset.datasetUuid;

			if (!uuid) return;

			const startTimeInput = document.getElementById("startTime");
			const endTimeInput = document.getElementById("endTime");
			const startEntry = document.getElementById("startTimeEntry");
			const endEntry = document.getElementById("endTimeEntry");
			const modalEl = document.getElementById("webDownloadModal");

			if (startEntry && endEntry && modalEl && modalEl.dataset.durationMs) {
				const entryStart = startEntry.value.trim();
				const entryEnd = endEntry.value.trim();
				if (entryStart !== "" || entryEnd !== "") {
					const durationMs = parseInt(modalEl.dataset.durationMs, 10);
					const startMs = entryStart === "" ? 0 : parseInt(entryStart, 10);
					const endMs = entryEnd === "" ? durationMs : parseInt(entryEnd, 10);
					if (
						!Number.isFinite(startMs) ||
						!Number.isFinite(endMs) ||
						startMs < 0 ||
						endMs > durationMs ||
						startMs >= endMs
					) {
						this.showToast(
							"Please enter valid start/end times (0 ≤ start < end ≤ " + durationMs + " ms).",
							"warning",
						);
						return;
					}
					if (startTimeInput) startTimeInput.value = String(startMs);
					if (endTimeInput) endTimeInput.value = String(endMs);
				}
			}

			const labels = this.getWebDownloadModalLabels(itemType);
			confirmWebDownloadBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Processing...';
			confirmWebDownloadBtn.disabled = true;

			const url = "/users/download-item/" + itemType + "/" + uuid + "/";
			const headers = {
				"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")?.value,
			};
			let body = null;
			if (startTimeInput && endTimeInput && startTimeInput.value && endTimeInput.value) {
				headers["Content-Type"] = "application/x-www-form-urlencoded";
				body = new URLSearchParams({
					start_time: startTimeInput.value,
					end_time: endTimeInput.value,
				});
			} else {
				headers["Content-Type"] = "application/json";
			}

			fetch(url, { method: "POST", headers, body })
				.then((response) => {
					const contentType = response.headers.get("content-type");
					if (contentType && contentType.includes("application/json")) {
						return response.json();
					}
					return response.text().then((text) => {
						throw new Error("Server returned non-JSON response: " + text);
					});
				})
				.then((data) => {
					if (data.success === true) {
						this.showToast(
							data.message ||
								"Download request submitted successfully! You will receive an email when ready.",
							"success",
						);
						const modal = bootstrap.Modal.getInstance(webDownloadModal);
						if (modal) modal.hide();
					} else {
						this.showToast(
							"Error requesting download: " + (data.message || "Unknown error"),
							"danger",
						);
					}
				})
				.catch((error) => {
					console.error("Download error:", error);
					this.showToast(
						error.message || "An error occurred while processing your request.",
						"danger",
					);
				})
				.finally(() => {
					confirmWebDownloadBtn.innerHTML =
						'<i class="bi bi-download"></i> ' + labels.confirmText;
					confirmWebDownloadBtn.disabled = false;
				});
		});

		webDownloadModal.addEventListener("hidden.bs.modal", () => {
			confirmWebDownloadBtn.dataset.itemType = "";
			confirmWebDownloadBtn.dataset.itemUuid = "";
			confirmWebDownloadBtn.dataset.itemName = "";
			confirmWebDownloadBtn.dataset.datasetUuid = "";
			confirmWebDownloadBtn.dataset.datasetName = "";
			const nameEl = document.getElementById("webDownloadDatasetName");
			if (nameEl) nameEl.textContent = "";
		});

		window.showWebDownloadModal = (a1, a2) => {
			const options =
				typeof a1 === "string" && a2 !== undefined
					? { itemType: "dataset", uuid: a1, name: a2 }
					: a1;
			this.showWebDownloadModal(options);
		};
	}

	/**
	 * Open web download modal for a dataset or capture.
	 * @param {{ itemType?: string, uuid: string, name?: string }} options - itemType 'dataset'|'capture', uuid, name
	 */
	showWebDownloadModal(options) {
		const { itemType = "dataset", uuid, name } = options || {};
		const nameEl = document.getElementById("webDownloadDatasetName");
		const confirmBtn = document.getElementById("confirmWebDownloadBtn");
		const modalEl = document.getElementById("webDownloadModal");
		const titleEl = document.getElementById("webDownloadModalLabel");

		if (nameEl) nameEl.textContent = name || "";
		if (confirmBtn) {
			confirmBtn.dataset.itemType = itemType;
			confirmBtn.dataset.itemUuid = uuid || "";
			confirmBtn.dataset.itemName = name || "";
		}
		// Update title and button text from item type
		const labels = this.getWebDownloadModalLabels(itemType);
		if (titleEl && window.DOMUtils) {
			window.DOMUtils.renderContent(titleEl, { icon: "download", text: labels.title });
		}
		if (confirmBtn && window.DOMUtils) {
			window.DOMUtils.renderContent(confirmBtn, { icon: "download", text: labels.confirmText });
		}
		if (modalEl && window.bootstrap) {
			new bootstrap.Modal(modalEl).show();
		}
	}

	/**
	 * Initialize or update the capture download temporal slider. Call before
     * showing the modal when opening for a capture with known bounds.
     * @param {number} durationMs - Total capture duration in milliseconds
     * @param {number} fileCadenceMs - File cadence in milliseconds (step)
     * @param {Object} opts - Optional: { perDataFileSize, totalSize, dataFilesCount, totalFilesCount, dataFilesTotalSize, captureUuid, captureStartEpochSec }
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
		var startDateTimeEntry = document.getElementById('startDateTimeEntry');
		var endDateTimeEntry = document.getElementById('endDateTimeEntry');
		var rangeHintEl = document.getElementById('temporalRangeHint');
		var sizeWarningEl = document.getElementById('temporalFilterSizeWarning');
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
		var dataFilesTotalSize = Number(opts.dataFilesTotalSize);
		if (!Number.isFinite(dataFilesTotalSize) || dataFilesTotalSize < 0) {
			dataFilesTotalSize = perDataFileSize * dataFilesCount;
		}
		var metadataFilesTotalSize = totalSize - dataFilesTotalSize;
		if (metadataFilesTotalSize < 0) metadataFilesTotalSize = 0;
		var metadataFilesCount = Math.max(0, totalFilesCount - dataFilesCount);
		var captureUuid = opts.captureUuid != null ? String(opts.captureUuid) : '';
		var captureStartEpochSec = Number(opts.captureStartEpochSec);
		if (totalSize > 0 && dataFilesTotalSize > totalSize) {
			console.warn(
				'[DownloadActionManager] data files total size exceeds total size (backend/query inconsistency).',
				{ captureUuid: captureUuid || '(unknown)', totalSize, dataFilesTotalSize, perDataFileSize, dataFilesCount }
			);
			if (sizeWarningEl) {
				sizeWarningEl.classList.remove('d-none');
			}
			dataFilesTotalSize = totalSize;
			metadataFilesTotalSize = 0;
		} else if (sizeWarningEl) {
			sizeWarningEl.classList.add('d-none');
		}
		if (webDownloadModal) {
			webDownloadModal.dataset.durationMs = String(Math.round(durationMs));
			webDownloadModal.dataset.fileCadenceMs = String(fileCadenceMs);
			webDownloadModal.dataset.captureStartEpochSec = Number.isFinite(captureStartEpochSec) ? String(captureStartEpochSec) : '';
		}
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
		var hasEpoch = Number.isFinite(captureStartEpochSec);
		if (startDateTimeEntry) {
			startDateTimeEntry.value = '';
			startDateTimeEntry.disabled = !hasEpoch;
		}
		if (endDateTimeEntry) {
			endDateTimeEntry.value = '';
			endDateTimeEntry.disabled = !hasEpoch;
		}
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
			if (hasEpoch) {
				if (startDateTimeEntry) startDateTimeEntry.value = msToDatetimeLocal(captureStartEpochSec, startMs);
				if (endDateTimeEntry) endDateTimeEntry.value = msToDatetimeLocal(captureStartEpochSec, endMs);
			}
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
		if (hasEpoch && startDateTimeEntry && endDateTimeEntry) {
			startDateTimeEntry.value = msToDatetimeLocal(captureStartEpochSec, 0);
			endDateTimeEntry.value = msToDatetimeLocal(captureStartEpochSec, durationMs);
			startDateTimeEntry.disabled = false;
			endDateTimeEntry.disabled = false;
		}

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
		function syncFromDateTimeEntries() {
			if (!hasEpoch || !sliderEl.noUiSlider || !startDateTimeEntry || !endDateTimeEntry) return;
			var startMs = datetimeLocalToMs(captureStartEpochSec, startDateTimeEntry.value);
			var endMs = datetimeLocalToMs(captureStartEpochSec, endDateTimeEntry.value);
			if (Number.isNaN(startMs) || Number.isNaN(endMs)) return;
			startMs = Math.max(0, Math.min(startMs, durationMs));
			endMs = Math.max(0, Math.min(endMs, durationMs));
			if (startMs >= endMs) endMs = Math.min(startMs + fileCadenceMs, durationMs);
			sliderEl.noUiSlider.set([startMs, endMs]);
		}
		if (startTimeEntry) startTimeEntry.addEventListener('change', syncSliderFromEntries);
		if (endTimeEntry) endTimeEntry.addEventListener('change', syncSliderFromEntries);
		if (startDateTimeEntry) startDateTimeEntry.addEventListener('change', syncFromDateTimeEntries);
		if (endDateTimeEntry) endDateTimeEntry.addEventListener('change', syncFromDateTimeEntries);
	}

	/**
	 * Labels for web download modal by item type (dataset vs capture).
	 * @param {string} itemType - 'dataset' or 'capture'
	 * @returns {{ title: string, confirmText: string }}
	 */
	getWebDownloadModalLabels(itemType) {
		const t = (itemType || "dataset").toLowerCase();
		return {
			title: t === "capture" ? "Download Capture" : "Download Dataset",
			confirmText:
				t === "capture" ? "Yes, Download Capture" : "Yes, Download Dataset",
		};
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

		const labels = this.getWebDownloadModalLabels("capture");
		const modalTitleElement = document.getElementById("webDownloadModalLabel");
		const modalNameElement = document.getElementById("webDownloadDatasetName");
		const confirmBtn = document.getElementById("confirmWebDownloadBtn");

		if (modalTitleElement) {
			await window.DOMUtils.renderContent(modalTitleElement, {
				icon: "download",
				text: labels.title,
			});
		}

		const newConfirmBtn = confirmBtn.cloneNode(true);
		confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

		if (confirmBtn) {
			await window.DOMUtils.renderContent(confirmBtn, {
				icon: "download",
				text: labels.confirmText,
			});
			confirmBtn.dataset.itemType = "capture";
			confirmBtn.dataset.itemUuid = captureUuid;
			confirmBtn.dataset.itemName = captureName || "Unnamed Capture";
		}

		// Initialize temporal slider from button data attributes (clears or builds slider)
		const durationMs = parseInt(button.getAttribute("data-length-of-capture-ms"), 10);
		const fileCadenceMs = parseInt(button.getAttribute("data-file-cadence-ms"), 10);
		const perDataFileSize = parseFloat(button.getAttribute("data-per-data-file-size"), 10);
		const totalSize = parseInt(button.getAttribute("data-total-size"), 10);
		const dataFilesCount = parseInt(button.getAttribute("data-data-files-count"), 10);
		const totalFilesCount = parseInt(button.getAttribute("data-total-files-count"), 10);
		const dataFilesTotalSizeRaw = button.getAttribute("data-data-files-total-size");
		const dataFilesTotalSize = dataFilesTotalSizeRaw !== null && dataFilesTotalSizeRaw !== '' ? parseInt(dataFilesTotalSizeRaw, 10) : NaN;
		const captureStartEpochSec = parseInt(button.getAttribute("data-capture-start-epoch-sec"), 10);
		const captureUuid = button.getAttribute("data-capture-uuid") || undefined;
		this.initializeCaptureDownloadSlider(
			Number.isNaN(durationMs) ? 0 : durationMs,
			Number.isNaN(fileCadenceMs) ? 1000 : fileCadenceMs,
			{
				perDataFileSize: Number.isNaN(perDataFileSize) ? 0 : perDataFileSize,
				totalSize: Number.isNaN(totalSize) ? 0 : totalSize,
				dataFilesCount: Number.isNaN(dataFilesCount) ? 0 : dataFilesCount,
				totalFilesCount: Number.isNaN(totalFilesCount) ? 0 : totalFilesCount,
				dataFilesTotalSize: Number.isNaN(dataFilesTotalSize) ? undefined : dataFilesTotalSize,
				captureUuid: captureUuid,
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
