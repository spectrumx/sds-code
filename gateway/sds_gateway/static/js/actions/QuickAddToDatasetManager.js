/**
 * Quick Add to Dataset Manager
 * Handles opening the quick-add modal, loading datasets, and adding a capture to a dataset.
 */
class QuickAddToDatasetManager {
	constructor() {
		this.modalEl = document.getElementById("quickAddToDatasetModal");
		this.currentCaptureUuid = null;
		this.currentCaptureName = null;
		/** @type {string[]|null} When set, call quick-add API once per UUID (e.g. from file list "Add" button) */
		this.currentCaptureUuids = null;
		if (!this.modalEl) return;
		this.quickAddUrl = this.modalEl.getAttribute("data-quick-add-url");
		this.datasetsUrl = this.modalEl.getAttribute("data-datasets-url");
		this.selectEl = document.getElementById("quick-add-dataset-select");
		this.confirmBtn = document.getElementById("quick-add-confirm-btn");
		this.messageEl = document.getElementById("quick-add-message");
		this.captureNameEl = document.getElementById("quick-add-capture-name");
		this.initializeEventListeners();
	}

	initializeEventListeners() {
		// Delegate click on "Add to dataset" buttons (e.g. in table dropdown)
		document.addEventListener("click", (e) => {
			const btn = e.target.closest(".add-to-dataset-btn");
			if (!btn) return;
			e.preventDefault();
			e.stopPropagation();
			this.currentCaptureUuid = btn.getAttribute("data-capture-uuid");
			this.currentCaptureName =
				btn.getAttribute("data-capture-name") || "This capture";
			this.openModal();
		});

		if (!this.modalEl) return;

		// When modal is shown, load datasets and apply state (single vs multi from file list)
		this.modalEl.addEventListener("show.bs.modal", () => {
			this.resetMessage();
			const rawIds = this.modalEl.dataset.captureUuids;
			if (rawIds) {
				try {
					this.currentCaptureUuids = JSON.parse(rawIds);
					this.currentCaptureUuid = null;
					this.currentCaptureName = null;
					const n = this.currentCaptureUuids.length;
					if (this.captureNameEl) {
						this.captureNameEl.textContent =
							n === 1 ? "1 capture" : `${n} captures`;
					}
					delete this.modalEl.dataset.captureUuids;
				} catch (_) {
					this.currentCaptureUuids = null;
				}
			} else {
				this.currentCaptureUuids = null;
				if (this.captureNameEl) {
					this.captureNameEl.textContent =
						this.currentCaptureName || "This capture";
				}
			}
			this.loadDatasets();
		});

		// When dataset select changes, enable/disable Add button
		if (this.selectEl) {
			this.selectEl.addEventListener("change", () => {
				if (this.confirmBtn) {
					this.confirmBtn.disabled = !this.selectEl.value;
				}
			});
		}

		// Add button click
		if (this.confirmBtn) {
			this.confirmBtn.addEventListener("click", () => this.handleAdd());
		}
	}

	openModal() {
		if (!this.modalEl) return;
		const Modal = window.bootstrap?.Modal;
		if (Modal) {
			const modal = Modal.getOrCreateInstance(this.modalEl);
			modal.show();
		}
	}

	resetMessage() {
		if (this.messageEl) {
			this.messageEl.classList.add("d-none");
			this.messageEl.classList.remove(
				"alert-success",
				"alert-danger",
				"alert-warning",
			);
			this.messageEl.textContent = "";
		}
		if (this.confirmBtn) {
			this.confirmBtn.disabled = true;
		}
		if (this.selectEl) {
			this.selectEl.innerHTML = '<option value="">Loading...</option>';
		}
	}

	showMessage(text, type) {
		if (!this.messageEl) return;
		this.messageEl.textContent = text;
		this.messageEl.classList.remove(
			"d-none",
			"alert-success",
			"alert-danger",
			"alert-warning",
		);
		this.messageEl.classList.add(`alert-${type}`);
	}

	async loadDatasets() {
		if (!this.selectEl || !this.datasetsUrl) return;
		this.selectEl.innerHTML = '<option value="">Loading...</option>';
		if (this.confirmBtn) this.confirmBtn.disabled = true;
		try {
			const response = await window.APIClient.get(this.datasetsUrl);
			const datasets = response.datasets || [];
			this.selectEl.innerHTML = '<option value="">Select dataset...</option>';
			for (const d of datasets) {
				const opt = document.createElement("option");
				opt.value = d.uuid;
				opt.textContent = d.name;
				this.selectEl.appendChild(opt);
			}
			if (datasets.length === 0) {
				this.showMessage(
					"You have no datasets you can add captures to.",
					"warning",
				);
			}
		} catch (err) {
			this.selectEl.innerHTML = '<option value="">Failed to load</option>';
			const reason = err?.data?.error || err?.message || "Try again.";
			this.showMessage(`Failed to load datasets. ${reason}`, "danger");
		}
	}

