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
	return `${hms}.${String(decimalMs).padStart(3, "0")}`;
}

function formatUtcRange(startEpochSec, startMs, endMs) {
	if (!Number.isFinite(startEpochSec)) return "—";
	const startDate = new Date(startEpochSec * 1000 + startMs);
	const endDate = new Date(startEpochSec * 1000 + endMs);
	const pad2 = (x) => String(x).padStart(2, "0");
	const fmt = (d) =>
		`${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())} ${pad2(d.getUTCMonth() + 1)}/${pad2(d.getUTCDate())}/${d.getUTCFullYear()}`;
	return `${fmt(startDate)} - ${fmt(endDate)} (UTC)`;
}

/** Format ms from capture start as UTC string for display (Y-m-d H:i:s). */
function msToUtcString(captureStartEpochSec, ms) {
	if (!Number.isFinite(captureStartEpochSec) || !Number.isFinite(ms)) return "";
	const d = new Date(captureStartEpochSec * 1000 + ms);
	const pad2 = (x) => String(x).padStart(2, "0");
	return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}`;
}

/** Parse UTC date string (Y-m-d H:i:s or Y-m-d H:i) to epoch ms. */
function parseUtcStringToEpochMs(str) {
	if (!str || !str.trim()) return Number.NaN;
	const s = str.trim();
	const d = new Date(s.endsWith("Z") ? s : `${s.replace(" ", "T")}Z`);
	return Number.isFinite(d.getTime()) ? d.getTime() : Number.NaN;
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
		// Initialize web download modal buttons
		this.initializeWebDownloadButtons();

		// Initialize SDK download modal buttons
		this.initializeSDKDownloadButtons();
	}

	/**
	 * Initialize web download buttons on the table rows
	 */
	initializeWebDownloadButtons() {
		const downloadButtons = document.querySelectorAll(".web-download-btn");

		for (const button of downloadButtons) {
			// Prevent duplicate event listener attachment
			if (button.dataset.downloadSetup === "true") {
				continue;
			}
			button.dataset.downloadSetup = "true";

			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();

				const itemUuid = button.getAttribute("data-item-uuid");
				const itemType = button.getAttribute("data-item-type");

				if (!this.permissions.canDownload()) {
					this.showToast(
						`You don't have permission to download this ${itemType}`,
						"warning",
					);
					return;
				}

				this.initializeWebDownloadModal(itemUuid, itemType, button);
			});
		}
	}

	/**
	 * Initialize or update the capture download temporal slider. Call before
	 * showing the modal when opening for a capture with known bounds.
	 * @param {number} durationMs - Total capture duration in milliseconds
	 * @param {number} fileCadenceMs - File cadence in milliseconds (step)
	 * @param {Object} opts - Optional: { perDataFileSize, totalSize, dataFilesCount, totalFilesCount, dataFilesTotalSize, captureUuid, captureStartEpochSec }
	 */
	initializeCaptureDownloadSlider(modalId, durationMs, fileCadenceMs, opts) {
		const webDownloadModal = document.getElementById(modalId);
		if (!webDownloadModal) return;

		const resolvedOpts = opts ?? {};
		const q = (id) => webDownloadModal.querySelector(`#${id}`);
		const sliderEl = q("temporalFilterSlider");
		const rangeLabel = q("temporalFilterRangeLabel");
		const totalFilesLabel = q("totalFilesLabel");
		const metadataFilesLabel = q("metadataFilesLabel");
		const totalSizeLabel = q("totalSizeLabel");
		const dateTimeLabel = q("dateTimeLabel");
		const startTimeInput = q("startTime");
		const endTimeInput = q("endTime");
		const startTimeEntry = q("startTimeEntry");
		const endTimeEntry = q("endTimeEntry");
		const startDateTimeEntry = q("startDateTimeEntry");
		const endDateTimeEntry = q("endDateTimeEntry");
		const rangeHintEl = q("temporalRangeHint");
		const sizeWarningEl = q("temporalFilterSizeWarning");
		if (!sliderEl || typeof noUiSlider === "undefined") return;
		const resolvedDurationMs = (() => {
			const n = Number(durationMs);
			return !Number.isFinite(n) || n < 0 ? 0 : n;
		})();
		const resolvedFileCadenceMs = (() => {
			const n = Number(fileCadenceMs);
			return !Number.isFinite(n) || n < 1 ? 1000 : n;
		})();
		const perDataFileSize = Number(resolvedOpts.perDataFileSize) || 0;
		const totalSize = Number(resolvedOpts.totalSize) || 0;
		const dataFilesCount = Number(resolvedOpts.dataFilesCount) || 0;
		const totalFilesCount = Number(resolvedOpts.totalFilesCount) || 0;
		let dataFilesTotalSize = Number(resolvedOpts.dataFilesTotalSize);
		if (!Number.isFinite(dataFilesTotalSize) || dataFilesTotalSize < 0) {
			dataFilesTotalSize = perDataFileSize * dataFilesCount;
		}
		let metadataFilesTotalSize = totalSize - dataFilesTotalSize;
		if (metadataFilesTotalSize < 0) metadataFilesTotalSize = 0;
		const metadataFilesCount = Math.max(0, totalFilesCount - dataFilesCount);
		const captureUuid =
			resolvedOpts.captureUuid != null ? String(resolvedOpts.captureUuid) : "";
		const captureStartEpochSec = Number(resolvedOpts.captureStartEpochSec);
		if (totalSize > 0 && dataFilesTotalSize > totalSize) {
			console.warn(
				"[DownloadActionManager] data files total size exceeds total size (backend/query inconsistency).",
				{
					captureUuid: captureUuid || "(unknown)",
					totalSize,
					dataFilesTotalSize,
					perDataFileSize,
					dataFilesCount,
				},
			);
			if (sizeWarningEl) {
				sizeWarningEl.classList.remove("d-none");
			}
			dataFilesTotalSize = totalSize;
			metadataFilesTotalSize = 0;
		} else if (sizeWarningEl) {
			sizeWarningEl.classList.add("d-none");
		}
		if (webDownloadModal) {
			webDownloadModal.dataset.durationMs = String(
				Math.round(resolvedDurationMs),
			);
			webDownloadModal.dataset.fileCadenceMs = String(resolvedFileCadenceMs);
			webDownloadModal.dataset.captureStartEpochSec = Number.isFinite(
				captureStartEpochSec,
			)
				? String(captureStartEpochSec)
				: "";
		}
		if (rangeHintEl)
			rangeHintEl.textContent = `0 – ${Math.round(resolvedDurationMs)} ms`;
		if (sliderEl.noUiSlider) {
			sliderEl.noUiSlider.destroy();
		}
		if (rangeLabel) rangeLabel.textContent = "—";
		if (totalFilesLabel) totalFilesLabel.textContent = "0 files";
		if (totalSizeLabel)
			totalSizeLabel.textContent = window.DOMUtils.formatFileSize(totalSize);
		if (dateTimeLabel) dateTimeLabel.textContent = "—";
		if (startTimeInput) startTimeInput.value = "";
		if (endTimeInput) endTimeInput.value = "";
		if (startTimeEntry) startTimeEntry.value = "";
		if (endTimeEntry) endTimeEntry.value = "";
		const hasEpoch = Number.isFinite(captureStartEpochSec);
		if (startDateTimeEntry) {
			startDateTimeEntry.value = "";
			startDateTimeEntry.disabled = !hasEpoch;
		}
		if (endDateTimeEntry) {
			endDateTimeEntry.value = "";
			endDateTimeEntry.disabled = !hasEpoch;
		}
		if (resolvedDurationMs <= 0) return;
		let fpStart = null;
		let fpEnd = null;
		const epochStart = captureStartEpochSec * 1000;
		const epochEnd = epochStart + resolvedDurationMs;
		if (
			hasEpoch &&
			typeof flatpickr !== "undefined" &&
			startDateTimeEntry &&
			endDateTimeEntry
		) {
			const fpOpts = {
				enableTime: true,
				enableSeconds: true,
				utc: true,
				dateFormat: "Y-m-d H:i:S",
				time_24hr: true,
				minDate: epochStart,
				maxDate: epochEnd,
				allowInput: true,
				static: true,
				appendTo: webDownloadModal || undefined,
			};
			flatpickr(
				startDateTimeEntry,
				Object.assign({}, fpOpts, {
					onChange: () => {
						syncFromDateTimeEntries();
					},
				}),
			);
			flatpickr(
				endDateTimeEntry,
				Object.assign({}, fpOpts, {
					onChange: () => {
						syncFromDateTimeEntries();
					},
				}),
			);
			fpStart = startDateTimeEntry._flatpickr;
			fpEnd = endDateTimeEntry._flatpickr;
			startDateTimeEntry.disabled = false;
			endDateTimeEntry.disabled = false;
		}
		noUiSlider.create(sliderEl, {
			start: [0, resolvedDurationMs],
			connect: true,
			step: resolvedFileCadenceMs,
			range: { min: 0, max: resolvedDurationMs },
		});
		sliderEl.noUiSlider.on("update", (values) => {
			const startMs = Number(values[0]);
			const endMs = Number(values[1]);
			// the + 1 is to include the first file in the selection
			// as file cadence is the time between files, not the time of the file
			const filesInSelection =
				Math.round((endMs - startMs) / resolvedFileCadenceMs) + 1;
			if (rangeLabel) {
				rangeLabel.textContent = `${msToHms(startMs)} - ${msToHms(endMs)}`;
			}
			if (totalFilesLabel) {
				totalFilesLabel.textContent =
					dataFilesCount > 0
						? `${filesInSelection} of ${dataFilesCount} files`
						: `${filesInSelection} files`;
			}
			if (totalSizeLabel) {
				totalSizeLabel.textContent = window.DOMUtils.formatFileSize(
					perDataFileSize * filesInSelection + metadataFilesTotalSize,
				);
			}
			if (dateTimeLabel && Number.isFinite(captureStartEpochSec)) {
				dateTimeLabel.textContent = formatUtcRange(
					captureStartEpochSec,
					startMs,
					endMs,
				);
			}
			if (startTimeInput) startTimeInput.value = String(Math.round(startMs));
			if (endTimeInput) endTimeInput.value = String(Math.round(endMs));
			if (startTimeEntry) startTimeEntry.value = String(Math.round(startMs));
			if (endTimeEntry) endTimeEntry.value = String(Math.round(endMs));
			if (hasEpoch) {
				if (fpStart && typeof fpStart.setDate === "function")
					fpStart.setDate(epochStart + startMs);
				else if (startDateTimeEntry)
					startDateTimeEntry.value = msToUtcString(
						captureStartEpochSec,
						startMs,
					);
				if (fpEnd && typeof fpEnd.setDate === "function")
					fpEnd.setDate(epochStart + endMs);
				else if (endDateTimeEntry)
					endDateTimeEntry.value = msToUtcString(captureStartEpochSec, endMs);
			}
		});
		if (rangeLabel) {
			rangeLabel.textContent = `0:00:00.000 - ${msToHms(resolvedDurationMs)}`;
		}
		if (totalFilesLabel) {
			totalFilesLabel.textContent =
				dataFilesCount > 0 ? `${dataFilesCount} files` : "0 files";
		}
		if (metadataFilesLabel) {
			metadataFilesLabel.textContent =
				metadataFilesCount > 0 ? `${metadataFilesCount} files` : "0 files";
		}
		if (dateTimeLabel && Number.isFinite(captureStartEpochSec)) {
			dateTimeLabel.textContent = formatUtcRange(
				captureStartEpochSec,
				0,
				resolvedDurationMs,
			);
		}
		const startVal = "0";
		const endVal = String(resolvedDurationMs);
		if (startTimeInput) startTimeInput.value = startVal;
		if (endTimeInput) endTimeInput.value = endVal;
		if (startTimeEntry) startTimeEntry.value = startVal;
		if (endTimeEntry) endTimeEntry.value = endVal;
		if (hasEpoch && startDateTimeEntry && endDateTimeEntry) {
			if (fpStart && typeof fpStart.setDate === "function")
				fpStart.setDate(epochStart);
			else startDateTimeEntry.value = msToUtcString(captureStartEpochSec, 0);
			if (fpEnd && typeof fpEnd.setDate === "function") fpEnd.setDate(epochEnd);
			else
				endDateTimeEntry.value = msToUtcString(
					captureStartEpochSec,
					resolvedDurationMs,
				);
			if (!fpStart) {
				startDateTimeEntry.disabled = false;
				endDateTimeEntry.disabled = false;
			}
		}

		function syncSliderFromEntries() {
			if (!sliderEl.noUiSlider || !startTimeEntry || !endTimeEntry) return;
			const s = startTimeEntry.value.trim();
			const e = endTimeEntry.value.trim();
			let startMs = s === "" ? 0 : Number.parseInt(s, 10);
			let endMs = e === "" ? resolvedDurationMs : Number.parseInt(e, 10);
			if (!Number.isFinite(startMs)) startMs = 0;
			if (!Number.isFinite(endMs)) endMs = resolvedDurationMs;
			startMs = Math.max(0, Math.min(startMs, resolvedDurationMs));
			endMs = Math.max(0, Math.min(endMs, resolvedDurationMs));
			if (startMs >= endMs)
				endMs = Math.min(startMs + resolvedFileCadenceMs, resolvedDurationMs);
			sliderEl.noUiSlider.set([startMs, endMs]);
		}
		function syncFromDateTimeEntries() {
			if (
				!hasEpoch ||
				!sliderEl.noUiSlider ||
				!startDateTimeEntry ||
				!endDateTimeEntry
			)
				return;
			let startMs;
			let endMs;
			if (startDateTimeEntry._flatpickr && endDateTimeEntry._flatpickr) {
				const dStart = startDateTimeEntry._flatpickr.selectedDates[0];
				const dEnd = endDateTimeEntry._flatpickr.selectedDates[0];
				startMs = dStart ? dStart.getTime() - epochStart : 0;
				endMs = dEnd ? dEnd.getTime() - epochStart : resolvedDurationMs;
			} else {
				startMs =
					parseUtcStringToEpochMs(startDateTimeEntry.value) - epochStart;
				endMs = parseUtcStringToEpochMs(endDateTimeEntry.value) - epochStart;
			}
			if (Number.isNaN(startMs) || Number.isNaN(endMs)) return;
			startMs = Math.max(0, Math.min(startMs, resolvedDurationMs));
			endMs = Math.max(0, Math.min(endMs, resolvedDurationMs));
			if (startMs >= endMs)
				endMs = Math.min(startMs + resolvedFileCadenceMs, resolvedDurationMs);
			const cur = sliderEl.noUiSlider.get();
			if (
				Math.round(Number(cur[0])) === Math.round(startMs) &&
				Math.round(Number(cur[1])) === Math.round(endMs)
			)
				return;
			sliderEl.noUiSlider.set([startMs, endMs]);
		}
		if (startTimeEntry)
			startTimeEntry.addEventListener("change", syncSliderFromEntries);
		if (endTimeEntry)
			endTimeEntry.addEventListener("change", syncSliderFromEntries);
		if (startDateTimeEntry && !startDateTimeEntry._flatpickr)
			startDateTimeEntry.addEventListener("change", syncFromDateTimeEntries);
		if (endDateTimeEntry && !endDateTimeEntry._flatpickr)
			endDateTimeEntry.addEventListener("change", syncFromDateTimeEntries);
	}

	setTemporalSliderAttrs(modalId, button, itemUuid) {
		// Initialize temporal slider from button data attributes (clears or builds slider)
		const durationMs = Number.parseInt(
			button.getAttribute("data-length-of-capture-ms"),
			10,
		);
		const fileCadenceMs = Number.parseInt(
			button.getAttribute("data-file-cadence-ms"),
			10,
		);
		const perDataFileSize = Number.parseFloat(
			button.getAttribute("data-per-data-file-size"),
		);
		const dataFilesCount = Number.parseInt(
			button.getAttribute("data-data-files-count"),
			10,
		);
		const dataFilesTotalSize = Number.parseInt(
			button.getAttribute("data-total-data-file-size"),
			10,
		);
		const totalSize = Number.parseInt(
			button.getAttribute("data-total-size"),
			10,
		);
		const totalFilesCount = Number.parseInt(
			button.getAttribute("data-total-files-count"),
			10,
		);
		const captureStartEpochSec = Number.parseInt(
			button.getAttribute("data-capture-start-epoch-sec"),
			10,
		);
		this.initializeCaptureDownloadSlider(
			modalId,
			Number.isNaN(durationMs) ? 0 : durationMs,
			Number.isNaN(fileCadenceMs) ? 1000 : fileCadenceMs,
			{
				perDataFileSize: Number.isNaN(perDataFileSize) ? 0 : perDataFileSize,
				totalSize: Number.isNaN(totalSize) ? 0 : totalSize,
				dataFilesCount: Number.isNaN(dataFilesCount) ? 0 : dataFilesCount,
				totalFilesCount: Number.isNaN(totalFilesCount) ? 0 : totalFilesCount,
				dataFilesTotalSize: Number.isNaN(dataFilesTotalSize)
					? undefined
					: dataFilesTotalSize,
				captureUuid: itemUuid || undefined,
				captureStartEpochSec: Number.isNaN(captureStartEpochSec)
					? undefined
					: captureStartEpochSec,
			},
		);
	}

	addTimeFilteringToFetchRequest(modalId) {
		const modalEl = document.getElementById(modalId);
		if (!modalEl) {
			return { body: {}, isJson: false };
		}
		const startTimeInput = modalEl.querySelector("#startTime");
		const endTimeInput = modalEl.querySelector("#endTime");
		const startEntry = modalEl.querySelector("#startTimeEntry");
		const endEntry = modalEl.querySelector("#endTimeEntry");

		if (startEntry && endEntry && modalEl && modalEl.dataset.durationMs) {
			const entryStart = startEntry.value.trim();
			const entryEnd = endEntry.value.trim();
			if (entryStart !== "" || entryEnd !== "") {
				const durationMs = Number.parseInt(modalEl.dataset.durationMs, 10);
				const startMs = entryStart === "" ? 0 : Number.parseInt(entryStart, 10);
				const endMs =
					entryEnd === "" ? durationMs : Number.parseInt(entryEnd, 10);
				if (
					!Number.isFinite(startMs) ||
					!Number.isFinite(endMs) ||
					startMs < 0 ||
					endMs > durationMs ||
					startMs >= endMs
				) {
					this.showToast(
						`Please enter valid start/end times (0 ≤ start < end ≤ ${durationMs} ms).`,
						"warning",
					);
					return;
				}
				if (startTimeInput) startTimeInput.value = String(startMs);
				if (endTimeInput) endTimeInput.value = String(endMs);
			}
		}

		const body = {};
		let isJson = true;
		if (
			startTimeInput &&
			endTimeInput &&
			startTimeInput.value &&
			endTimeInput.value
		) {
			body.start_time = startTimeInput.value;
			body.end_time = endTimeInput.value;
			isJson = false;
		}

		return { body, isJson };
	}

	/**
	 * Initialize web download modal for assets
	 * @param {Element} button - Download button element
	 */
	async initializeWebDownloadModal(itemUuid, itemType, button) {
		const modalId = `webDownloadModal-${itemUuid}`;
		// Show the modal
		window.DOMUtils.openModal(modalId);

		if (itemType === "capture") {
			this.setTemporalSliderAttrs(modalId, button, itemUuid);
		}

		// Handle confirm download
		const confirmBtn = document.getElementById(
			`confirmWebDownloadBtn-${itemUuid}`,
		);
		if (!confirmBtn) return;

		// Remove any existing event listeners
		const newConfirmBtn = confirmBtn.cloneNode(true);
		confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

		newConfirmBtn.onclick = async () => {
			// Show loading state
			const originalContent = button.innerHTML;
			await window.DOMUtils.renderLoading(button, "Processing...", {
				format: "spinner",
				size: "sm",
			});
			button.disabled = true;

			// Close modal
			window.DOMUtils.closeModal(modalId);

			let body = {};
			let isJson = false;
			try {
				if (itemType === "capture") {
					const result = this.addTimeFilteringToFetchRequest(modalId);
					body = result.body;
					isJson = result.isJson;
				}
				const response = await window.APIClient.post(
					`/users/download-item/${itemType}/${itemUuid}/`,
					body,
					null,
					isJson,
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
	 * Check if user can download specific item
	 * @param {Object} item - Item object
	 * @returns {boolean} Whether user can download
	 */
	canDownloadItem(_item) {
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
		const downloadButtons = document.querySelectorAll(".web-download-btn");
		for (const button of downloadButtons) {
			button.removeEventListener("click", this.initializeWebDownloadButtons);
		}
	}
}

// Make class available globally
window.DownloadActionManager = DownloadActionManager;

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
	module.exports = { DownloadActionManager };
}
