/**
 * Dataset Editing Handler
 * Handles dataset editing workflow with pending changes management
 */
class DatasetEditingHandler {
	/**
	 * Initialize dataset editing handler
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.datasetUuid = config.datasetUuid;
		this.permissions = config.permissions; // PermissionsManager instance
		this.currentUserId = config.currentUserId;

		// Current assets in dataset
		this.currentCaptures = new Map();
		this.currentFiles = new Map();

		// Pending changes
		this.pendingCaptures = new Map(); // key: captureId, value: {action: 'add'|'remove', data: {...}}
		this.pendingFiles = new Map(); // key: fileId, value: {action: 'add'|'remove', data: {...}}

		// Search handlers
		this.capturesSearchHandler = null;
		this.filesSearchHandler = null;

		// Properties that SearchHandler expects from formHandler
		this.selectedCaptures = new Set();
		this.selectedFiles = new Set();

		// Store initial data
		this.initialCaptures = config.initialCaptures || [];
		this.initialFiles = config.initialFiles || [];

		this.initializeEventListeners();
		this.initializeAuthorsManagement();

		// Load current assets if no initial data provided
		if (!this.initialCaptures.length && !this.initialFiles.length) {
			this.loadCurrentAssets();
		}
	}

	/**
	 * Initialize event listeners
	 */
	initializeEventListeners() {
		// Initialize search handlers if they exist
		if (window.AssetSearchHandler) {
			this.capturesSearchHandler = new window.AssetSearchHandler({
				searchFormId: "captures-search-form",
				searchButtonId: "search-captures",
				clearButtonId: "clear-captures-search",
				tableBodyId: "captures-table-body",
				paginationContainerId: "captures-pagination",
				type: "captures",
				formHandler: this,
				isEditMode: true,
			});

			this.filesSearchHandler = new window.AssetSearchHandler({
				searchFormId: "files-search-form",
				searchButtonId: "search-files",
				clearButtonId: "clear-files-search",
				tableBodyId: "file-tree-table",
				paginationContainerId: "files-pagination",
				confirmFileSelectionId: "confirm-file-selection",
				type: "files",
				formHandler: this,
				isEditMode: true,
				apiEndpoint: window.location.pathname,
			});

			// Initialize captures search to show initial state
			if (
				this.capturesSearchHandler &&
				typeof this.capturesSearchHandler.initializeCapturesSearch ===
					"function"
			) {
				this.capturesSearchHandler.initializeCapturesSearch();
			}

			// Populate initial data now that handlers are ready
			this.populateFromInitialData(this.initialCaptures, this.initialFiles);
		}
	}

	/**
	 * Set search handler reference
	 * @param {Object} searchHandler - Search handler instance
	 * @param {string} type - Handler type (captures or files)
	 */
	setSearchHandler(searchHandler, type) {
		if (type === "captures") {
			this.capturesSearchHandler = searchHandler;
			// Defer population until SearchHandler is fully ready
			Promise.resolve().then(() => {
				this.populateSearchHandlerWithInitialData();
			});
		} else if (type === "files") {
			this.filesSearchHandler = searchHandler;
			this.filesSearchHandler.updateSelectedFilesList();
		}

		// If we have initial data and both handlers are ready, populate the data
		if (
			this.capturesSearchHandler &&
			this.filesSearchHandler &&
			(this.initialCaptures.length > 0 || this.initialFiles.length > 0)
		) {
			this.populateFromInitialData(this.initialCaptures, this.initialFiles);
		}
	}

	/**
	 * Populate search handler with initial data
	 */
	populateSearchHandlerWithInitialData() {
		// Populate the SearchHandler with initial captures if available
		if (
			this.capturesSearchHandler &&
			this.capturesSearchHandler.selectedCaptures &&
			this.capturesSearchHandler.selectedCaptureDetails &&
			this.initialCaptures &&
			this.initialCaptures.length > 0
		) {
			for (const capture of this.initialCaptures) {
				this.capturesSearchHandler.selectedCaptures.add(capture.id.toString());
				this.capturesSearchHandler.selectedCaptureDetails.set(
					capture.id.toString(),
					capture,
				);
			}
		}
		// Also populate the DatasetEditingHandler's selectedCaptures set
		if (this.initialCaptures && this.initialCaptures.length > 0) {
			for (const capture of this.initialCaptures) {
				this.selectedCaptures.add(capture.id.toString());
			}
		}
	}

	/**
	 * Populate from initial data
	 * @param {Array} initialCaptures - Initial captures data
	 * @param {Array} initialFiles - Initial files data
	 */
	populateFromInitialData(initialCaptures, initialFiles) {
		// Populate current captures in the side panel table
		this.currentCaptures.clear();
		this.populateCurrentCapturesList(initialCaptures);

		// Use the existing SearchHandler to populate captures in the main table
		if (
			this.capturesSearchHandler &&
			this.capturesSearchHandler.selectedCaptures
		) {
			if (initialCaptures && initialCaptures.length > 0) {
				for (const capture of initialCaptures) {
					this.capturesSearchHandler.selectedCaptures.add(
						capture.id.toString(),
					);
					this.capturesSearchHandler.selectedCaptureDetails.set(
						capture.id.toString(),
						capture,
					);
				}
			}
		}

		// Also populate the DatasetEditingHandler's selectedCaptures set
		if (initialCaptures && initialCaptures.length > 0) {
			for (const captureId of initialCaptures) {
				this.selectedCaptures.add(captureId.toString());
			}
		}

		// Populate current files
		this.currentFiles.clear();
		this.populateCurrentFilesList(initialFiles);

		// Use the existing SearchHandler to populate files for the file browser
		if (this.filesSearchHandler) {
			if (initialFiles && initialFiles.length > 0) {
				for (const file of initialFiles) {
					this.filesSearchHandler.selectedFiles.set(file.id, file);
				}
			}
			this.filesSearchHandler.updateSelectedFilesList();
		}

		// Add event listeners for remove buttons
		this.addRemoveButtonListeners();

		// Initialize file browser modal handlers
		this.initializeFileBrowserModal();
	}

	/**
	 * Initialize file browser modal handlers
	 */
	initializeFileBrowserModal() {
		// Modal show/hide handlers
		const modal = document.getElementById("fileTreeModal");
		if (modal) {
			modal.addEventListener("show.bs.modal", () => {
				this.onFileModalShow();
			});

			modal.addEventListener("hidden.bs.modal", () => {
				this.onFileModalHide();
			});
		}
	}

