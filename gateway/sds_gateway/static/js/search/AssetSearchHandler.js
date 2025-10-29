/**
 * Asset Search Handler
 * Handles search functionality for captures and files in dataset creation/editing
 * Refactored from SearchHandler to use core components and centralized management
 */
class AssetSearchHandler {
	/**
	 * Initialize asset search handler
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.searchForm = document.getElementById(config.searchFormId);
		this.searchButton = document.getElementById(config.searchButtonId);
		this.clearButton = document.getElementById(config.clearButtonId);
		this.tableBody = document.getElementById(config.tableBodyId);
		this.paginationContainer = document.getElementById(
			config.paginationContainerId,
		);
		this.type = config.type; // 'captures' or 'files'
		this.selectedFiles = new Map(
			Object.entries(config.initialFileDetails || {}),
		);
		this.confirmFileSelection = document.getElementById(
			config.confirmFileSelectionId,
		);
		this.currentTree = null;
		this.formHandler = config.formHandler;
		this.isEditMode = config.isEditMode || false;
		this.currentFilters = {}; // Store current capture filters
		this.selectedCaptureDetails = new Map(
			Object.entries(config.initialCaptureDetails || {}),
		);

		// Configuration
		this.config = {
			apiEndpoint: config.apiEndpoint || window.location.pathname,
			...config,
		};

		// Set the form handler's reference to this SearchHandler instance
		if (config.formHandler) {
			config.formHandler.setSearchHandler(this, config.type);
		}

		this.initializeEventListeners();
	}

	/**
	 * Initialize event listeners
	 */
	initializeEventListeners() {
		// Search form handlers
		if (this.searchButton) {
			this.searchButton.addEventListener("click", () => this.handleSearch());
		}
		if (this.clearButton) {
			this.clearButton.addEventListener("click", () => this.handleClear());
		}
		if (this.confirmFileSelection) {
			this.confirmFileSelection.addEventListener("click", () => {
				if (this.isEditMode) {
					// In edit mode, add selected files to pending changes
					if (window.datasetEditingHandler) {
						for (const [fileId, fileData] of this.selectedFiles.entries()) {
							window.datasetEditingHandler.addFileToPending(fileId, fileData);
						}
					}
				} else {
					// In create mode, update the selected files list
					this.updateSelectedFilesList();
				}
				this.handleClear();
			});
		}
		this.initializeEnterKeyListener();
	}

	/**
	 * Initialize enter key listener
	 */
	initializeEnterKeyListener() {
		// Allow pressing enter when focused on a search input to trigger the search
		const searchInputs = this.searchForm.querySelectorAll("input[type='text']");
		for (const input of searchInputs) {
			input.addEventListener("keypress", (e) => {
				if (e.key === "Enter") {
					this.handleSearch();
				}
			});
		}
	}

	/**
	 * Initialize select all checkbox
	 */
	initializeSelectAllCheckbox() {
		const selectAllCheckbox = document.getElementById(
			"select-all-files-checkbox",
		);
		if (!selectAllCheckbox) return;

		selectAllCheckbox.addEventListener("change", () => {
			const isChecked = selectAllCheckbox.checked;
			const fileCheckboxes = document.querySelectorAll(
				'#file-tree-table tbody input[type="checkbox"]',
			);

			for (const checkbox of fileCheckboxes) {
				if (checkbox.checked !== isChecked) {
					checkbox.checked = isChecked;
					checkbox.dispatchEvent(new Event("change"));
				}
			}
		});
	}

	/**
	 * Initialize remove all button
	 */
	initializeRemoveAllButton() {
		const removeAllButton = document.getElementById(
			"remove-all-selected-files-button",
		);
		if (!removeAllButton) return;

		removeAllButton.addEventListener("click", () => {
			// Check if formHandler has a custom removal handler for edit mode
			if (this.formHandler?.handleRemoveAllFiles) {
				this.formHandler.handleRemoveAllFiles();
			} else {
				// Default behavior for create mode
				// Deselect all files
				const fileCheckboxes = document.querySelectorAll(
					'#file-tree-table tbody input[type="checkbox"]',
				);
				for (const checkbox of fileCheckboxes) {
					checkbox.checked = false;
					checkbox.dispatchEvent(new Event("change"));
				}

				this.selectedFiles.clear();
				this.updateSelectedFilesList();
			}
		});
	}

