/**
 * Dataset Creation Handler
 * Handles dataset creation workflow and form management
 */
class DatasetCreationHandler {
	/**
	 * Initialize dataset creation handler
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.form = document.getElementById(config.formId);
		this.steps = config.steps || [];
		this.currentStep = 0;
		this.onStepChange = config.onStepChange;

		// Navigation elements
		this.prevBtn = document.getElementById("prevStep");
		this.nextBtn = document.getElementById("nextStep");
		this.submitBtn = document.getElementById("submitForm");
		this.stepTabs = document.querySelectorAll("#stepTabs .btn");

		// Form fields
		this.nameField = document.getElementById("id_name");
		this.authorsField = document.getElementById("id_authors");
		this.statusField = document.getElementById("id_status");
		this.descriptionField = document.getElementById("id_description");

		// Hidden fields
		this.selectedCapturesField = document.getElementById("selected_captures");
		this.selectedFilesField = document.getElementById("selected_files");

		// Selections
		this.selectedCaptures = new Set(); // Set of capture IDs
		this.selectedFiles = new Set(); // Set of file objects for the main card
		this.selectedCaptureDetails = new Map(); // Map of capture ID -> capture details

		// File browser modal state (intermediate selections)
		this.modalSelectedFiles = new Set(); // Set of file objects for modal intermediate state

		// Search handlers
		this.capturesSearchHandler = null;
		this.filesSearchHandler = null;

		this.initializeEventListeners();
		this.initializeErrorContainer();
		this.initializeAuthorsManagement();
		this.initializePlaceholders();
		this.validateCurrentStep();
		this.updateNavigation();
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
				isEditMode: false,
				apiEndpoint: window.location.pathname,
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
				isEditMode: false,
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
		}

		// Prevent form submission on enter key
		if (this.form) {
			this.form.addEventListener("keypress", (e) => {
				if (e.key === "Enter") {
					e.preventDefault();
				}
			});
		}

		// Navigation buttons
		if (this.prevBtn) {
			this.prevBtn.addEventListener("click", (e) => {
				e.stopPropagation();
				this.navigateStep(-1);
			});
		}

		if (this.nextBtn) {
			this.nextBtn.addEventListener("click", (e) => {
				e.stopPropagation();
				this.navigateStep(1);
			});
		}

		// Step tab handlers
		for (const [index, tab] of this.stepTabs.entries()) {
			tab.addEventListener("click", () => {
				if (index <= this.currentStep) {
					this.currentStep = index;
					this.updateNavigation();
					if (this.onStepChange) {
						this.onStepChange(this.currentStep);
					}
				}
			});
		}

		// Form field validation
		if (this.nameField) {
			this.nameField.addEventListener("input", () =>
				this.validateCurrentStep(),
			);
		}
		if (this.authorsField) {
			this.authorsField.addEventListener("input", () =>
				this.validateCurrentStep(),
			);
		}
		if (this.statusField) {
			this.statusField.addEventListener("change", () =>
				this.validateCurrentStep(),
			);
		}

		// Capture selection handler (direct table selection)
		document.addEventListener("change", (e) => {
			if (e.target.matches('input[name="captures"]')) {
				this.handleCaptureSelection(e.target);
			}
		});

		// File browser modal handlers
		this.initializeFileBrowserModal();
	}

	/**
	 * Initialize error container
	 */
	initializeErrorContainer() {
		const errorContainer = document.getElementById("formErrors");
		if (errorContainer) {
			this.hide(errorContainer);
		}
	}