	/**
	 * Handle file modal show
	 */
	onFileModalShow() {
		// Trigger initial file tree loading if filesSearchHandler exists and tree hasn't been loaded
		if (this.filesSearchHandler && !this.filesSearchHandler.currentTree) {
			this.filesSearchHandler.handleSearch();
		}
	}

	/**
	 * Handle file modal hide
	 */
	onFileModalHide() {
		// Clear any intermediate state if needed
	}

	/**
	 * Populate current captures list
	 * @param {Array} captures - Captures data
	 */
	populateCurrentCapturesList(captures) {
		const currentCapturesList = document.getElementById(
			"current-captures-list",
		);
		const currentCapturesCount = document.querySelector(
			".current-captures-count",
		);

		if (!currentCapturesList) return;

		if (captures && captures.length > 0) {
			// Show all captures in the dataset, but only allow removal based on permissions
			const rows = captures
				.map((capture) => {
					this.currentCaptures.set(capture.id, capture);
					// Permission logic: co-owners can remove anyone's captures, contributors can only remove their own
					const isOwnedByCurrentUser = capture.owner_id === this.currentUserId;
					const canRemoveThisCapture =
						this.permissions.canRemoveAnyAssets() ||
						(this.permissions.canRemoveAsset(capture) && isOwnedByCurrentUser);
					const rowClass = !canRemoveThisCapture ? "readonly-row" : "";

					return HTMLInjectionManager.createTableRow(
						capture,
						`
					<tr data-capture-id="${capture.id}" class="current-capture-row ${rowClass}">
						<td>{{type}}</td>
						<td>{{directory}}</td>
						<td>{{owner_name}}</td>
						${
							canRemoveThisCapture
								? `
							<td>
								<button class="btn btn-sm btn-danger mark-for-removal-btn"
										data-capture-id="${capture.id}"
										data-capture-type="capture">
									Remove
								</button>
							</td>
						`
								: '<td><span class="text-muted">N/A</span></td>'
						}
					</tr>
				`,
						{ escape: false },
					);
				})
				.join("");

			HTMLInjectionManager.injectHTML(currentCapturesList, rows, {
				escape: false,
			});

			if (currentCapturesCount) {
				currentCapturesCount.textContent = captures.length;
			}
		} else {
			HTMLInjectionManager.injectHTML(
				currentCapturesList,
				'<tr><td colspan="4" class="text-center text-muted">No captures in dataset</td></tr>',
				{ escape: false },
			);
			if (currentCapturesCount) {
				currentCapturesCount.textContent = "0";
			}
		}
	}

	/**
	 * Populate current files list
	 * @param {Array} files - Files data
	 */
	populateCurrentFilesList(files) {
		// Use the existing selected-files-table from file_browser.html
		const selectedFilesTable = document.getElementById("selected-files-table");
		const selectedFilesBody = selectedFilesTable?.querySelector("tbody");
		const selectedFilesDisplay = document.getElementById(
			"selected-files-display",
		);

		if (!selectedFilesBody) return;

		if (files && files.length > 0) {
			// Show all files in the dataset, but only allow removal based on permissions
			const rows = files
				.map((file) => {
					this.currentFiles.set(file.id, file);

					// Permission logic: co-owners can remove anyone's files, contributors can only remove their own
					const isOwnedByCurrentUser = file.owner_id === this.currentUserId;
					const canRemoveThisFile =
						this.permissions.canRemoveAnyAssets() ||
						(this.permissions.canRemoveAsset(file) && isOwnedByCurrentUser);
					const rowClass = !canRemoveThisFile ? "readonly-row" : "";

					return HTMLInjectionManager.createTableRow(
						file,
						`
					<tr data-file-id="${file.id}" class="current-file-row ${rowClass}">
						<td>{{name}}</td>
						<td>{{media_type}}</td>
						<td>{{relative_path}}</td>
						<td>{{size}}</td>
						<td>{{owner_name}}</td>
						${
							canRemoveThisFile
								? `
							<td>
								<button class="btn btn-sm btn-danger mark-for-removal-btn"
										data-file-id="${file.id}"
										data-file-type="file">
									Remove
								</button>
							</td>
						`
								: '<td><span class="text-muted">N/A</span></td>'
						}
					</tr>
				`,
						{ escape: false },
					);
				})
				.join("");

			HTMLInjectionManager.injectHTML(selectedFilesBody, rows, {
				escape: false,
			});

			// Update the display input
			if (selectedFilesDisplay) {
				selectedFilesDisplay.value = `${files.length} file(s) selected`;
			}
		} else {
			HTMLInjectionManager.injectHTML(
				selectedFilesBody,
				'<tr><td colspan="6" class="text-center text-muted">No files in dataset</td></tr>',
				{ escape: false },
			);
			if (selectedFilesDisplay) {
				selectedFilesDisplay.value = "0 file(s) selected";
			}
		}
	}

	/**
	 * Load current assets from API
	 */
	async loadCurrentAssets() {
		if (!this.datasetUuid) return;

		try {
			const data = await APIClient.get(
				`/users/dataset-details/?dataset_uuid=${this.datasetUuid}`,
			);
			this.populateFromInitialData(data.captures || [], data.files || []);
		} catch (error) {
			console.error("Error loading current assets:", error);
		}
	}

	/**
	 * Add remove button listeners
	 */
	addRemoveButtonListeners() {
		const removeButtons = document.querySelectorAll(".mark-for-removal-btn");
		for (const button of removeButtons) {
			button.addEventListener("click", (e) => {
				e.preventDefault();
				const captureId = button.dataset.captureId;
				const fileId = button.dataset.fileId;

				if (captureId) {
					this.markCaptureForRemoval(captureId);
				} else if (fileId) {
					this.markFileForRemoval(fileId);
				}
			});
		}
	}