	/**
	 * Initialize captures search
	 */
	initializeCapturesSearch() {
		// Initialize event listeners for captures search
		const searchButton = document.getElementById("search-captures");
		const clearButton = document.getElementById("clear-captures-search");

		if (!searchButton || !clearButton) return;

		// Add click handler for search button
		searchButton.addEventListener("click", () => {
			this.currentFilters = {
				directory: document.getElementById("search_directory_captures").value,
				capture_type: document.getElementById("search_capture_type").value,
				scan_group: document.getElementById("search_scan_group").value,
				channel: document.getElementById("search_channel").value,
			};
			this.fetchCaptures(this.currentFilters).then((data) =>
				this.updateCapturesTable(data),
			);
		});

		// Add click handler for clear button
		clearButton.addEventListener("click", () => {
			document.getElementById("search_directory_captures").value = "";
			document.getElementById("search_capture_type").value = "";
			document.getElementById("search_scan_group").value = "";
			document.getElementById("search_channel").value = "";
			this.currentFilters = {};
			this.fetchCaptures().then((data) => this.updateCapturesTable(data));
		});

		// Check if the selected captures pane exists and we're not in edit mode
		if (
			!document.getElementById("selected-captures-pane") &&
			!this.formHandler?.datasetUuid
		) {
			// Create selected captures pane only for create mode
			this.createSelectedCapturesPane();
		}

		// Load initial data
		this.fetchCaptures().then((data) => this.updateCapturesTable(data));
	}

	/**
	 * Create selected captures pane
	 */
	createSelectedCapturesPane() {
		// Create the selected captures pane next to the captures table
		const capturesContainer = document.querySelector("#step2 .row");
		if (!capturesContainer) return;

		// Create the pane with static structure (no need for server-side rendering for a one-time static element)
		const selectedPane = document.createElement("div");
		selectedPane.className = "col-md-4";
		selectedPane.innerHTML = `
			<div class="card" id="selected-captures-pane">
				<div class="card-header bg-light d-flex justify-content-between align-items-center">
					<h5 class="mb-0">Selected Captures</h5>
					<span class="badge bg-primary selected-captures-count">0 selected</span>
				</div>
				<div class="card-body p-0">
					<div class="table-responsive">
						<table class="table table-sm table-hover mb-0">
							<thead>
								<tr>
									<th>Type</th>
									<th>Directory</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody id="selected-captures-list">
								<tr><td colspan="3" class="text-center">No captures selected</td></tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>
		`;
		capturesContainer.appendChild(selectedPane);
	}