	async handleAdd() {
		const datasetUuid = this.selectEl?.value;
		if (!datasetUuid) return;
		const isMulti =
			Array.isArray(this.currentCaptureUuids) &&
			this.currentCaptureUuids.length > 0;
		const isSingle = this.currentCaptureUuid && this.quickAddUrl;
		if (!isMulti && !isSingle) return;
		if (this.confirmBtn) this.confirmBtn.disabled = true;
		this.resetMessage();
		if (isMulti) {
			await this.handleMultiAdd(datasetUuid);
		} else {
			await this.handleSingleAdd(datasetUuid);
		}
	}

	/**
	 * Build a concise summary from quick-add counts (added, skipped, failed count).
	 * API returns detailed JSON; we show one short line.
	 * Failed = request threw (non-2xx HTTP or network) or response.success false or per-capture errors in 200 body.
	 */
	formatQuickAddSummary(added, skipped, failedCount, firstErrorMessage) {
		const parts = [];
		if (added > 0) parts.push(`${added} added`);
		if (skipped > 0) parts.push(`${skipped} already in dataset`);
		if (failedCount > 0) {
			parts.push(`${failedCount} failed`);
			if (firstErrorMessage != null) {
				const text =
					typeof firstErrorMessage === "object"
						? (firstErrorMessage.message ??
							firstErrorMessage.detail ??
							String(firstErrorMessage))
						: String(firstErrorMessage);
				if (text) parts.push(`: ${text}`);
			}
		}
		return parts.length ? `${parts.join(", ")}.` : "Done.";
	}

	/**
	 * Call quick-add API once per selected capture UUID (loop). Backend handles
	 * multi-channel grouping per UUID. We aggregate counts and show one concise message.
	 */
	async handleMultiAdd(datasetUuid) {
		if (!this.quickAddUrl) {
			this.showMessage("Quick-add URL not configured.", "danger");
			if (this.confirmBtn) this.confirmBtn.disabled = false;
			return;
		}
		let totalAdded = 0;
		let totalSkipped = 0;
		const errorMessages = [];
		for (const captureUuid of this.currentCaptureUuids) {
			try {
				const response = await window.APIClient.post(
					this.quickAddUrl,
					{
						dataset_uuid: datasetUuid,
						capture_uuid: captureUuid,
					},
					null,
					true,
				);
				if (response.success) {
					totalAdded += response.added?.length ?? 0;
					totalSkipped += response.skipped?.length ?? 0;
					if (response.errors?.length) {
						errorMessages.push(...(response.errors || []));
					}
				} else {
					errorMessages.push(response.error || "Request failed");
				}
			} catch (err) {
				// APIClient throws on non-2xx (and on network errors), so failed = exception or 4xx/5xx
				errorMessages.push(err?.data?.error || err?.message || String(err));
			}
		}
		// failed count = requests that threw (non-200 or network) + response.success false + per-capture errors in 200 response
		const errorCount = errorMessages.length;
		const hasErrors = errorCount > 0;
		const hasSuccess = totalAdded > 0 || totalSkipped > 0;
		const msg = this.formatQuickAddSummary(
			totalAdded,
			totalSkipped,
			errorCount,
			errorMessages[0],
		);
		this.showMessage(msg, hasErrors ? "warning" : "success");
		if (window.showAlert)
			window.showAlert(msg, hasErrors ? "warning" : "success");
		if (hasSuccess || !hasErrors) {
			setTimeout(() => {
				window.bootstrap?.Modal?.getInstance(this.modalEl)?.hide();
			}, 1500);
		} else if (this.confirmBtn) {
			this.confirmBtn.disabled = false;
		}
	}

	async handleSingleAdd(datasetUuid) {
		try {
			const response = await window.APIClient.post(
				this.quickAddUrl,
				{
					dataset_uuid: datasetUuid,
					capture_uuid: this.currentCaptureUuid,
				},
				null,
				true,
			);
			if (response.success) {
				const added = response.added?.length ?? 0;
				const skipped = response.skipped?.length ?? 0;
				const errorCount = response.errors?.length ?? 0;
				const firstError = response.errors?.[0];
				const msg = this.formatQuickAddSummary(
					added,
					skipped,
					errorCount,
					firstError,
				);
				this.showMessage(msg, errorCount > 0 ? "warning" : "success");
				if (window.showAlert)
					window.showAlert(msg, errorCount > 0 ? "warning" : "success");
				setTimeout(() => {
					window.bootstrap?.Modal?.getInstance(this.modalEl)?.hide();
				}, 1500);
			} else {
				this.showMessage(response.error || "Request failed.", "danger");
				if (this.confirmBtn) this.confirmBtn.disabled = false;
			}
		} catch (err) {
			const msg =
				err?.data?.error || err?.message || "Failed to add capture to dataset.";
			this.showMessage(msg, "danger");
			if (this.confirmBtn) this.confirmBtn.disabled = false;
		}
	}
}

window.QuickAddToDatasetManager = QuickAddToDatasetManager;