	/**
	 * Initialize placeholder text for empty tables
	 */
	initializePlaceholders() {
		// Initialize selected files table with placeholder
		const selectedFilesTable = document.getElementById("selected-files-table");
		const selectedFilesBody = selectedFilesTable?.querySelector("tbody");
		if (selectedFilesBody && selectedFilesBody.innerHTML.trim() === "") {
			selectedFilesBody.innerHTML =
				'<tr><td colspan="6" class="text-center text-muted">No files selected</td></tr>';
		}

		// Initialize captures selection table with placeholder
		const capturesSelectionTable = document.getElementById(
			"captures-table-body",
		);
		if (
			capturesSelectionTable &&
			capturesSelectionTable.innerHTML.trim() === ""
		) {
			capturesSelectionTable.innerHTML =
				'<tr><td colspan="7" class="text-center text-muted">No captures found</td></tr>';
		}

		// Initialize captures table on review step with placeholder (will be updated later)
		const capturesTable = document.querySelector(
			"#step4 .captures-table tbody",
		);
		if (capturesTable && capturesTable.innerHTML.trim() === "") {
			capturesTable.innerHTML =
				'<tr><td colspan="6" class="text-center text-muted">No captures selected</td></tr>';
		}

		// Initialize files table on review step with placeholder (will be updated later)
		const filesTable = document.querySelector("#step4 .files-table tbody");
		if (filesTable && filesTable.innerHTML.trim() === "") {
			filesTable.innerHTML =
				'<tr><td colspan="5" class="text-center text-muted">No files selected</td></tr>';
		}
	}

	/**
	 * Initialize file browser modal handlers
	 */
	initializeFileBrowserModal() {
		// Modal file selection handlers
		document.addEventListener("change", (e) => {
			if (e.target.matches('#file-tree-table input[name="files"]')) {
				this.handleModalFileSelection(e.target);
			}
		});

		// Select all files checkbox
		const selectAllCheckbox = document.getElementById(
			"select-all-files-checkbox",
		);
		if (selectAllCheckbox) {
			selectAllCheckbox.addEventListener("change", (e) => {
				this.handleSelectAllFiles(e.target.checked);
			});
		}

		// Confirm file selection button
		const confirmButton = document.getElementById("confirm-file-selection");
		if (confirmButton) {
			confirmButton.addEventListener("click", () => {
				this.confirmFileSelection();
			});
		}

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

		// Remove all files button
		const removeAllButton = document.getElementById(
			"remove-all-selected-files-button",
		);
		if (removeAllButton) {
			removeAllButton.addEventListener("click", () => {
				this.removeAllSelectedFiles();
			});
		}
	}

