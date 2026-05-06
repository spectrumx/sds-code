class FileListCapturesTableManager extends CapturesTableManager {
	/**
	 * UUIDs selected for quick-add / bulk actions. Class field initializes as soon as
	 * the instance exists (after super()), so renderRow never runs before this exists.
	 */
	selectedCaptureIds = new Set();

	constructor(options) {
		super(options);
		this.resultsCountElement = document.getElementById(options.resultsCountId);
		this.searchButton = document.getElementById("search-btn");
		this.searchButtonContent = document.getElementById("search-btn-content");
		this.searchButtonLoading = document.getElementById("search-btn-loading");
		this.onSelectionChange = options.onSelectionChange ?? null;
		this.setupSelectionCheckboxHandler();
		this.setupRowClickSelection();
	}

	_notifySelectionChange() {
		if (typeof this.onSelectionChange === "function") {
			this.onSelectionChange();
		}
	}

	/**
	 * Override showLoading to toggle button contents instead of showing separate indicator
	 */
	showLoading() {
		if (this.searchButton) {
			this.searchButton.disabled = true;
			if (this.searchButtonContent)
				this.searchButtonContent.classList.add("d-none");
			if (this.searchButtonLoading)
				this.searchButtonLoading.classList.remove("d-none");
		}
	}

	/**
	 * Override hideLoading to restore button contents
	 */
	hideLoading() {
		if (this.searchButton) {
			this.searchButton.disabled = false;
			if (this.searchButtonContent)
				this.searchButtonContent.classList.remove("d-none");
			if (this.searchButtonLoading)
				this.searchButtonLoading.classList.add("d-none");
		}
	}

	/**
	 * Delegated handler for selection checkboxes: keep selectedCaptureIds in sync
	 */
	setupSelectionCheckboxHandler() {
		this._checkboxChangeHandler = (e) => {
			if (!e.target.matches(".capture-select-checkbox")) return;
			const uuid = e.target.getAttribute("data-capture-uuid");
			if (!uuid) return;
			if (e.target.checked) {
				this.selectedCaptureIds.add(uuid);
			} else {
				this.selectedCaptureIds.delete(uuid);
			}
			this._notifySelectionChange();
		};
		document.addEventListener("change", this._checkboxChangeHandler);
	}

	/**
	 * When selection mode is active, clicking a row toggles its selection (instead of opening the modal).
	 * Uses capture phase so we run before the row's click handler.
	 */
	setupRowClickSelection() {
		const table = document.getElementById(this.tableId);
		if (!table) return;
		this._rowClickTable = table;

		this._rowClickHandler = (e) => {
			if (!table.classList.contains("selection-mode-active")) return;
			if (
				e.target.closest(
					"button, a, [data-bs-toggle='dropdown'], .capture-select-checkbox",
				)
			)
				return;
			const row = e.target.closest("tr");
			if (!row) return;
			const checkbox = row.querySelector(".capture-select-checkbox");
			if (!checkbox) return;
			const uuid = checkbox.getAttribute("data-capture-uuid");
			if (!uuid) return;

			if (this.selectedCaptureIds.has(uuid)) {
				this.selectedCaptureIds.delete(uuid);
				checkbox.checked = false;
			} else {
				this.selectedCaptureIds.add(uuid);
				checkbox.checked = true;
			}
			this._notifySelectionChange();
			e.preventDefault();
			e.stopPropagation();
		};

		table.addEventListener("click", this._rowClickHandler, true);
	}

	destroy() {
		if (this._checkboxChangeHandler) {
			document.removeEventListener("change", this._checkboxChangeHandler);
			this._checkboxChangeHandler = null;
		}
		if (this._rowClickHandler && this._rowClickTable) {
			this._rowClickTable.removeEventListener(
				"click",
				this._rowClickHandler,
				true,
			);
			this._rowClickHandler = null;
			this._rowClickTable = null;
		}
		super.destroy();
	}

	/**
	 * Initialize dropdowns with body container for proper positioning
	 */
	initializeDropdowns() {
		if (window.DropdownUtils) {
			window.DropdownUtils.initIconDropdowns(document);
		}
	}

	/**
	 * Update table with new data
	 */
	updateTable(captures, hasResults) {
		this.selectedCaptureIds ??= new Set();
		const tbody = this.tbody ?? this.table?.querySelector("tbody");
		if (!tbody) return;

		// Update results count
		this.updateResultsCount(captures, hasResults);

		if (!hasResults || captures.length === 0) {
			tbody.innerHTML = `
				<tr>
					<td colspan="6" class="text-center text-muted py-4">
						<em>No captures found matching your search criteria.</em>
					</td>
				</tr>
			`;
			this._notifySelectionChange();
			return;
		}

		// Build table HTML efficiently
		const tableHTML = captures
			.map((capture, index) => this.renderRow(capture, index))
			.join("");
		tbody.innerHTML = tableHTML;

		// Initialize dropdowns after table is updated
		this.initializeDropdowns();
		this._notifySelectionChange();
	}

	/**
	 * Update results count display
	 */
	updateResultsCount(captures, hasResults) {
		if (this.resultsCountElement) {
			const count = hasResults && captures ? captures.length : 0;
			const pluralSuffix = count === 1 ? "" : "s";
			this.resultsCountElement.textContent = `${count} capture${pluralSuffix} found`;
		}
	}

	/**
	 * Render individual table row with XSS protection
	 * Overrides the base class method to include file-specific columns
	 */
	renderRow(capture) {
		this.selectedCaptureIds ??= new Set();
		// Sanitize all data before rendering
		const safeData = {
			uuid: ComponentUtils.escapeHtml(capture.uuid || ""),
			name: ComponentUtils.escapeHtml(capture.name || ""),
			channel: ComponentUtils.escapeHtml(capture.channel || ""),
			scanGroup: ComponentUtils.escapeHtml(capture.scan_group || ""),
			captureType: ComponentUtils.escapeHtml(capture.capture_type || ""),
			captureTypeDisplay: ComponentUtils.escapeHtml(
				capture.capture_type_display || "",
			),
			topLevelDir: ComponentUtils.escapeHtml(capture.top_level_dir || ""),
			indexName: ComponentUtils.escapeHtml(capture.index_name || ""),
			owner: ComponentUtils.escapeHtml(capture.owner || ""),
			origin: ComponentUtils.escapeHtml(capture.origin || ""),
			dataset: ComponentUtils.escapeHtml(capture.dataset || ""),
			createdAt: ComponentUtils.escapeHtml(capture.created_at || ""),
			updatedAt: ComponentUtils.escapeHtml(capture.updated_at || ""),
			isPublic: ComponentUtils.escapeHtml(capture.is_public || ""),
			isDeleted: ComponentUtils.escapeHtml(capture.is_deleted || ""),
			centerFrequencyGhz: ComponentUtils.escapeHtml(
				capture.center_frequency_ghz || "",
			),
			lengthOfCaptureMs: capture.length_of_capture_ms ?? 0,
			fileCadenceMs: capture.file_cadence_ms ?? 1000,
			perDataFileSize: capture.per_data_file_size ?? 0,
			totalSize: capture.total_file_size ?? 0,
			dataFilesCount: capture.data_files_count ?? 0,
			dataFilesTotalSize: capture.data_files_total_size ?? 0,
			totalFilesCount: capture.files.length ?? 0,
			captureStartEpochSec: capture.capture_start_epoch_sec ?? 0,
		};

		let typeDisplay = safeData.captureTypeDisplay || safeData.captureType;

		if (capture.is_multi_channel) {
			typeDisplay = capture.capture_type_display || safeData.captureType;
		}

		// Display name with fallback to "Unnamed Capture"
		const nameDisplay = safeData.name || "Unnamed Capture";

		// Format created date to match template format
		let createdDate = "-";
		if (capture.created_at) {
			const date = new Date(capture.created_at);
			if (!Number.isNaN(date.getTime())) {
				const dateStr = date.toISOString().split("T")[0]; // YYYY-MM-DD
				const timeStr = date.toLocaleTimeString("en-US", {
					hour12: false,
					timeZoneName: "short",
				}); // HH:mm:ss TZ
				createdDate = `
					<div class="d-flex align-items-center gap-2">
						<span class="bg-transparent pe-2">${dateStr}</span>
						<span class="text-muted bg-transparent">${timeStr}</span>
					</div>
				`;
			}
		}

		// Check if shared (for shared icon)
		const isShared = capture.is_shared_with_me || false;
		const sharedIcon = isShared
			? `<span class="ms-2 align-middle" data-bs-toggle="tooltip" title="Shared with you">
					<i class="bi bi-people-fill text-success"></i>
				</span>`
			: "";

		// Check if owner (for conditional actions and selection — only owned captures are selectable)
		const isOwner = capture.is_owner === true;

		const checked = this.selectedCaptureIds.has(capture.uuid) ? " checked" : "";
		const selectCell = isOwner
			? `<input type="checkbox"
						   class="capture-select-checkbox form-check-input"
						   data-capture-uuid="${safeData.uuid}"
						   aria-label="Select capture ${nameDisplay}"${checked}>`
			: '<span class="text-muted" aria-hidden="true">—</span>';
		return `
			<tr class="capture-row" data-clickable="true" data-uuid="${safeData.uuid}" data-capture-uuid="${safeData.uuid}">
				<td class="capture-select-column" headers="select-header">${selectCell}</td>
				<td headers="name-header">
					<a href="#" class="capture-link"
					   data-uuid="${safeData.uuid}"
					   data-name="${safeData.name}"
					   data-channel="${safeData.channel}"
					   data-scan-group="${safeData.scanGroup}"
					   data-capture-type="${safeData.captureType}"
					   data-top-level-dir="${safeData.topLevelDir}"
					   data-index-name="${safeData.indexName}"
					   data-owner="${safeData.owner}"
					   data-origin="${safeData.origin}"
					   data-dataset="${safeData.dataset}"
					   data-created-at="${safeData.createdAt}"
					   data-updated-at="${safeData.updatedAt}"
					   data-is-public="${safeData.isPublic}"
					   data-is-deleted="${safeData.isDeleted}"
					   data-center-frequency-ghz="${safeData.centerFrequencyGhz}"
					   data-is-multi-channel="${capture.is_multi_channel || false}"
					   data-channels="${capture.channels ? JSON.stringify(capture.channels) : ""}"
					   aria-label="View details for ${nameDisplay}"
					   title="View capture details: ${nameDisplay}">
						${nameDisplay}
					</a>
					${sharedIcon}
				</td>
				<td headers="top-level-dir-header">${safeData.topLevelDir || "-"}</td>
				<td headers="type-header">${typeDisplay}</td>
				<td headers="created-header" class="text-nowrap">${createdDate}</td>
				<td headers="actions-header" class="text-center">
					<div class="dropdown">
						<button class="btn btn-sm btn-light dropdown-toggle btn-icon-dropdown d-flex align-items-center justify-content-center mx-auto"
								type="button"
								data-bs-toggle="dropdown"
								data-bs-boundary="viewport"
								aria-expanded="false"
								aria-label="Actions for capture ${nameDisplay}"
								style="width: 32px; height: 32px; padding: 0;">
							<i class="bi bi-three-dots-vertical"></i>
						</button>
						<ul class="dropdown-menu">
							${
								isOwner
									? `
								<li>
									<button class="dropdown-item capture-details-btn"
											type="button"
											data-uuid="${safeData.uuid}"
											data-name="${safeData.name}"
											data-channel="${safeData.channel}"
											data-scan-group="${safeData.scanGroup}"
											data-capture-type="${safeData.captureType}"
											data-top-level-dir="${safeData.topLevelDir}"
											data-index-name="${safeData.indexName}"
											data-owner="${safeData.owner}"
											data-origin="${safeData.origin}"
											data-dataset="${safeData.dataset}"
											data-created-at="${safeData.createdAt}"
											data-updated-at="${safeData.updatedAt}"
											data-is-public="${safeData.isPublic}"
											data-is-deleted="${safeData.isDeleted}"
											data-center-frequency-ghz="${safeData.centerFrequencyGhz}"
											data-is-multi-channel="${capture.is_multi_channel || false}"
											data-channels="${capture.channels ? JSON.stringify(capture.channels) : ""}">
										Edit
									</button>
								</li>
								<li>
									<button class="dropdown-item"
											type="button"
											data-bs-toggle="modal"
											data-bs-target="#shareModal-${safeData.uuid}">
										Share
									</button>
								</li>
								<li>
									<button class="dropdown-item add-to-dataset-btn"
											type="button"
											data-capture-uuid="${safeData.uuid}"
											data-capture-name="${safeData.name}">
										Add to dataset
									</button>
								</li>
							`
									: ""
							}
							<li>
								<button class="dropdown-item download-capture-btn"
										type="button"
										data-capture-uuid="${safeData.uuid}"
										data-capture-name="${safeData.name}"
										data-length-of-capture-ms="${safeData.lengthOfCaptureMs}"
										data-file-cadence-ms="${safeData.fileCadenceMs}"
										data-per-data-file-size="${safeData.perDataFileSize}"
										data-total-size="${safeData.totalSize}"
										data-data-files-count="${safeData.dataFilesCount}"
										data-data-files-total-size="${safeData.dataFilesTotalSize}"
										data-total-files-count="${safeData.totalFilesCount}"
										data-capture-start-epoch-sec="${safeData.captureStartEpochSec}">
									Download
								</button>
							</li>
							${
								safeData.captureType === "drf"
									? `
								<li>
									<button class="dropdown-item visualization-trigger-btn"
											type="button"
											data-capture-uuid="${safeData.uuid}"
											data-capture-type="${safeData.captureType}">
										Visualize
									</button>
								</li>
							`
									: ""
							}
						</ul>
					</div>
				</td>
			</tr>
		`;
	}
}