	/**
	 * Mark capture for removal
	 * @param {string} captureId - Capture ID to mark for removal
	 */
	markCaptureForRemoval(captureId) {
		const capture =
			this.currentCaptures.get(captureId) ||
			this.capturesSearchHandler?.selectedCaptureDetails.get(captureId);
		if (!capture) return;

		// Check if user has permission to remove this specific capture
		const isOwnedByCurrentUser = capture.owner_id === this.currentUserId;
		const canRemoveThisCapture =
			this.permissions.canRemoveAnyAssets() ||
			(this.permissions.canRemoveAsset(capture) && isOwnedByCurrentUser);

		if (!canRemoveThisCapture) {
			console.warn(
				`User does not have permission to remove capture ${captureId}`,
			);
			return;
		}

		// Add to pending removals
		this.pendingCaptures.set(captureId, {
			action: "remove",
			data: capture,
		});

		// Update visual state of current captures list
		this.updateCurrentCapturesList();

		// Also mark in the search results table if visible
		const searchRow = document.querySelector(
			`#captures-table-body tr[data-capture-id="${captureId}"]`,
		);
		if (searchRow) {
			searchRow.classList.add("marked-for-removal");
			const checkbox = searchRow.querySelector('input[type="checkbox"]');
			if (checkbox) {
				checkbox.checked = true;
			}
		}

		this.updatePendingCapturesList();

		// Update review display
		if (window.updateReviewDatasetDisplay) {
			window.updateReviewDatasetDisplay();
		}
	}

	/**
	 * Mark file for removal
	 * @param {string} fileId - File ID to mark for removal
	 */
	markFileForRemoval(fileId) {
		const file = this.filesSearchHandler?.selectedFiles.get(fileId);
		if (!file) return;

		// Check if user has permission to remove this specific file
		const isOwnedByCurrentUser = file.owner_id === this.currentUserId;
		const canRemoveThisFile =
			this.permissions.canRemoveAnyAssets() ||
			(this.permissions.canRemoveAsset(file) && isOwnedByCurrentUser);

		if (!canRemoveThisFile) {
			console.warn(`User does not have permission to remove file ${fileId}`);
			return;
		}

		// Add to pending removals
		this.pendingFiles.set(fileId, {
			action: "remove",
			data: file,
		});

		// Update visual state of current files list
		this.updateCurrentFilesList();

		// Update review display
		if (window.updateReviewDatasetDisplay) {
			window.updateReviewDatasetDisplay();
		}

		// Also mark in the search results table if visible
		const searchRow = document.querySelector(
			`#file-tree-table tr[data-file-id="${fileId}"]`,
		);
		if (searchRow) {
			searchRow.classList.add("marked-for-removal");
			const checkbox = searchRow.querySelector('input[type="checkbox"]');
			if (checkbox) {
				checkbox.checked = true;
			}
		}

		this.updatePendingFilesList();
	}

	/**
	 * Add capture to pending additions
	 * @param {string} captureId - Capture ID
	 * @param {Object} captureData - Capture data
	 */
	addCaptureToPending(captureId, captureData) {
		// Check if already in current captures
		if (this.currentCaptures.has(captureId)) {
			return; // Already in dataset
		}

		// Check if already in pending additions
		if (
			this.pendingCaptures.has(captureId) &&
			this.pendingCaptures.get(captureId).action === "add"
		) {
			return; // Already marked for addition
		}

		// Add to pending additions
		this.pendingCaptures.set(captureId, {
			action: "add",
			data: captureData,
		});

		// Also add to selectedCaptures set so it shows as checked in search results
		this.selectedCaptures.add(captureId.toString());

		this.updatePendingCapturesList();

		// Update review display
		if (window.updateReviewDatasetDisplay) {
			window.updateReviewDatasetDisplay();
		}
	}

	/**
	 * Add file to pending additions
	 * @param {string} fileId - File ID
	 * @param {Object} fileData - File data
	 */
	addFileToPending(fileId, fileData) {
		// Check if already in current files
		if (this.currentFiles.has(fileId)) {
			return; // Already in dataset
		}

		// Check if already in pending additions
		if (
			this.pendingFiles.has(fileId) &&
			this.pendingFiles.get(fileId).action === "add"
		) {
			return; // Already marked for addition
		}

		// Add to pending additions
		this.pendingFiles.set(fileId, {
			action: "add",
			data: fileData,
		});

		this.updatePendingFilesList();

		// Update review display
		if (window.updateReviewDatasetDisplay) {
			window.updateReviewDatasetDisplay();
		}
	}

	/**
	 * Update pending captures list
	 */
	updatePendingCapturesList() {
		const pendingList = document.getElementById("pending-captures-list");
		const pendingCount = document.querySelector(".pending-changes-count");

		const allChanges = Array.from(this.pendingCaptures.entries());

		if (allChanges.length === 0) {
			HTMLInjectionManager.injectHTML(
				pendingList,
				'<tr><td colspan="3" class="text-center text-muted">No pending capture changes</td></tr>',
				{ escape: false },
			);
			if (pendingCount) {
				pendingCount.textContent = "0";
			}
			return;
		}

		const rows = allChanges
			.map(([id, change]) => {
				const badgeClass = change.action === "add" ? "bg-success" : "bg-danger";
				const badgeText = change.action === "add" ? "Add" : "Remove";

				return `
				<tr>
					<td><span class="badge ${badgeClass}">${badgeText}</span></td>
					<td>${HTMLInjectionManager.escapeHtml(change.data.type)}</td>
					<td>
						<button class="btn btn-sm btn-secondary cancel-change"
								data-capture-id="${id}"
								data-change-type="capture">
							Cancel
						</button>
					</td>
				</tr>
			`;
			})
			.join("");

		HTMLInjectionManager.injectHTML(pendingList, rows, { escape: false });

		if (pendingCount) {
			pendingCount.textContent = allChanges.length;
		}

		// Add event listeners for cancel buttons
		this.addCancelButtonListeners();
	}

	/**
	 * Update pending files list
	 */
	updatePendingFilesList() {
		const pendingList = document.getElementById("pending-files-list");
		const pendingCount = document.querySelector(".pending-files-changes-count");

		const allChanges = Array.from(this.pendingFiles.entries());

		if (allChanges.length === 0) {
			HTMLInjectionManager.injectHTML(
				pendingList,
				'<tr><td colspan="3" class="text-center text-muted">No pending file changes</td></tr>',
				{ escape: false },
			);
			if (pendingCount) {
				pendingCount.textContent = "0";
			}
			return;
		}

		const rows = allChanges
			.map(([id, change]) => {
				const badgeClass = change.action === "add" ? "bg-success" : "bg-danger";
				const badgeText = change.action === "add" ? "Add" : "Remove";

				return `
				<tr>
					<td><span class="badge ${badgeClass}">${badgeText}</span></td>
					<td>${HTMLInjectionManager.escapeHtml(change.data.name)}</td>
					<td>
						<button class="btn btn-sm btn-secondary cancel-change"
								data-file-id="${id}"
								data-change-type="file">
							Cancel
						</button>
					</td>
				</tr>
			`;
			})
			.join("");

		HTMLInjectionManager.injectHTML(pendingList, rows, { escape: false });

		if (pendingCount) {
			pendingCount.textContent = allChanges.length;
		}

		// Add event listeners for cancel buttons
		this.addCancelButtonListeners();
	}