	/**
	 * Handle capture selection from direct table
	 * @param {Element} checkbox - Checkbox element
	 */
	handleCaptureSelection(checkbox) {
		const captureId = checkbox.value;
		const row = checkbox.closest("tr");

		if (checkbox.checked) {
			// Add to selected captures
			this.selectedCaptures.add(captureId);

			// Highlight the row
			if (row) {
				row.classList.add("table-warning");
			}

			// Store capture details if available from search handler
			if (this.capturesSearchHandler?.selectedCaptureDetails) {
				const captureDetails =
					this.capturesSearchHandler.selectedCaptureDetails.get(captureId);
				if (captureDetails) {
					this.selectedCaptureDetails.set(captureId, captureDetails);
				}
			}
		} else {
			// Remove from selected captures
			this.selectedCaptures.delete(captureId);
			this.selectedCaptureDetails.delete(captureId);

			// Remove highlight from row
			if (row) {
				row.classList.remove("table-warning");
			}
		}

		this.updateHiddenFields();
		this.updateSelectedCapturesPanel();
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
	 * Handle modal file selection (intermediate state)
	 * @param {Element} checkbox - Checkbox element
	 */
	handleModalFileSelection(checkbox) {
		const fileId = checkbox.value;
		const row = checkbox.closest("tr");

		// Get file data from the row
		const fileData = this.getFileDataFromRow(row);

		if (checkbox.checked) {
			// Add to modal intermediate selection
			this.modalSelectedFiles.add(fileData);
		} else {
			// Remove from modal intermediate selection
			this.modalSelectedFiles.delete(fileData);
		}

		// Update select all checkbox state
		this.updateSelectAllCheckbox();
	}

	/**
	 * Get file data from table row
	 * @param {Element} row - Table row element
	 * @returns {Object} File data object
	 */
	getFileDataFromRow(row) {
		const cells = row.querySelectorAll("td");
		return {
			id: row.querySelector('input[name="files"]').value,
			name: cells[1]?.textContent?.trim() || "",
			media_type: cells[2]?.textContent?.trim() || "",
			relative_path: cells[3]?.textContent?.trim() || "",
			size: cells[4]?.textContent?.trim() || "",
			created_at: cells[5]?.textContent?.trim() || "",
		};
	}

	/**
	 * Handle select all files checkbox
	 * @param {boolean} checked - Whether select all is checked
	 */
	handleSelectAllFiles(checked) {
		const checkboxes = document.querySelectorAll(
			'#file-tree-table input[name="files"]',
		);
		for (const checkbox of checkboxes) {
			checkbox.checked = checked;
			this.handleModalFileSelection(checkbox);
		}
	}

	/**
	 * Update select all checkbox state
	 */
	updateSelectAllCheckbox() {
		const selectAllCheckbox = document.getElementById(
			"select-all-files-checkbox",
		);
		const allCheckboxes = document.querySelectorAll(
			'#file-tree-table input[name="files"]',
		);

		if (selectAllCheckbox && allCheckboxes.length > 0) {
			const checkedCount = Array.from(allCheckboxes).filter(
				(cb) => cb.checked,
			).length;
			selectAllCheckbox.checked = checkedCount === allCheckboxes.length;
			selectAllCheckbox.indeterminate =
				checkedCount > 0 && checkedCount < allCheckboxes.length;
		}
	}

	/**
	 * Confirm file selection (move from modal to main selection)
	 */
	confirmFileSelection() {
		// Add modal selections to main selection
		for (const file of this.modalSelectedFiles) {
			this.selectedFiles.add(file);
		}

		// Clear modal selections
		this.modalSelectedFiles.clear();

		// Update UI
		this.updateSelectedFilesDisplay();
		this.updateHiddenFields();

		// Close modal
		const modal = bootstrap.Modal.getInstance(
			document.getElementById("fileTreeModal"),
		);
		if (modal) {
			modal.hide();
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
		this.modalSelectedFiles.clear();
	}

	/**
	 * Remove all selected files
	 */
	removeAllSelectedFiles() {
		// Clear main selection
		this.selectedFiles.clear();

		// Clear modal intermediate selection
		this.modalSelectedFiles.clear();

		// Update UI
		this.updateSelectedFilesDisplay();
		this.updateHiddenFields();

		// Uncheck all checkboxes in modal if it's open
		const checkboxes = document.querySelectorAll(
			'#file-tree-table input[name="files"]',
		);
		for (const checkbox of checkboxes) {
			checkbox.checked = false;
		}

		// Update select all checkbox
		this.updateSelectAllCheckbox();
	}

	/**
	 * Update selected files display
	 */
	updateSelectedFilesDisplay() {
		const displayInput = document.getElementById("selected-files-display");
		const count = this.selectedFiles.size;

		if (displayInput) {
			displayInput.value = `${count} file(s) selected`;
		}

		// Update selected files table
		this.updateSelectedFilesTable();
	}

	/**
	 * Navigate between steps
	 * @param {number} direction - Direction to navigate (-1 or 1)
	 */
	async navigateStep(direction) {
		if (direction < 0 || this.validateCurrentStep()) {
			const nextStep = this.currentStep + direction;

			// Update review step if moving to it
			if (nextStep === 3) {
				this.updateReviewStep();
			}

			this.currentStep = nextStep;
			this.updateNavigation();
			this.updateDatasetNameDisplay();

			if (this.onStepChange) {
				this.onStepChange(this.currentStep);
			}
		}
	}

	/**
	 * Update review step content
	 */
	updateReviewStep() {
		// Update dataset name
		const nameDisplay = document.querySelector("#step4 .dataset-name");
		if (nameDisplay) {
			nameDisplay.textContent = this.nameField ? this.nameField.value : "";
		}

		// Update authors display
		if (window.updateReviewAuthorsDisplay) {
			window.updateReviewAuthorsDisplay();
		} else {
			this.updateAuthorsDisplayFallback();
		}

		// Update status display
		const statusDisplay = document.querySelector("#step4 .dataset-status");
		if (statusDisplay) {
			if (this.statusField?.options && this.statusField.selectedIndex >= 0) {
				statusDisplay.textContent =
					this.statusField.options[this.statusField.selectedIndex].text;
			} else {
				statusDisplay.textContent = "";
			}
		}

		// Update description display
		const descriptionDisplay = document.querySelector(
			"#step4 .dataset-description",
		);
		if (descriptionDisplay) {
			descriptionDisplay.textContent = this.descriptionField
				? this.descriptionField.value
				: "No description provided.";
		}

		// Update selected items table
		this.updateSelectedItemsTable();
	}

	/**
	 * Update authors display fallback
	 */
	updateAuthorsDisplayFallback() {
		const authorsField = document.getElementById("id_authors");
		const authorsDisplay = document.querySelector("#step4 .dataset-authors");

		if (authorsField?.value && authorsDisplay) {
			try {
				const authors = JSON.parse(authorsField.value);
				const authorNames = authors.map((author) => {
					if (typeof author === "string") {
						return author;
					}
					if (author?.name) {
						return author.name;
					}
					return "Unnamed Author";
				});
				authorsDisplay.textContent = authorNames.join(", ");
			} catch (e) {
				authorsDisplay.textContent = authorsField.value;
			}
		} else if (authorsDisplay) {
			authorsDisplay.textContent = "No authors specified";
		}
	}

	/**
	 * Update dataset name display
	 */
	updateDatasetNameDisplay() {
		const nameDisplays = document.getElementsByClassName(
			"dataset-name-display",
		);
		if (this.nameField && nameDisplays.length > 0) {
			for (const nameDisplay of Array.from(nameDisplays)) {
				nameDisplay.textContent = this.nameField.value || "Untitled Dataset";
			}
		}
	}

	/**
	 * Update navigation state
	 */
	updateNavigation() {
		// Update step tabs
		for (const [index, tab] of this.stepTabs.entries()) {
			tab.classList.remove(
				"btn-outline-primary",
				"btn-primary",
				"active-tab",
				"inactive-tab",
			);

			if (index === this.currentStep) {
				tab.classList.add("btn-primary", "active-tab");
			} else if (index > this.currentStep) {
				tab.classList.add("btn-outline-primary", "inactive-tab");
			} else {
				tab.classList.add("btn-primary", "inactive-tab");
			}
		}

		// Update content panes
		for (const [index, pane] of document
			.querySelectorAll(".tab-pane")
			.entries()) {
			pane.classList.remove("show", "active");
			if (index === this.currentStep) {
				pane.classList.add("show", "active");
			}
		}

		// Update navigation buttons
		if (this.prevBtn) {
			this.currentStep > 0 ? this.show(this.prevBtn) : this.hide(this.prevBtn);
		}

		const isValid = this.validateCurrentStep();

		if (this.nextBtn) {
			const isLastStep = this.currentStep === this.steps.length - 1;
			isLastStep ? this.hide(this.nextBtn) : this.show(this.nextBtn);
			this.nextBtn.disabled = !isValid;
		}

		if (this.submitBtn) {
			const isLastStep = this.currentStep === this.steps.length - 1;
			if (isLastStep) {
				this.show(this.submitBtn);
				this.submitBtn.disabled = !isValid;
			} else {
				this.hide(this.submitBtn);
			}
		}
	}

	/**
	 * Validate current step
	 * @returns {boolean} Whether current step is valid
	 */
	validateCurrentStep() {
		let isValid = true;

		switch (this.currentStep) {
			case 0:
				isValid = this.validateDatasetInfo();
				break;
			case 1:
				isValid = this.validateCapturesSelection();
				break;
			case 2:
				isValid = this.validateFilesSelection();
				break;
			default:
				isValid = true;
		}

		// Update button states
		if (this.nextBtn) {
			this.nextBtn.disabled = !isValid;
		}
		if (this.submitBtn && this.currentStep === this.steps.length - 1) {
			this.submitBtn.disabled = !isValid;
		}

		return isValid;
	}

	/**
	 * Validate dataset info step
	 * @returns {boolean} Whether dataset info is valid
	 */
	validateDatasetInfo() {
		const nameValue = this.nameField?.value.trim() || "";
		const authorsValue = this.authorsField?.value.trim() || "";
		const statusValue = this.statusField?.value || "";

		// Validate authors JSON
		if (authorsValue) {
			try {
				const authors = JSON.parse(authorsValue);
				if (!Array.isArray(authors) || authors.length === 0) {
					return false;
				}
			} catch (e) {
				return false;
			}
		}

		return nameValue !== "" && authorsValue !== "" && statusValue !== "";
	}

	/**
	 * Validate captures selection step
	 * @returns {boolean} Whether captures selection is valid
	 */
	validateCapturesSelection() {
		return true; // Captures selection is optional
	}

	/**
	 * Validate files selection step
	 * @returns {boolean} Whether files selection is valid
	 */
	validateFilesSelection() {
		return true; // Files selection is optional
	}

	/**
	 * Handle form submission
	 * @param {Event} e - Submit event
	 */
	async handleSubmit(e) {
		e.preventDefault();

		if (!this.validateCurrentStep()) {
			return;
		}

		// Set loading state
		this.setSubmitButtonLoading(true);

		// Update hidden fields
		this.updateHiddenFields();

		// Clear existing errors
		this.clearErrors();

		const formData = new FormData(this.form);

		try {
			const response = await window.APIClient.request(this.form.action, {
				method: "POST",
				body: formData,
			});

			if (response.success) {
				window.location.href = response.redirect_url;
			} else if (response.errors) {
				throw new APIError("Validation failed", 400, response.errors);
			}
		} catch (error) {
			console.error("Error submitting form:", error);
			this.handleSubmissionError(error);
		} finally {
			this.setSubmitButtonLoading(false);
		}
	}

	/**
	 * Handle submission error
	 * @param {Error} error - Error object
	 */
	handleSubmissionError(error) {
		let errorMessage;

		if (error instanceof APIError && error.data.errors) {
			// Use HTMLInjectionManager to create error message HTML
			errorMessage = window.HTMLInjectionManager.createErrorMessage(
				error.data.errors,
			);
		} else {
			errorMessage = "An unexpected error occurred. Please try again.";
		}

		// Use the new notification system
		window.HTMLInjectionManager.showNotification(errorMessage, "danger", {
			containerId: "formErrors",
			autoHide: false, // Don't auto-hide error messages
			scrollTo: true,
			replace: true,
			icon: true,
			dismissible: true,
		});
	}

	/**
	 * Clear form errors
	 */
	clearErrors() {
		window.HTMLInjectionManager.clearNotifications("formErrors");
	}

	/**
	 * Set submit button loading state
	 * @param {boolean} isLoading - Whether button is loading
	 */
	setSubmitButtonLoading(isLoading) {
		if (!this.submitBtn) return;

		if (isLoading) {
			this.submitBtn.dataset.originalText = this.submitBtn.textContent;
			this.submitBtn.disabled = true;
			this.submitBtn.innerHTML =
				window.HTMLInjectionManager.createLoadingSpinner("Creating...");
		} else {
			this.submitBtn.disabled = false;
			if (this.submitBtn.dataset.originalText) {
				this.submitBtn.textContent = this.submitBtn.dataset.originalText;
			}
		}
	}

	/**
	 * Update selected items table in review step
	 */
	updateSelectedItemsTable() {
		this.updateSelectedCapturesTable();
		this.updateSelectedFilesTable();
		this.updateSelectionCounts();
	}

	/**
	 * Update selected captures table
	 */
	updateSelectedCapturesTable() {
		const capturesTableBody = document.querySelector(
			"#step4 .captures-table tbody",
		);

		if (!capturesTableBody) return;

		if (this.selectedCaptures.size > 0 && this.capturesSearchHandler) {
			const rows = Array.from(this.selectedCaptures)
				.map((captureId) => {
					const data = this.capturesSearchHandler.selectedCaptureDetails.get(
						captureId,
					) || {
						type: "Unknown",
						directory: "Unknown",
						channel: "-",
						scan_group: "-",
						created_at: new Date().toISOString(),
					};

					return window.HTMLInjectionManager.createTableRow(
						data,
						`
					<tr>
						<td>{{type}}</td>
						<td>{{directory}}</td>
						<td>{{channel}}</td>
						<td>{{scan_group}}</td>
						<td>{{created_at}}</td>
						<td>
							<button class="btn btn-sm btn-danger remove-capture" data-id="${captureId}">
								Remove
							</button>
						</td>
					</tr>
				`,
						{ dateFormat: "en-US" },
					);
				})
				.join("");

			window.HTMLInjectionManager.injectHTML(capturesTableBody, rows, {
				escape: false,
			});
			this.attachCaptureRemoveHandlers();
		} else {
			window.HTMLInjectionManager.injectHTML(
				capturesTableBody,
				"<tr><td colspan='6' class='text-center'>No captures selected</td></tr>",
				{ escape: false },
			);
		}
	}

	/**
	 * Update selected captures side panel
	 */
	updateSelectedCapturesPanel() {
		const selectedCapturesTable = document.getElementById(
			"selected-captures-table",
		);
		const selectedCapturesBody = selectedCapturesTable?.querySelector("tbody");
		const selectedCapturesCount = document.getElementById(
			"selected-captures-count",
		);

		if (!selectedCapturesBody) return;

		if (this.selectedCaptures.size > 0 && this.capturesSearchHandler) {
			const rows = Array.from(this.selectedCaptures)
				.map((captureId) => {
					const data = this.capturesSearchHandler.selectedCaptureDetails.get(
						captureId,
					) || {
						type: "Unknown",
						directory: "Unknown",
					};

					return window.HTMLInjectionManager.createTableRow(
						data,
						`
					<tr>
						<td>{{type}}</td>
						<td>{{directory}}</td>
						<td>
							<button class="btn btn-sm btn-outline-danger remove-selected-capture" data-id="${captureId}" title="Remove from selection">
								<i class="bi bi-x"></i>
							</button>
						</td>
					</tr>
				`,
					);
				})
				.join("");

			window.HTMLInjectionManager.injectHTML(selectedCapturesBody, rows, {
				escape: false,
			});

			// Add event listeners for remove buttons
			const removeButtons = selectedCapturesBody.querySelectorAll(
				".remove-selected-capture",
			);
			for (const button of removeButtons) {
				button.addEventListener("click", (e) => {
					const captureId = e.target.closest("button").dataset.id;
					this.removeCapture(captureId);
				});
			}
		} else {
			window.HTMLInjectionManager.injectHTML(
				selectedCapturesBody,
				"<tr><td colspan='3' class='text-center text-muted'>No captures selected</td></tr>",
				{ escape: false },
			);
		}

		// Update count badge
		if (selectedCapturesCount) {
			selectedCapturesCount.textContent = `${this.selectedCaptures.size} selected`;
		}
	}

	/**
	 * Update selected files table
	 */
	updateSelectedFilesTable() {
		const filesTableBody = document.querySelector("#step4 .files-table tbody");

		if (!filesTableBody) return;

		if (this.selectedFiles.size > 0) {
			const rows = Array.from(this.selectedFiles)
				.map((file) => {
					return window.HTMLInjectionManager.createTableRow(
						file,
						`
					<tr>
						<td>{{name}}</td>
						<td>{{media_type}}</td>
						<td>{{relative_path}}</td>
						<td>{{size}}</td>
						<td>
							<button class="btn btn-sm btn-danger remove-file" data-id="{{id}}">
								Remove
							</button>
						</td>
					</tr>
				`,
					);
				})
				.join("");

			window.HTMLInjectionManager.injectHTML(filesTableBody, rows, {
				escape: false,
			});
			this.attachFileRemoveHandlers();
		} else {
			window.HTMLInjectionManager.injectHTML(
				filesTableBody,
				"<tr><td colspan='5' class='text-center'>No files selected</td></tr>",
				{ escape: false },
			);
		}
	}

	/**
	 * Update selection counts
	 */
	updateSelectionCounts() {
		const capturesCount = this.selectedCaptures.size;
		const filesCount = this.selectedFiles.size;

		const capturesCountElement = document.querySelector(
			"#step4 .captures-count",
		);
		const filesCountElement = document.querySelector("#step4 .files-count");

		if (capturesCountElement) {
			capturesCountElement.textContent = `${capturesCount} selected`;
		}
		if (filesCountElement) {
			filesCountElement.textContent = `${filesCount} selected`;
		}
	}

	/**
	 * Attach capture remove handlers
	 */
	attachCaptureRemoveHandlers() {
		const removeButtons = document.querySelectorAll(".remove-capture");
		for (const button of removeButtons) {
			button.addEventListener("click", () => {
				const captureId = button.dataset.id;
				this.removeCapture(captureId);
			});
		}
	}

	/**
	 * Attach file remove handlers
	 */
	attachFileRemoveHandlers() {
		const removeButtons = document.querySelectorAll(".remove-file");
		for (const button of removeButtons) {
			button.addEventListener("click", () => {
				const fileId = button.dataset.id;
				this.removeFile(fileId);
			});
		}
	}

	/**
	 * Remove capture from selection
	 * @param {string} captureId - Capture ID to remove
	 */
	removeCapture(captureId) {
		this.selectedCaptures.delete(captureId);
		if (this.capturesSearchHandler) {
			this.capturesSearchHandler.selectedCaptureDetails.delete(captureId);
		}
		this.updateHiddenFields();
		this.updateSelectedItemsTable();
		this.updateSelectedCapturesPanel();

		// Update checkbox in captures table if visible
		const checkbox = document.querySelector(
			`input[name="captures"][value="${captureId}"]`,
		);
		if (checkbox) {
			checkbox.checked = false;
			const row = checkbox.closest("tr");
			if (row) {
				row.classList.remove("table-warning");
			}
		}
	}

	/**
	 * Remove file from selection
	 * @param {string} fileId - File ID to remove
	 */
	removeFile(fileId) {
		// Remove from main selection
		const fileToRemove = Array.from(this.selectedFiles).find(
			(f) => f.id === fileId,
		);
		if (fileToRemove) {
			this.selectedFiles.delete(fileToRemove);
		}

		// Remove from modal intermediate selection
		const modalFileToRemove = Array.from(this.modalSelectedFiles).find(
			(f) => f.id === fileId,
		);
		if (modalFileToRemove) {
			this.modalSelectedFiles.delete(modalFileToRemove);
		}

		// Update UI
		this.updateSelectedFilesDisplay();
		this.updateHiddenFields();
		this.updateSelectedItemsTable();

		// Update checkbox in file tree modal if visible
		const checkbox = document.querySelector(
			`input[name="files"][value="${fileId}"]`,
		);
		if (checkbox) {
			checkbox.checked = false;
		}

		// Update select all checkbox
		this.updateSelectAllCheckbox();
	}

	/**
	 * Set search handler reference
	 * @param {Object} searchHandler - Search handler instance
	 * @param {string} type - Handler type (captures or files)
	 */
	setSearchHandler(searchHandler, type) {
		if (type === "captures") {
			this.capturesSearchHandler = searchHandler;
		} else if (type === "files") {
			this.filesSearchHandler = searchHandler;
			// Files search handler manages the modal file tree, not the main selection
			// The main selection is managed by this handler
		}
	}

	/**
	 * Update hidden fields with current selections
	 */
	updateHiddenFields() {
		// Update captures hidden field
		if (this.selectedCapturesField) {
			this.selectedCapturesField.value = Array.from(this.selectedCaptures).join(
				",",
			);
		}

		// Update files hidden field
		if (this.selectedFilesField) {
			const fileIds = Array.from(this.selectedFiles).map((file) =>
				typeof file === "object" ? file.id : file,
			);
			this.selectedFilesField.value = fileIds.join(",");
		}
	}

	/**
	 * Initialize authors management for creation mode
	 */
	initializeAuthorsManagement() {
		const authorsContainer = document.getElementById("authors-container");
		const authorsList = authorsContainer?.querySelector(".authors-list");
		const addAuthorBtn = document.getElementById("add-author-btn");
		const authorsHiddenField = document.getElementById("id_authors");

		if (!authorsContainer || !authorsList || !authorsHiddenField) return;

		// Get initial authors from the hidden field
		let authors = [];
		try {
			const initialAuthors = authorsHiddenField.value;
			if (initialAuthors && initialAuthors.trim() !== "") {
				authors = JSON.parse(initialAuthors);
			}
		} catch (e) {
			console.error("Error parsing initial authors:", e);
		}

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

		// If no authors, add the current user as the first author
		if (authors.length === 0) {
			const currentUserName =
				document.body.dataset.currentUserName || "Current User";
			const currentUserOrcid = document.body.dataset.currentUserOrcid || "";
			authors = [
				{
					name: currentUserName,
					orcid_id: currentUserOrcid,
				},
			];
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
										: `<button type="button" class="btn btn-sm btn-outline-danger remove-author" data-index="${index}" title="Remove author"><i class="bi bi-trash"></i></button>`
								}
							</div>
						</div>
						<div class="row g-2">
							<div class="col-6">
								<label class="form-label small">Author Name</label>
								<input type="text"
									   class="form-control author-name-input"
									   value="${window.HTMLInjectionManager.escapeHtml(authorName)}"
									   placeholder="Enter full name"
									   ${index === 0 ? "readonly" : ""}
									   data-index="${index}"
									   data-field="name">
							</div>
							<div class="col-6">
								<label class="form-label small">ORCID ID</label>
								<input type="text"
									   class="form-control author-orcid-input"
									   value="${window.HTMLInjectionManager.escapeHtml(authorOrcid)}"
									   placeholder="0000-0000-0000-0000"
									   ${index === 0 ? "readonly" : ""}
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

			// Show add button in create mode (always available)
			if (addAuthorBtn) {
				addAuthorBtn.style.display = "";
			}
		};

		/**
		 * Add new author
		 */
		const addAuthor = () => {
			authors.push({
				name: "",
				orcid_id: "",
			});

			updateAuthorsDisplay();

			// Focus on the new name input
			const newInput = authorsList.querySelector(
				`input[data-index="${authors.length - 1}"][data-field="name"]`,
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
				authors.splice(index, 1);
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
		 * Show notification using HTMLInjectionManager
		 */
		this.showNotification = (message, type = "info") => {
			window.HTMLInjectionManager.showNotification(message, type, {
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

				authors[index][field] = e.target.value;

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

		// Handle remove buttons
		authorsList.addEventListener("click", (e) => {
			const removeButton = e.target.closest(".remove-author");

			if (removeButton) {
				e.preventDefault();
				e.stopPropagation();
				const index = Number.parseInt(removeButton.dataset.index);
				removeAuthor(index);
			}
		});

		// Initial display
		updateAuthorsDisplay();

		// Store authors for external access
		this.authors = authors;
		this.updateAuthorsDisplay = updateAuthorsDisplay;

		// Make author display functions available for review (simple version for creation mode)
		window.updateDatasetAuthors = (authorsField) =>
			this.updateDatasetAuthors(authorsField);
		window.formatAuthors = (authors) => this.formatAuthors(authors);
		window.escapeHtml = (text) => window.HTMLInjectionManager.escapeHtml(text);
	}

	/**
	 * Update dataset authors for review display (simple version for creation mode)
	 */
	updateDatasetAuthors(authorsField) {
		const authorsElement = document.querySelector(".dataset-authors");
		if (!authorsElement || !authorsField) return;

		try {
			const authors = JSON.parse(authorsField.value || "[]");
			const authorNames = this.formatAuthors(authors);
			// In creation mode, just show current authors (no original/changes logic)
			authorsElement.innerHTML = `<span class="current-value">${window.HTMLInjectionManager.escapeHtml(authorNames)}</span>`;
		} catch (e) {
			authorsElement.innerHTML =
				'<span class="current-value">Error parsing authors.</span>';
		}
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
}

// Make class available globally
window.DatasetCreationHandler = DatasetCreationHandler;