	/**
	 * Update selected captures pane
	 */
	updateSelectedCapturesPane() {
		const selectedList = document.getElementById("selected-captures-list");
		const countBadge = document.querySelector(".selected-captures-count");
		if (!selectedList || !countBadge || !this.formHandler) return;

		const selectedCaptures = this.formHandler.selectedCaptures;
		countBadge.textContent = `${selectedCaptures.size} selected`;

		// Prepare captures data for server-side rendering
		const capturesData = Array.from(selectedCaptures).map((captureId) => {
			const data = this.selectedCaptureDetails.get(captureId) || {
				type: "Unknown",
				directory: "Unknown",
			};
			return {
				id: captureId,
				type: data.type,
				directory: data.directory,
			};
		});

		this.renderSelectedCapturesTable(selectedList, capturesData);

		// Add remove handlers
		const removeSelectedButtons = selectedList.querySelectorAll(
			".remove-selected-capture",
		);
		for (const button of removeSelectedButtons) {
			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();
				const captureId = button.dataset.id;

				// Check if formHandler has a custom removal handler for edit mode
				if (this.formHandler?.handleCaptureRemoval) {
					this.formHandler.handleCaptureRemoval(captureId);
				} else {
					// Default behavior for create mode
					this.formHandler.selectedCaptures.delete(captureId);
					this.selectedCaptureDetails.delete(captureId);

					// Update checkbox if visible
					const checkbox = document.querySelector(
						`input[name="captures"][value="${captureId}"]`,
					);
					if (checkbox) {
						checkbox.checked = false;
						checkbox.closest("tr").classList.remove("table-warning");
					}

					this.updateSelectedCapturesPane();
					this.formHandler.updateHiddenFields();
				}
			});
		}
	}

	/**
	 * Render selected captures table asynchronously
	 */
	async renderSelectedCapturesTable(selectedList, capturesData) {
		try {
			const response = await window.APIClient.post("/users/render-html/", {
				template: "users/components/selected_captures_table.html",
				context: {
					captures: capturesData,
					empty_message: "No captures selected",
				},
			});

			if (response.html) {
				selectedList.innerHTML = response.html;
			}
		} catch (error) {
			console.error("Error rendering selected captures table:", error);
			// Fallback
			if (capturesData.length === 0) {
				selectedList.innerHTML =
					'<tr><td colspan="3" class="text-center">No captures selected</td></tr>';
			} else {
				selectedList.innerHTML = capturesData
					.map((capture) => `
						<tr data-capture-id="${capture.id}">
							<td>${capture.type}</td>
							<td>${capture.directory}</td>
							<td>
								<button type="button" class="btn btn-sm btn-danger remove-selected-capture" data-id="${capture.id}">
									Remove
								</button>
							</td>
						</tr>
					`)
					.join("");
			}
		}
	}

	/**
	 * Fetch captures data
	 * @param {Object} params - Search parameters
	 * @returns {Promise<Object>} Captures data
	 */
	async fetchCaptures(params = {}) {
		try {
			const searchParams = new URLSearchParams();

			// Add all params to the search parameters
			for (const [key, value] of Object.entries(params)) {
				if (value) {
					searchParams.append(key, value);
				}
			}

			// Always add the search_captures parameter
			searchParams.append("search_captures", "true");

			const data = await window.APIClient.request(
				`${this.config.apiEndpoint}?${searchParams.toString()}`,
				{
					headers: {
						"X-Requested-With": "XMLHttpRequest",
					},
				},
			);

			// APIClient.request already returns parsed JSON data
			return data;
		} catch (error) {
			console.error("Error fetching captures:", error);
			return { results: [], pagination: {} };
		}
	}

	/**
	 * Fetch files data
	 * @param {Object} params - Search parameters
	 * @returns {Promise<Object>} Files data
	 */
	async fetchFiles(params = {}) {
		try {
			const searchParams = new URLSearchParams(params);
			const data = await window.APIClient.request(
				`${this.config.apiEndpoint}?${searchParams.toString()}&search_files=true`,
				{
					headers: {
						"X-Requested-With": "XMLHttpRequest",
					},
				},
			);

			// APIClient.request already returns parsed JSON data
			return data;
		} catch (error) {
			console.error("Error fetching files:", error);
			return { tree: {}, pagination: {} };
		}
	}

	/**
	 * Update captures table
	 * @param {Object} data - Captures data
	 */
	async updateCapturesTable(data) {
		const tbody = document.querySelector("#captures-table tbody");

		// Update the results count
		this.updateResultsCount(data.results.length);

		// Transform captures data for table_rows.html template
		const rows = data.results.map((capture) => {
			const isSelected = this.formHandler?.selectedCaptures.has(
				capture.id.toString(),
			);
			const isOwnedByCurrentUser =
				capture.owner_id === this.formHandler?.currentUserId;
			const canSelect = isOwnedByCurrentUser;
			const ownerName = capture.owner
				? capture.owner.name || capture.owner.email || "-"
				: "-";
			const createdAt = new Date(capture.created_at).toLocaleDateString(
				"en-US",
				{
					month: "2-digit",
					day: "2-digit",
					year: "numeric",
				},
			);

			return {
				id: capture.id,
				css_class: `capture-row${isSelected ? " table-warning" : ""}${!canSelect ? " readonly-row" : ""}`,
				data_attrs: {
					"capture-id": capture.id,
				},
				cells: [
					{
						html: `<input type="checkbox" class="form-check-input capture-checkbox" name="captures" value="${capture.id}"
							${isSelected ? "checked" : ""}
							${!canSelect ? "disabled" : ""}
							data-capture-type="${capture.type}"
							data-capture-directory="${capture.directory}"
							data-capture-channel="${capture.channel}"
							data-capture-scan-group="${capture.scan_group}"
							data-capture-created-at="${capture.created_at}"
							data-capture-owner-id="${capture.owner_id}"
							data-capture-owner-name="${ownerName}" />`,
					},
					{ value: capture.type },
					{ value: capture.directory },
					{ value: capture.channel },
					{ value: capture.scan_group },
					{ value: ownerName },
					{ value: createdAt },
				],
			};
		});

		// Render using DOMUtils
		const success = await window.DOMUtils.renderTable(tbody, rows, {
			empty_message: "No captures found",
			empty_colspan: 7,
		});

		if (success) {
			// Attach event handlers to rendered rows
			this.attachCaptureRowHandlers(tbody);
		} else {
			await window.DOMUtils.renderError(tbody, "Error loading captures", {
				format: "table",
				colspan: 7,
			});
		}

		// Update pagination with current filters
		this.updatePagination("captures", data.pagination);

		// Update selected captures pane
		this.updateSelectedCapturesPane();
	}

	/**
	 * Attach event handlers to capture table rows
	 * @param {Element} tbody - Table body element
	 */
	attachCaptureRowHandlers(tbody) {
		const rows = tbody.querySelectorAll("tr[data-capture-id]");

		for (const row of rows) {
			const checkbox = row.querySelector("input.capture-checkbox");
			if (!checkbox) continue;

			const captureId = checkbox.value;
			const captureData = {
				type: checkbox.dataset.captureType,
				directory: checkbox.dataset.captureDirectory,
				channel: checkbox.dataset.captureChannel,
				scan_group: checkbox.dataset.captureScanGroup,
				created_at: checkbox.dataset.captureCreatedAt,
				owner_id: checkbox.dataset.captureOwnerId,
				owner_name: checkbox.dataset.captureOwnerName,
			};

			const handleSelection = (e) => {
				if (e.target.type !== "checkbox") {
					checkbox.checked = !checkbox.checked;
				}

				if (checkbox.checked) {
					// Check if this is an editing handler
					if (this.formHandler.addCaptureToPending) {
						this.formHandler.addCaptureToPending(captureId, captureData);
					} else {
						// Regular selection for creation
						this.formHandler.selectedCaptures.add(captureId);
						row.classList.add("table-warning");
						this.selectedCaptureDetails.set(captureId, captureData);
						this.formHandler.updateHiddenFields();
						this.updateSelectedCapturesPane();
					}

					if (this.formHandler.updateCurrentCapturesList) {
						this.formHandler.updateCurrentCapturesList();
					}
				} else {
					if (this.formHandler.addCaptureToPending) {
						this.formHandler.cancelCaptureChange(captureId);
					} else {
						this.formHandler.selectedCaptures.delete(captureId);
						row.classList.remove("table-warning");
						this.selectedCaptureDetails.delete(captureId);
						this.formHandler.updateHiddenFields();
						this.updateSelectedCapturesPane();
					}

					if (this.formHandler.updateCurrentCapturesList) {
						this.formHandler.updateCurrentCapturesList();
					}
				}
			};

			// Add click handler for the row
			row.addEventListener("click", handleSelection);

			// Add specific handler for checkbox to prevent double-triggering
			checkbox.addEventListener("change", (e) => {
				e.stopPropagation();
				handleSelection(e);
			});
		}
	}

	/**
	 * Update pagination
	 * @param {string} type - Type of pagination (captures or files)
	 * @param {Object} pagination - Pagination data
	 */
	async updatePagination(type, pagination) {
		const paginationContainer = document.querySelector(`#${type}-pagination`);
		if (!paginationContainer) return;

		const success = await window.DOMUtils.renderPagination(
			paginationContainer,
			pagination,
		);

		if (success && pagination && pagination.num_pages > 1) {
			// Attach click handlers after rendering
			this.attachPaginationHandlers(type, paginationContainer);
		}
	}

	/**
	 * Attach pagination click handlers
	 * @param {string} type - Type of pagination (captures or files)
	 * @param {Element} container - Pagination container element
	 */
	attachPaginationHandlers(type, container) {
		const links = container.querySelectorAll("a.page-link");
		for (const link of links) {
			link.addEventListener("click", async (e) => {
				e.preventDefault();
				const target = e.target.closest("a.page-link");
				const page = target?.dataset.page;

				if (type === "captures") {
					const params = {
						...this.currentFilters,
						page: page,
					};
					const data = await this.fetchCaptures(params);
					this.updateCapturesTable(data);
				} else {
					// Get current search values for files
					const fileNameInput = document.getElementById("file-name");
					const directoryInput = document.getElementById("file-directory");
					const extensionSelect = document.getElementById("file-extension");

					const params = {
						file_name: fileNameInput?.value || "",
						directory: directoryInput?.value || "",
						file_extension: extensionSelect?.value || "",
						page: page,
					};

					const data = await this.fetchFiles(params);
					this.updateFilesTable(data);
				}
			});
		}
	}

	/**
	 * Handle search
	 */
	async handleSearch() {
		try {
			// Get all input elements within the search container
			const searchContainer = this.searchForm;
			if (!searchContainer) {
				console.error("Search container not found:", this.searchForm);
				return;
			}
			const params = new URLSearchParams();

			// Get all form inputs within the container
			const inputs = searchContainer.querySelectorAll(
				"input, select, textarea",
			);
			for (const input of inputs) {
				if (input.value) {
					params.append(input.name, input.value);
				}
			}

			// Add the search type parameter
			params.append(
				this.type === "captures" ? "search_captures" : "search_files",
				"true",
			);

			const data = await window.APIClient.request(
				`${this.config.apiEndpoint}?${params.toString()}`,
				{
					headers: {
						"X-Requested-With": "XMLHttpRequest",
					},
				},
			);

			// APIClient.request already returns parsed JSON data

			if (this.type === "captures") {
				this.updateCapturesTable(data);
			} else {
				// Reset select all checkbox
				const selectAllCheckbox = document.getElementById(
					"select-all-files-checkbox",
				);
				if (selectAllCheckbox) {
					selectAllCheckbox.checked = false;
				}
				if (data.tree) {
					// Update file extension select options while preserving current selection
					const extensionSelect = document.getElementById("file-extension");
					if (extensionSelect && data.extension_choices) {
						const currentValue = extensionSelect.value;
						await this.renderSelectOptions(
							extensionSelect,
							data.extension_choices,
							currentValue,
						);
					}

					// Restore search values if they exist
					if (data.search_values) {
						const fileNameInput = document.getElementById("file-name");
						const directoryInput = document.getElementById("file-directory");

						if (fileNameInput) {
							fileNameInput.value = data.search_values.file_name || "";
						}
						if (extensionSelect) {
							extensionSelect.value = data.search_values.file_extension || "";
						}
						if (directoryInput) {
							directoryInput.value = data.search_values.directory || "";
						}
					}

					const searchTermEntered =
						data.search_values.file_name ||
						data.search_values.directory ||
						data.search_values.file_extension;

					this.renderFileTree(data.tree, null, 0, "", searchTermEntered);

					// Initialize select all checkbox handler for the current file tree
					this.initializeSelectAllCheckbox();

					// Initialize remove all button handler for the current file tree
					this.initializeRemoveAllButton();
				}
			}

			if (data.pagination) {
				this.updatePagination(this.type, data.pagination);
			}
		} catch (error) {
			console.error("Error during search:", error);
			this.showError("An error occurred during the search. Please try again.");
		}
	}

	/**
	 * Handle clear
	 */
	handleClear() {
		// Clear all form inputs
		const searchContainer = this.searchForm;
		if (!searchContainer) {
			console.error("Search container not found:", this.searchForm);
			return;
		}

		const inputs = searchContainer.querySelectorAll("input, select, textarea");
		for (const input of inputs) {
			input.value = "";
		}

		// Trigger a new search with empty parameters
		this.handleSearch();
	}

	/**
	 * Update selected files list
	 */
	updateSelectedFilesList() {
		// Update form handler's selectedFiles with current selection (create mode only)
		if (this.formHandler && !this.isEditMode) {
			// Convert Map entries to array of file objects with IDs
			const fileList = Array.from(this.selectedFiles.entries()).map(
				([id, file]) => ({ ...file, id: id }),
			);
			this.formHandler.selectedFiles = new Set(fileList);
		}

		// Update selected files display input
		const selectedFilesDisplay = document.getElementById(
			"selected-files-display",
		);
		if (selectedFilesDisplay) {
			selectedFilesDisplay.value = `${this.selectedFiles.size} file(s) selected`;
		}

		// Update Remove All button state
		const removeAllButton = document.getElementById(
			"remove-all-selected-files-button",
		);
		if (removeAllButton) {
			removeAllButton.disabled = this.selectedFiles.size === 0;
		}

		// Update selected files table if it exists (only in create mode)
		if (!this.isEditMode) {
			const selectedFilesTable = document.getElementById(
				"selected-files-table",
			);
			const selectedFilesBody = selectedFilesTable?.querySelector("tbody");
			if (selectedFilesBody) {
				this.renderSelectedFilesTable(selectedFilesBody);
			}
		}

		// Update count badge
		const countBadge = document.querySelector(".selected-files-count");
		if (countBadge) {
			countBadge.textContent = `${this.selectedFiles.size} selected`;
		}
	}

	/**
	 * Load file tree
	 */
	async loadFileTree() {
		try {
			// Get current values from form fields
			const fileNameInput = document.getElementById("file-name");
			const directoryInput = document.getElementById("file-directory");
			const extensionSelect = document.getElementById("file-extension");

			const params = {
				file_name: fileNameInput?.value || "",
				directory: directoryInput?.value || "",
				file_extension: extensionSelect?.value || "",
			};

			const data = await this.fetchFiles(params);
			if (!data.tree) {
				console.error("No tree data received:", data);
				return;
			}

			// Update file extension select options
			if (extensionSelect && data.extension_choices) {
				await window.DOMUtils.renderSelectOptions(
					extensionSelect,
					data.extension_choices,
				);
			}

			// Pass the search parameters to renderFileTree
			const searchTermEntered =
				params.file_name || params.directory || params.file_extension;

			this.renderFileTree(data.tree, null, 0, "", searchTermEntered);

			// Initialize search handler after tree is loaded
			this.initializeEventListeners();

			// Initialize select all checkbox handler for the current file tree
			this.initializeSelectAllCheckbox();

			// Initialize remove all button handler for the current file tree
			this.initializeRemoveAllButton();
		} catch (error) {
			console.error("Error loading file tree:", error);
		}
	}

	/**
	 * Get relative path
	 * @param {Object} file - File object
	 * @param {string} currentPath - Current path
	 * @returns {string} Relative path
	 */
	getRelativePath(file, currentPath = "") {
		if (!currentPath) {
			return "";
		}
		return `/${currentPath}`;
	}

	/**
	 * Render file tree
	 * @param {Object} tree - File tree data
	 * @param {HTMLElement} parentElement - Parent element
	 * @param {number} level - Nesting level
	 * @param {string} currentPath - Current path
	 * @param {boolean} searchTermEntered - Whether search term was entered
	 */
	renderFileTree(
		tree,
		parentElement = null,
		level = 0,
		currentPath = "",
		searchTermEntered = false,
	) {
		this.currentTree = tree;
		const targetElement =
			parentElement || document.querySelector("#file-tree-table tbody");
		if (!targetElement) {
			console.error("File tree table body not found");
			return;
		}

		if (!parentElement) {
			targetElement.innerHTML = "";
		}

		// Early return if no tree or if tree is empty
		if (
			!tree ||
			((!tree.files || tree.files.length === 0) &&
				(!tree.children || Object.keys(tree.children).length === 0))
		) {
			targetElement.innerHTML =
				'<tr><td colspan="5" class="text-center">No files or directories found</td></tr>';
			return;
		}

		// Show/hide select all checkbox based on search term
		const selectAllContainer = document.getElementById("select-all-container");
		const hasFiles = tree.files && tree.files.length > 0;
		if (selectAllContainer) {
			if (searchTermEntered && hasFiles) {
				this.formHandler.show(selectAllContainer);
			} else {
				this.formHandler.hide(selectAllContainer);
			}
		}

		// Render directories
		const directories = tree.children || {};

		for (const [name, content] of Object.entries(directories)) {
			if (
				name === "files" ||
				!content ||
				typeof content !== "object" ||
				!content.type ||
				content.type !== "directory"
			) {
				continue;
			}

			const row = document.createElement("tr");
			row.className = "folder-row";

			// Set initial toggle state based on search term only (don't expand by default)
			const initiallyExpanded = searchTermEntered;
			const toggleSymbol = initiallyExpanded ? "▼" : "▶";

			// Construct the path for this directory
			const dirPath = currentPath
				? `${currentPath}/${content.name || name}`
				: content.name || name;

			row.innerHTML = `
				<td>
					<span class="folder-toggle">${toggleSymbol}</span>
				</td>
				<td class="${level > 0 ? `ps-${level * 3}` : ""}">
					<i class="bi bi-folder me-2"></i>
					${content.name || name}
				</td>
				<td>Directory</td>
				<td>${this.formHandler.formatFileSize(content.size || 0)}</td>
				<td>${content.created_at ? new Date(content.created_at).toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" }) : "-"}</td>
			`;
			targetElement.appendChild(row);

			// Create container for nested content
			const nestedContainer = document.createElement("tr");
			nestedContainer.className = "nested-row";
			if (!initiallyExpanded) {
				this.formHandler.hide(nestedContainer);
			} else {
				this.formHandler.show(nestedContainer, "display-table-row");
			}
			nestedContainer.innerHTML = `
				<td colspan="5">
					<div class="nested-content">
						<table class="table table-striped">
							<tbody></tbody>
						</table>
					</div>
				</td>
			`;
			targetElement.appendChild(nestedContainer);

			// Add click handler for folder
			row.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();
				const hasChildren = Object.keys(content.children || {}).length > 0;
				const hasFiles = content.files && content.files.length > 0;
				const expandable = hasChildren || hasFiles;

				const toggle = row.querySelector(".folder-toggle");
				const isExpanded = toggle.textContent === "▼";

				if (expandable) {
					toggle.textContent = isExpanded ? "▶" : "▼";

					if (isExpanded) {
						this.formHandler.hide(nestedContainer, "display-table-row");
					} else {
						this.formHandler.show(nestedContainer, "display-table-row");
					}
				} else {
					toggle.textContent = "▶";
					this.formHandler.hide(nestedContainer, "display-table-row");
				}

				// Load nested content if not already loaded
				if (expandable && !isExpanded && !nestedContainer.dataset.loaded) {
					this.renderFileTree(
						content,
						nestedContainer.querySelector("tbody"),
						level + 1,
						dirPath,
						searchTermEntered,
					);
					nestedContainer.dataset.loaded = "true";
				}
			});

			// If there's a search term or initially expanded, automatically load and expand the content
			if (initiallyExpanded && !nestedContainer.dataset.loaded) {
				this.renderFileTree(
					content,
					nestedContainer.querySelector("tbody"),
					level + 1,
					dirPath,
					searchTermEntered,
				);
				nestedContainer.dataset.loaded = "true";
			}
		}

		// Render files
		if (tree.files && tree.files.length > 0) {
			for (const file of tree.files) {
				const row = document.createElement("tr");
				const filePath = this.getRelativePath(file, currentPath);
				const isSelected = this.selectedFiles.has(file.id);
				row.innerHTML = `
					<td>
						<input type="checkbox" class="form-check-input" name="files" value="${file.id}"
							${isSelected ? "checked" : ""}>
					</td>
					<td class="${level > 0 ? `ps-${level * 3}` : ""}">
						<i class="bi bi-file-earmark me-2"></i>
						${file.name}
					</td>
					<td>${file.media_type || "Unknown"}</td>
					<td>${this.formHandler.formatFileSize(file.size)}</td>
					<td>${new Date(file.created_at).toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" })}</td>
				`;

				const checkbox = row.querySelector('input[type="checkbox"]');

				// Add click handler for the checkbox
				checkbox.addEventListener("change", (e) => {
					e.stopPropagation(); // Prevent row click from firing
					if (checkbox.checked) {
						// Add to intermediate selection (both edit and create mode)
						this.selectedFiles.set(file.id, {
							...file,
							relative_path: filePath,
						});
					} else {
						// Remove from intermediate selection (both edit and create mode)
						this.selectedFiles.delete(file.id);
					}
					this.updateSelectAllCheckboxState();
				});

				// Add click handler for the row
				row.addEventListener("click", (e) => {
					// Don't toggle if clicking the checkbox directly
					if (e.target.type === "checkbox") return;

					checkbox.checked = !checkbox.checked;
					// Trigger the change event to ensure the selectedFiles is updated
					checkbox.dispatchEvent(new Event("change"));
				});

				// Add hover effect class
				row.classList.add("clickable-row");

				targetElement.appendChild(row);
			}
		}

		// Update select all checkbox state when rendering new tree
		this.updateSelectAllCheckboxState();
	}

	/**
	 * Update files table
	 * @param {Object} data - Files data
	 */
	updateFilesTable(data) {
		const tbody = document.querySelector("#file-tree-table tbody");
		if (!tbody) {
			console.error("File tree table body not found");
			return;
		}
		tbody.innerHTML = "";

		if (!data.tree) {
			this.renderEmptyFilesTable(tbody);
			return;
		}

		this.renderFileTree(data.tree);
	}

	/**
	 * Render empty files table asynchronously
	 */
	async renderEmptyFilesTable(tbody) {
		try {
			const response = await window.APIClient.post("/users/render-html/", {
				template: "users/components/empty_table_row.html",
				context: {
					colspan: 5,
					message: "No files or directories found",
				},
			});

			if (response.html) {
				tbody.innerHTML = response.html;
			}
		} catch (error) {
			console.error("Error rendering empty files table:", error);
			// Fallback
			tbody.innerHTML =
				'<tr><td colspan="5" class="text-center">No files or directories found</td></tr>';
		}
	}

	/**
	 * Show error message
	 * @param {string} message - Error message
	 */
	async showError(message) {
		const errorContainer = document.getElementById("formErrors");
		const errorContent = errorContainer?.querySelector(".error-content");
		if (errorContainer && errorContent) {
			await window.DOMUtils.renderError(errorContent, message, {
				format: "list",
			});
			this.formHandler.show(errorContainer);
			errorContainer.scrollIntoView({ behavior: "smooth", block: "start" });
		}
	}

	/**
	 * Render selected files table
	 * @param {Element} tbody - Table body element
	 */
	async renderSelectedFilesTable(tbody) {
		// Transform files data for table_rows.html template
		const rows = Array.from(this.selectedFiles.entries()).map(([id, file]) => {
			const isExistingFile = file.owner_id !== undefined;
			const canRemove =
				!isExistingFile ||
				(isExistingFile && this.formHandler.permissions?.canRemoveAsset(file));

			return {
				id: id,
				css_class: !canRemove ? "readonly-row" : "",
				data_attrs: {
					"file-id": id,
				},
				cells: [
					{ value: file.name },
					{ value: file.media_type },
					{ value: file.relative_path },
					{ value: this.formHandler.formatFileSize(file.size) },
					{ value: file.owner_name || "Unknown" },
				],
				actions: canRemove
					? [
							{
								label: "Remove",
								css_class: "btn-danger",
								extra_class: "remove-selected-file",
								data_attrs: { id: id },
							},
						]
					: [],
			};
		});

		// Render using DOMUtils
		const success = await window.DOMUtils.renderTable(tbody, rows, {
			empty_message: "No files selected",
			empty_colspan: 6,
		});

		if (success) {
			// Attach event handlers to remove buttons
			this.attachFileRemovalHandlers(tbody);
		} else {
			await window.DOMUtils.renderError(tbody, "Error loading files", {
				format: "table",
				colspan: 6,
			});
		}
	}

	/**
	 * Attach event handlers to file removal buttons
	 * @param {Element} tbody - Table body element
	 */
	attachFileRemovalHandlers(tbody) {
		const removeButtons = tbody.querySelectorAll(".remove-selected-file");
		for (const button of removeButtons) {
			button.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();
				const fileId = button.dataset.id;

				// Check if formHandler has a custom removal handler for edit mode
				if (this.formHandler?.handleFileRemoval) {
					this.formHandler.handleFileRemoval(fileId);
				} else {
					// Default behavior for create mode
					this.selectedFiles.delete(fileId);
					// Update checkbox in file tree if visible
					const checkbox = document.querySelector(
						`input[name="files"][value="${fileId}"]`,
					);
					if (checkbox) {
						checkbox.checked = false;
					}
					// Update the selected files list
					this.updateSelectedFilesList();
					// Update form handler's hidden fields
					if (this.formHandler) {
						this.formHandler.updateHiddenFields();
					}
				}
			});
		}
	}

	/**
	 * Update select all checkbox state
	 */
	updateSelectAllCheckboxState() {
		const selectAllCheckbox = document.getElementById(
			"select-all-files-checkbox",
		);
		if (!selectAllCheckbox) return;

		// Only count visible file checkboxes (not in hidden rows)
		const fileCheckboxes = document.querySelectorAll(
			'#file-tree-table tbody tr:not(.nested-row):not([style*="display: none"]) input[type="checkbox"]',
		);
		const checkedBoxes = document.querySelectorAll(
			'#file-tree-table tbody tr:not(.nested-row):not([style*="display: none"]) input[type="checkbox"]:checked',
		);

		if (checkedBoxes.length === fileCheckboxes.length) {
			selectAllCheckbox.checked = true;
		} else {
			selectAllCheckbox.checked = false;
		}
	}

	/**
	 * Update results count
	 * @param {number} count - Results count
	 */
	updateResultsCount(count) {
		const resultsCountElement = document.getElementById("results-count");
		if (resultsCountElement) {
			const captureText = count === 1 ? "capture" : "captures";
			resultsCountElement.textContent = `${count} ${captureText} found`;
		}
	}
}

// Make class available globally
window.AssetSearchHandler = AssetSearchHandler;

// Export for ES6 modules (Jest testing)
export { AssetSearchHandler };