	/**
	 * Add cancel button listeners
	 */
	addCancelButtonListeners() {
		const cancelButtons = document.querySelectorAll(".cancel-change");
		for (const button of cancelButtons) {
			button.addEventListener("click", (e) => {
				e.preventDefault();
				const captureId = button.dataset.captureId;
				const fileId = button.dataset.fileId;
				const changeType = button.dataset.changeType;

				if (changeType === "capture" && captureId) {
					this.cancelCaptureChange(captureId);
				} else if (changeType === "file" && fileId) {
					this.cancelFileChange(fileId);
				}
			});
		}
	}

	/**
	 * Cancel capture change
	 * @param {string} captureId - Capture ID
	 */
	cancelCaptureChange(captureId) {
		const change = this.pendingCaptures.get(captureId);
		if (!change) return;

		this.pendingCaptures.delete(captureId);

		if (change.action === "remove") {
			// Update visual state of current captures list
			this.updateCurrentCapturesList();
		} else if (change.action === "add") {
			// Remove from selectedCaptures set so it shows as unchecked in search results
			this.selectedCaptures.delete(captureId.toString());
		}

		this.updatePendingCapturesList();

		// Update review display
		if (window.updateReviewDatasetDisplay) {
			window.updateReviewDatasetDisplay();
		}
	}

	/**
	 * Cancel file change
	 * @param {string} fileId - File ID
	 */
	cancelFileChange(fileId) {
		const change = this.pendingFiles.get(fileId);
		if (!change) return;

		this.pendingFiles.delete(fileId);

		if (change.action === "remove") {
			// Update visual state of current files list
			this.updateCurrentFilesList();
		} else if (change.action === "add") {
			// Remove from SearchHandler's selectedFiles if it exists
			if (this.filesSearchHandler) {
				this.filesSearchHandler.selectedFiles.delete(fileId);
			}
		}

		this.updatePendingFilesList();

		// Update review display
		if (window.updateReviewDatasetDisplay) {
			window.updateReviewDatasetDisplay();
		}
	}

	/**
	 * Get pending changes
	 * @returns {Object} Pending changes object
	 */
	getPendingChanges() {
		return {
			captures: Array.from(this.pendingCaptures.entries()),
			files: Array.from(this.pendingFiles.entries()),
		};
	}

	/**
	 * Check if there are any pending changes
	 * @returns {boolean} Whether there are pending changes
	 */
	hasChanges() {
		return this.pendingCaptures.size > 0 || this.pendingFiles.size > 0;
	}

	/**
	 * Handle file removal (override for edit mode)
	 * @param {string} fileId - File ID to remove
	 */
	handleFileRemoval(fileId) {
		// In edit mode: mark for removal instead of actually removing
		this.markFileForRemoval(fileId);
	}

	/**
	 * Handle capture removal (override for edit mode)
	 * @param {string} captureId - Capture ID to remove
	 */
	handleCaptureRemoval(captureId) {
		// In edit mode: mark for removal instead of actually removing
		this.markCaptureForRemoval(captureId);
	}

	/**
	 * Handle remove all files (override for edit mode)
	 */
	handleRemoveAllFiles() {
		// In edit mode: mark files for removal only if user has permission
		if (this.filesSearchHandler && this.filesSearchHandler.selectedFiles) {
			let removedCount = 0;
			for (const [
				fileId,
				file,
			] of this.filesSearchHandler.selectedFiles.entries()) {
				// Only mark for removal if user has permission
				if (this.permissions.canRemoveAsset(file)) {
					this.markFileForRemoval(fileId);
					removedCount++;
				}
			}

			// Disable the remove all files button if any files were marked for removal
			if (removedCount > 0) {
				const removeAllFilesButton = document.querySelector(
					".remove-all-selected-files-button",
				);
				if (removeAllFilesButton) {
					removeAllFilesButton.disabled = true;
					removeAllFilesButton.style.opacity = "0.5";
				}
			}
		}
	}

	/**
	 * Update current files list visual state
	 * This method only updates the visual state of existing files (e.g., marking for removal)
	 * It does NOT add new files - those should only appear in pending changes
	 */
	updateCurrentFilesList() {
		const selectedFilesTable = document.getElementById("selected-files-table");
		const selectedFilesBody = selectedFilesTable?.querySelector("tbody");
		if (!selectedFilesBody) return;

		// Update visual state of existing rows based on pending changes
		const rows = selectedFilesBody.querySelectorAll("tr[data-file-id]");
		for (const row of rows) {
			const fileId = row.dataset.fileId;
			const pendingChange = this.pendingFiles.get(fileId);

			if (pendingChange && pendingChange.action === "remove") {
				// Mark as pending removal
				row.classList.add("marked-for-removal");
				const removeButton = row.querySelector(".mark-for-removal-btn");
				if (removeButton) {
					removeButton.disabled = true;
					removeButton.style.opacity = "0.5";
				}
			} else {
				// Restore normal state
				row.classList.remove("marked-for-removal");
				const removeButton = row.querySelector(".mark-for-removal-btn");
				if (removeButton) {
					removeButton.disabled = false;
					removeButton.style.opacity = "";
				}
			}
		}
	}

	/**
	 * Update current captures list visual state
	 * This method only updates the visual state of existing captures (e.g., marking for removal)
	 * It does NOT add new captures - those should only appear in pending changes
	 */
	updateCurrentCapturesList() {
		const currentCapturesList = document.getElementById(
			"current-captures-list",
		);
		if (!currentCapturesList) return;

		// Update visual state of existing rows based on pending changes
		const rows = currentCapturesList.querySelectorAll("tr[data-capture-id]");
		for (const row of rows) {
			const captureId = row.dataset.captureId;
			const pendingChange = this.pendingCaptures.get(captureId);

			if (pendingChange && pendingChange.action === "remove") {
				// Mark as pending removal
				row.classList.add("marked-for-removal");
				const removeButton = row.querySelector(".mark-for-removal-btn");
				if (removeButton) {
					removeButton.disabled = true;
					removeButton.style.opacity = "0.5";
				}
			} else {
				// Restore normal state
				row.classList.remove("marked-for-removal");
				const removeButton = row.querySelector(".mark-for-removal-btn");
				if (removeButton) {
					removeButton.disabled = false;
					removeButton.style.opacity = "";
				}
			}
		}
	}

	/**
	 * Format file size
	 * @param {number} bytes - File size in bytes
	 * @returns {string} Formatted file size
	 */
	formatFileSize(bytes) {
		if (bytes === 0) return "0 Bytes";
		const k = 1024;
		const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
	}

	/**
	 * Show element
	 * @param {Element} container - Element to show
	 * @param {string} showClass - CSS class to add
	 */
	show(container, showClass = "display-block") {
		container.classList.remove("display-none");
		container.classList.add(showClass);
	}

	/**
	 * Hide element
	 * @param {Element} container - Element to hide
	 * @param {string} showClass - CSS class to remove
	 */
	hide(container, showClass = "display-block") {
		container.classList.remove(showClass);
		container.classList.add("display-none");
	}

	/**
	 * Update hidden fields (no-op for editing mode)
	 */
	updateHiddenFields() {
		// This method is called by SearchHandler but not needed for editing mode
		// We'll implement it as a no-op since editing mode doesn't use hidden fields
	}

	/**
	 * Handle form submission for edit mode
	 * @param {Event} e - Submit event
	 */
	handleSubmit(e) {
		e.preventDefault();

		// Collect form data
		const formData = new FormData(document.getElementById("datasetForm"));

		// Add pending changes to form data
		const pendingChanges = this.getPendingChanges();

		// Add pending captures
		const capturesAdd = [];
		const capturesRemove = [];
		for (const [id, change] of pendingChanges.captures) {
			if (change.action === "add") {
				capturesAdd.push(id);
			} else if (change.action === "remove") {
				capturesRemove.push(id);
			}
		}

		// Add pending files
		const filesAdd = [];
		const filesRemove = [];
		for (const [id, change] of pendingChanges.files) {
			if (change.action === "add") {
				filesAdd.push(id);
			} else if (change.action === "remove") {
				filesRemove.push(id);
			}
		}

		// Add comma-separated lists to form data
		if (capturesAdd.length > 0) {
			formData.append("captures_add", capturesAdd.join(","));
		}
		if (capturesRemove.length > 0) {
			formData.append("captures_remove", capturesRemove.join(","));
		}
		if (filesAdd.length > 0) {
			formData.append("files_add", filesAdd.join(","));
		}
		if (filesRemove.length > 0) {
			formData.append("files_remove", filesRemove.join(","));
		}

		// Add author changes if they exist
		if (
			this.authorChanges &&
			(this.authorChanges.added.length > 0 ||
				this.authorChanges.removed.length > 0 ||
				Object.keys(this.authorChanges.modified).length > 0)
		) {
			formData.append("author_changes", JSON.stringify(this.authorChanges));
		}

		// Submit the form
		this.submitForm(formData);
	}

	/**
	 * Submit the form with pending changes
	 * @param {FormData} formData - Form data to submit
	 */
	async submitForm(formData) {
		try {
			// Show loading state
			const submitBtn = document.getElementById("submitForm");
			if (submitBtn) {
				submitBtn.disabled = true;
				submitBtn.innerHTML =
					'<span class="spinner-border spinner-border-sm me-2"></span>Updating...';
			}

			// Submit form
			const response = await fetch(window.location.href, {
				method: "POST",
				body: formData,
				headers: {
					"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")
						.value,
				},
			});

			if (response.ok) {
				// Success - redirect or show success message
				const result = await response.json();
				if (result.success) {
					// Redirect to dataset list or show success message
					window.location.href = result.redirect_url || "/users/dataset-list/";
				} else {
					// Show error message
					this.showNotification(
						result.message || "An error occurred while updating the dataset.",
						"error",
					);
				}
			} else {
				// Handle error response
				this.showNotification(
					"An error occurred while updating the dataset.",
					"error",
				);
			}
		} catch (error) {
			console.error("Error submitting form:", error);
			this.showNotification(
				"An error occurred while updating the dataset.",
				"error",
			);
		} finally {
			// Restore submit button
			const submitBtn = document.getElementById("submitForm");
			if (submitBtn) {
				submitBtn.disabled = false;
				submitBtn.innerHTML = "Update Dataset";
			}
		}
	}

	/**
	 * Initialize authors management for edit mode
	 */
	initializeAuthorsManagement() {
		// Always set up global functions for review display, regardless of edit permissions
		window.updateDatasetAuthors = (authorsField) =>
			this.updateDatasetAuthors(authorsField);
		window.formatAuthors = (authors) => this.formatAuthors(authors);
		window.escapeHtml = (text) => HTMLInjectionManager.escapeHtml(text);

		const authorsContainer = document.getElementById("authors-container");
		const authorsList = authorsContainer?.querySelector(".authors-list");
		const addAuthorBtn = document.getElementById("add-author-btn");
		const authorsHiddenField = document.getElementById("id_authors");

		if (!authorsContainer || !authorsList || !authorsHiddenField) return;

		// Get initial authors from the hidden field
		let authors = [];
		let originalAuthors = []; // Store original authors for edit mode
		try {
			const initialAuthors = authorsHiddenField.value;
			if (initialAuthors && initialAuthors.trim() !== "") {
				authors = JSON.parse(initialAuthors);
			}
		} catch (e) {
			console.error("Error parsing initial authors:", e);
		}

		// Get original authors from dataset context
		const datasetAuthors = this.initialAuthors || [];
		originalAuthors = Array.isArray(datasetAuthors) ? datasetAuthors : [];

		// Convert to consistent format
		originalAuthors = originalAuthors.map((author) => {
			if (typeof author === "string") {
				return { name: author, orcid_id: "" };
			}
			return author;
		});

		// Convert legacy string authors to new format if needed
		authors = authors.map((author) => {
			if (typeof author === "string") {
				return {
					name: author,
					orcid_id: "",
				};
			}
			return author;
		});

		// Track author changes for edit mode
		const authorChanges = {
			added: [],
			removed: [],
			modified: {}, // index -> {old: string, new: string}
		};

		// Detect initial changes by comparing current authors with original authors
		if (originalAuthors.length > 0) {
			// Find new authors (authors in current list but not in original list)
			for (const [index, author] of authors.entries()) {
				const authorName = typeof author === "string" ? author : author.name;
				const authorOrcid = typeof author === "string" ? "" : author.orcid_id;

				// Check if this author exists in the original authors
				const existsInOriginal = originalAuthors.some((origAuthor) => {
					const origName =
						typeof origAuthor === "string" ? origAuthor : origAuthor.name;
					const origOrcid =
						typeof origAuthor === "string" ? "" : origAuthor.orcid_id;
					return origName === authorName && origOrcid === authorOrcid;
				});

				if (!existsInOriginal) {
					authorChanges.added.push(index);
				}
			}

			// Find removed authors (authors in original list but not in current list)
			for (const [origIndex, origAuthor] of originalAuthors.entries()) {
				const origName =
					typeof origAuthor === "string" ? origAuthor : origAuthor.name;
				const origOrcid =
					typeof origAuthor === "string" ? "" : origAuthor.orcid_id;

				// Check if this author exists in the current authors
				const existsInCurrent = authors.some((author) => {
					const authorName = typeof author === "string" ? author : author.name;
					const authorOrcid = typeof author === "string" ? "" : author.orcid_id;
					return authorName === origName && authorOrcid === origOrcid;
				});

				if (!existsInCurrent) {
					// Find the index in the current authors array
					const currentIndex = authors.findIndex((author) => {
						const authorName =
							typeof author === "string" ? author : author.name;
						return authorName === origName;
					});
					if (currentIndex >= 0) {
						authorChanges.removed.push(currentIndex);
					}
				}
			}
		}

		/**
		 * Update authors display
		 */
		const updateAuthorsDisplay = () => {
			// Clear the entire authors list
			authorsList.innerHTML = "";
			// Rebuild the display from the current authors array
			for (const [index, author] of authors.entries()) {
				const authorDiv = document.createElement("div");
				authorDiv.className = "author-item mb-3 p-3 border rounded";
				authorDiv.id = author._stableId;

				// Check if this author is marked for removal
				const isMarkedForRemoval = authorChanges.removed.includes(index);

				// Apply visual styling for marked authors
				if (isMarkedForRemoval) {
					authorDiv.classList.add("marked-for-removal");
					authorDiv.classList.add("border-danger");
				}

				const authorName =
					typeof author === "string" ? author : author.name || "";
				const authorOrcid =
					typeof author === "string" ? "" : author.orcid_id || "";

				authorDiv.innerHTML = `
					<div class="position-relative">
						<div class="d-flex justify-content-between align-items-start mb-2">
							<div class="flex-grow-1">
								<!-- Empty space for alignment -->
							</div>
							<div class="d-flex align-items-center gap-2">
								${
									index === 0
										? '<span class="badge bg-primary">Primary</span><i class="bi bi-lock-fill text-muted" title="Primary author cannot be removed"></i>'
										: isMarkedForRemoval
											? `<button type="button" class="btn btn-sm btn-outline-secondary cancel-remove-author" data-index="${index}" title="Cancel removal"><i class="bi bi-arrow-counterclockwise"></i></button>`
											: `<button type="button" class="btn btn-sm btn-outline-danger remove-author" data-index="${index}" title="Mark for removal"><i class="bi bi-trash"></i></button>`
								}
							</div>
						</div>
						<div class="row g-2">
							<div class="col-6">
								<label class="form-label small">Author Name</label>
								<input type="text"
									   class="form-control author-name-input"
									   value="${HTMLInjectionManager.escapeHtml(authorName)}"
									   placeholder="Enter full name"
									   ${index === 0 ? "readonly" : ""}
									   ${isMarkedForRemoval ? "disabled" : ""}
									   data-index="${index}"
									   data-field="name">
							</div>
							<div class="col-6">
								<label class="form-label small">ORCID ID</label>
								<input type="text"
									   class="form-control author-orcid-input"
									   value="${HTMLInjectionManager.escapeHtml(authorOrcid)}"
									   placeholder="0000-0000-0000-0000"
									   ${index === 0 ? "readonly" : ""}
									   ${isMarkedForRemoval ? "disabled" : ""}
									   data-index="${index}"
									   data-field="orcid_id">
							</div>
						</div>
					</div>
				`;
				authorsList.appendChild(authorDiv);
			}

			// Update hidden field
			authorsHiddenField.value = JSON.stringify(authors);

			// Show/hide add button based on permissions
			if (addAuthorBtn) {
				addAuthorBtn.style.display = this.permissions?.canEditMetadata
					? ""
					: "none";
			}
		};

		/**
		 * Add new author
		 */
		const addAuthor = () => {
			const newIndex = authors.length;
			authors.push({
				name: "",
				orcid_id: "",
			});

			// Track as added for change management
			if (!authorChanges.added.includes(newIndex)) {
				authorChanges.added.push(newIndex);
			}

			updateAuthorsDisplay();

			// Focus on the new name input
			const newInput = authorsList.querySelector(
				`input[data-index="${newIndex}"][data-field="name"]`,
			);
			if (newInput) {
				newInput.focus();
			}

			// Update review display
			if (window.updateReviewDatasetDisplay) {
				window.updateReviewDatasetDisplay();
			}
		};

		/**
		 * Remove author
		 */
		const removeAuthor = (index) => {
			if (index > 0) {
				// Don't remove the primary author
				// Check if this is a newly added author
				const isNewlyAdded = authorChanges.added.includes(index);

				if (isNewlyAdded) {
					// If it's a newly added author, completely remove it
					authors.splice(index, 1);

					// Remove from the added list
					const addIndex = authorChanges.added.indexOf(index);
					if (addIndex > -1) {
						authorChanges.added.splice(addIndex, 1);
					}

					// Adjust indices in the added list for authors that come after this one
					authorChanges.added = authorChanges.added.map((addedIndex) =>
						addedIndex > index ? addedIndex - 1 : addedIndex,
					);

					// Adjust indices in the removed list for authors that come after this one
					authorChanges.removed = authorChanges.removed.map((removedIndex) =>
						removedIndex > index ? removedIndex - 1 : removedIndex,
					);

					// Adjust indices in the modified list for authors that come after this one
					const newModified = {};
					for (const [modifiedIndex, changes] of Object.entries(
						authorChanges.modified,
					)) {
						const numIndex = Number.parseInt(modifiedIndex);
						if (numIndex > index) {
							newModified[numIndex - 1] = changes;
						} else if (numIndex < index) {
							newModified[numIndex] = changes;
						}
					}
					authorChanges.modified = newModified;
				} else {
					// For existing authors, mark for removal instead of actually removing
					if (!authorChanges.removed.includes(index)) {
						authorChanges.removed.push(index);
					}
				}

				updateAuthorsDisplay();

				// Update review display
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
			} else {
				// Show warning that primary author cannot be removed
				this.showNotification(
					"The primary author cannot be removed. This is the dataset creator.",
					"warning",
				);
			}
		};

		/**
		 * Cancel author removal
		 */
		const cancelAuthorRemoval = (index) => {
			if (authorChanges.removed.includes(index)) {
				const removeIndex = authorChanges.removed.indexOf(index);
				if (removeIndex > -1) {
					authorChanges.removed.splice(removeIndex, 1);
				}
				updateAuthorsDisplay();

				// Update review display
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
			}
		};

		/**
		 * Show notification using HTMLInjectionManager
		 */
		this.showNotification = (message, type = "info") => {
			HTMLInjectionManager.showNotification(message, type, {
				containerId: "formErrors",
				autoHide: true,
				autoHideDelay: 5000,
				scrollTo: true,
				replace: true,
			});
		};

		// Event listeners
		if (addAuthorBtn) {
			addAuthorBtn.addEventListener("click", addAuthor);
		}

		// Handle input changes
		authorsList.addEventListener("input", (e) => {
			if (
				e.target.classList.contains("author-name-input") ||
				e.target.classList.contains("author-orcid-input")
			) {
				const index = Number.parseInt(e.target.dataset.index);
				const field = e.target.dataset.field;

				// Ensure author object exists
				if (!authors[index] || typeof authors[index] === "string") {
					authors[index] = {
						name: typeof authors[index] === "string" ? authors[index] : "",
						orcid_id: "",
					};
				}

				const oldValue = authors[index][field];
				authors[index][field] = e.target.value;

				// Track modifications in edit mode
				if (index < originalAuthors.length) {
					const originalAuthor = originalAuthors[index];
					const originalValue =
						typeof originalAuthor === "string"
							? field === "name"
								? originalAuthor
								: ""
							: originalAuthor[field] || "";

					if (e.target.value !== originalValue) {
						if (!authorChanges.modified[index]) {
							authorChanges.modified[index] = {};
						}
						authorChanges.modified[index][field] = {
							old: originalValue,
							new: e.target.value,
						};
					} else {
						if (authorChanges.modified[index]) {
							delete authorChanges.modified[index][field];
							if (Object.keys(authorChanges.modified[index]).length === 0) {
								delete authorChanges.modified[index];
							}
						}
					}
				}

				// Only update display if we need to remove empty authors
				let needsUpdate = false;
				if (
					index > 0 &&
					!authors[index].name.trim() &&
					!authors[index].orcid_id.trim()
				) {
					authors.splice(index, 1);
					needsUpdate = true;
				}

				authorsHiddenField.value = JSON.stringify(authors);

				// Only call updateAuthorsDisplay if we actually removed an author
				if (needsUpdate) {
					updateAuthorsDisplay();
				}

				// Update review display if we're on the review step
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
			}
		});

		// Handle remove and cancel buttons
		authorsList.addEventListener("click", (e) => {
			const removeButton = e.target.closest(".remove-author");
			const cancelButton = e.target.closest(".cancel-remove-author");

			if (removeButton) {
				e.preventDefault();
				e.stopPropagation();
				const index = Number.parseInt(removeButton.dataset.index);
				removeAuthor(index);
			} else if (cancelButton) {
				e.preventDefault();
				e.stopPropagation();
				const index = Number.parseInt(cancelButton.dataset.index);
				cancelAuthorRemoval(index);
			}
		});

		// Initial display
		updateAuthorsDisplay();

		// Store authors and changes for external access
		this.authors = authors;
		this.originalAuthors = originalAuthors;
		this.authorChanges = authorChanges;
		this.updateAuthorsDisplay = updateAuthorsDisplay;

		// Make functions available globally for review display
		window.getAuthorChanges = () => authorChanges;
		window.calculateAuthorChanges = (originalAuthors, currentAuthors) =>
			this.calculateAuthorChanges(originalAuthors, currentAuthors);
		window.getCurrentAuthorsWithDOMIds = () =>
			this.getCurrentAuthorsWithDOMIds();
		window.captureAuthorsWithDOMIds = (authors) =>
			this.captureAuthorsWithDOMIds(authors);
		window.cancelAuthorAddition = (index) => {
			if (authorChanges.added.includes(index)) {
				const removeIndex = authorChanges.added.indexOf(index);
				if (removeIndex > -1) {
					authorChanges.added.splice(removeIndex, 1);
				}
				authors.splice(index, 1);
				updateAuthorsDisplay();
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
			}
		};

		window.cancelAuthorRemoval = (index) => {
			if (authorChanges.removed.includes(index)) {
				const removeIndex = authorChanges.removed.indexOf(index);
				if (removeIndex > -1) {
					authorChanges.removed.splice(removeIndex, 1);
				}
				updateAuthorsDisplay();
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
			}
		};

		window.cancelAuthorModification = (index, field) => {
			if (
				authorChanges.modified[index] &&
				authorChanges.modified[index][field]
			) {
				delete authorChanges.modified[index][field];
				if (Object.keys(authorChanges.modified[index]).length === 0) {
					delete authorChanges.modified[index];
				}
				// Restore original value
				if (originalAuthors[index]) {
					const originalAuthor = originalAuthors[index];
					const originalValue =
						typeof originalAuthor === "string"
							? field === "name"
								? originalAuthor
								: ""
							: originalAuthor[field] || "";
					authors[index][field] = originalValue;
				}
				updateAuthorsDisplay();
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
			}
		};
	}

	/**
	 * Update dataset authors with pending changes (for review display)
	 */
	updateDatasetAuthors(authorsField) {
		const authorsElement = document.querySelector(".dataset-authors");
		if (!authorsElement) return;

		if (!authorsField) {
			// In contributor view, there's no editable authors field, so show original authors
			const originalAuthors =
				window.datasetModeManager?.originalDatasetData?.authors || [];
			const originalAuthorNames = this.formatAuthors(originalAuthors);
			authorsElement.innerHTML = `<span class="current-value">${HTMLInjectionManager.escapeHtml(originalAuthorNames)}</span>`;
			return;
		}

		try {
			// Get all authors from form field
			const allAuthors = JSON.parse(authorsField.value || "[]");

			// Get current authors with DOM-based stable IDs
			const currentAuthorsWithIds = this.getCurrentAuthorsWithDOMIds();
			// Get original authors from DatasetModeManager's captured data
			const originalAuthors =
				window.datasetModeManager?.originalDatasetData?.authors || [];

			// Format original authors for display
			const originalAuthorNames = this.formatAuthors(originalAuthors);
			// Always show original value in black
			authorsElement.innerHTML = `<span class="current-value">${HTMLInjectionManager.escapeHtml(originalAuthorNames)}</span>`;

			// Calculate changes using DOM-based IDs
			const changes = this.calculateAuthorChanges(
				originalAuthors,
				currentAuthorsWithIds,
			);
			// Add pending changes if there are any
			if (changes.length > 0) {
				const changesList =
					authorsElement.querySelector(".pending-changes") ||
					document.createElement("ul");
				changesList.className = "pending-changes list-unstyled mt-2";
				changesList.innerHTML = changes
					.map((change) => {
						if (change.type === "add") {
							return `<li class="text-success">
							<i class="bi bi-plus-circle me-1"></i>
							Add: <span class="text-success">${HTMLInjectionManager.escapeHtml(change.name)}</span>
						</li>`;
						} else if (change.type === "remove") {
							return `<li class="text-danger">
							<i class="bi bi-dash-circle me-1"></i>
							Remove: <span class="text-danger">${HTMLInjectionManager.escapeHtml(change.name)}</span>
						</li>`;
						} else if (change.type === "change") {
							return `<li class="text-warning">
							<i class="bi bi-pencil me-1"></i>
							Change Name: "${HTMLInjectionManager.escapeHtml(change.oldName)}" → <span class="text-warning">"${HTMLInjectionManager.escapeHtml(change.newName)}"</span>
						</li>`;
						}
					})
					.join("");
				authorsElement.appendChild(changesList);
			} else {
				// Remove pending changes if no changes
				const changesList = authorsElement.querySelector(".pending-changes");
				if (changesList) {
					changesList.remove();
				}
			}
		} catch (e) {
			authorsElement.innerHTML =
				'<span class="current-value">Error parsing authors.</span>';
		}
	}

	/**
	 * Get current authors with DOM-based stable IDs
	 */
	getCurrentAuthorsWithDOMIds() {
		const authorsList = document.querySelector(".authors-list");
		const currentAuthors = [];

		if (authorsList) {
			// Get all visible author items (not marked for removal)
			const authorItems = authorsList.querySelectorAll(
				".author-item:not(.marked-for-removal)",
			);

			for (const [index, authorItem] of authorItems.entries()) {
				// Get the stable ID from the DOM element
				const authorId = authorItem.id;
				if (!authorId) {
					console.error("❌ Author item missing ID");
					return;
				}

				// Get current values from the inputs
				const nameInput = authorItem.querySelector(".author-name-input");
				const orcidInput = authorItem.querySelector(".author-orcid-input");

				const authorData = {
					name: nameInput?.value || "",
					orcid_id: orcidInput?.value || "",
					_stableId: authorId,
				};

				currentAuthors.push(authorData);
			}
		}

		return currentAuthors;
	}

	/**
	 * Capture authors with DOM-based stable IDs
	 */
	captureAuthorsWithDOMIds(authors) {
		const authorsList = document.querySelector(".authors-list");
		const authorsWithIds = [];

		if (authorsList) {
			// Get author items from DOM
			const authorItems = authorsList.querySelectorAll(".author-item");

			for (const [index, authorItem] of authorItems.entries()) {
				// Get or create a stable ID for this author item
				const authorId = authorItem.id;
				if (!authorId) {
					console.error("❌ Author item missing ID");
					return;
				}

				// Get the author data (either from the authors array or from DOM inputs)
				let authorData;
				if (authors[index]) {
					authorData =
						typeof authors[index] === "string"
							? { name: authors[index], orcid_id: "" }
							: { ...authors[index] };
				} else {
					// Fallback to DOM inputs if author data is missing
					const nameInput = authorItem.querySelector(".author-name-input");
					const orcidInput = authorItem.querySelector(".author-orcid-input");
					authorData = {
						name: nameInput?.value || "",
						orcid_id: orcidInput?.value || "",
					};
				}

				// Add the stable ID
				authorData._stableId = authorId;
				authorsWithIds.push(authorData);
			}
		}

		return authorsWithIds;
	}

	/**
	 * Format authors array into display string
	 */
	formatAuthors(authors) {
		if (!Array.isArray(authors) || authors.length === 0) {
			return "No authors specified.";
		}

		return authors
			.map((author) =>
				typeof author === "string" ? author : author.name || "Unknown",
			)
			.join(", ");
	}

	/**
	 * Calculate author changes between original and current
	 */
	calculateAuthorChanges(originalAuthors, currentAuthors) {
		const changes = [];

		// Create maps using stable IDs
		const originalMap = new Map();
		const currentMap = new Map();

		for (const author of originalAuthors) {
			if (author._stableId) {
				originalMap.set(author._stableId, author);
			}
		}

		for (const author of currentAuthors) {
			if (author._stableId) {
				currentMap.set(author._stableId, author);
			}
		}

		// Find additions (in current but not in original)
		for (const [id, author] of currentMap) {
			if (!originalMap.has(id)) {
				const name = author.name || "Unknown";
				changes.push({ type: "add", name });
			}
		}

		// Find removals (in original but not in current)
		for (const [id, author] of originalMap) {
			if (!currentMap.has(id)) {
				const name = author.name || "Unknown";
				changes.push({ type: "remove", name });
			}
		}

		// Find changes (same ID but different content)
		for (const [id, currentAuthor] of currentMap) {
			const originalAuthor = originalMap.get(id);
			if (originalAuthor) {
				const currentName = currentAuthor.name || "Unknown";
				const originalName = originalAuthor.name || "Unknown";

				const currentOrcid = currentAuthor.orcid_id || "";
				const originalOrcid = originalAuthor.orcid_id || "";

				if (currentName !== originalName) {
					changes.push({
						type: "change",
						oldName: originalName,
						newName: currentName,
					});
				}
				if (currentOrcid !== originalOrcid) {
					changes.push({
						type: "change",
						oldOrcid: originalOrcid,
						newOrcid: currentOrcid,
					});
				}
			}
		}

		return changes;
	}

	/**
	 * Escape HTML to prevent XSS
	 */
	escapeHtml(text) {
		const div = document.createElement("div");
		div.textContent = text;
		return div.innerHTML;
	}
}

// Make class available globally
window.DatasetEditingHandler = DatasetEditingHandler;
