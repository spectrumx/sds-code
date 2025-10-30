/**
 * Dataset Mode Manager
 * Manages the creation vs editing mode and delegates to appropriate handlers
 */
class DatasetModeManager {
	/**
	 * Initialize dataset mode manager
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.isEditMode = !!config.datasetUuid;
		this.config = config;

		// Define numbered steps
		this.step1 = 0;
		this.step2 = 1;
		this.step3 = 2;
		this.step4 = 3;

		// Initialize permissions manager
		if (window.PermissionsManager) {
			// In creation mode, user should have full permissions
			const permissionsConfig = {
				userPermissionLevel: config.userPermissionLevel,
				datasetUuid: config.datasetUuid,
				currentUserId: config.currentUserId,
				isOwner: config.isOwner,
				datasetPermissions: config.datasetPermissions,
			};

			// For creation mode, ensure user has full permissions
			if (!this.isEditMode) {
				permissionsConfig.isOwner = true;
				permissionsConfig.userPermissionLevel = window.PermissionLevels?.OWNER || 'owner';
				permissionsConfig.datasetPermissions = {
					canEditMetadata: true,
					canAddAssets: true,
					canRemoveAssets: true,
					canShare: true,
					canDownload: true,
					...config.datasetPermissions,
				};
			}

			this.permissions = new window.PermissionsManager(permissionsConfig);
		}

		// Initialize appropriate handler based on mode
		if (this.isEditMode && window.DatasetEditingHandler) {
			this.handler = new window.DatasetEditingHandler({
				...config,
				permissions: this.permissions,
			});
		} else if (!this.isEditMode && window.DatasetCreationHandler) {
			this.handler = new window.DatasetCreationHandler({
				...config,
				formId: "datasetForm",
			});
		}

		// Store reference globally for backward compatibility
		if (this.isEditMode) {
			window.datasetEditingHandler = this.handler;
			// Get search handlers from editing handler
			this.filesSearchHandler = this.handler.filesSearchHandler;
		} else {
			// Get search handlers from creation handler
			this.filesSearchHandler = this.handler.filesSearchHandler;
		}

		// Initialize original dataset data for change tracking
		this.originalDatasetData = this.captureOriginalDatasetData();

		// Initialize UI
		this.initializeUI();
	}

	/**
	 * Capture original dataset data for change tracking
	 */
	captureOriginalDatasetData() {
		const nameField = document.getElementById("id_name");
		const statusField = document.getElementById("id_status");
		const descriptionField = document.getElementById("id_description");
		const authorsField = document.getElementById("id_authors");

		const originalData = {};

		// In edit mode, try to get data from form fields first, then fall back to config
		if (this.isEditMode) {
			// Try to get from form fields (when user can edit metadata)
			if (nameField) {
				originalData.name = nameField.value || "Untitled Dataset";
			} else {
				// Fall back to readonly field or config data
				const readonlyNameField = document.querySelector(
					"input[readonly][value]",
				);
				originalData.name =
					readonlyNameField?.value ||
					this.config.existingDatasetName ||
					"Untitled Dataset";
			}

			if (statusField) {
				const selectedOption = statusField.options[statusField.selectedIndex];
				originalData.status = selectedOption ? selectedOption.text : "Unknown";
			} else {
				// Fall back to readonly field or config data
				const readonlyStatusField = document.querySelector("input[readonly]");
				originalData.status =
					readonlyStatusField?.value ||
					this.config.existingDatasetStatus ||
					"Unknown";
			}

			if (descriptionField) {
				originalData.description =
					descriptionField.value || "No description provided.";
			} else {
				// Fall back to readonly field or config data
				const readonlyDescField = document.querySelector("textarea[readonly]");
				originalData.description =
					readonlyDescField?.value ||
					this.config.existingDatasetDescription ||
					"No description provided.";
			}

			if (authorsField) {
				try {
					const authors = JSON.parse(authorsField.value || "[]");
					originalData.authors = authors;
				} catch (e) {
					originalData.authors = [];
				}
			} else {
				// Fall back to config data for authors
				originalData.authors = this.config.initialAuthors || [];
			}
		} else {
			// Creation mode - get from form fields
			originalData.name = nameField?.value || "Untitled Dataset";
			if (statusField) {
				const selectedOption = statusField.options[statusField.selectedIndex];
				originalData.status = selectedOption ? selectedOption.text : "Unknown";
			}
			originalData.description =
				descriptionField?.value || "No description provided.";

			if (authorsField) {
				try {
					const authors = JSON.parse(authorsField.value || "[]");
					originalData.authors = authors;
				} catch (e) {
					originalData.authors = [];
				}
			}
		}

		return originalData;
	}

	/**
	 * Initialize UI based on mode and permissions
	 */
	initializeUI() {
		// Update UI based on permissions
		this.updateUIForPermissions();

		// Initialize mode-specific UI elements
		if (this.isEditMode) {
			this.initializeEditModeUI();
		} else {
			this.initializeCreateModeUI();
		}
	}

	/**
	 * Initialize edit mode UI
	 */
	initializeEditModeUI() {
		// Remove btn-group-disabled class to allow tab navigation
		const stepTabsContainer = document.getElementById("stepTabs");
		if (stepTabsContainer) {
			stepTabsContainer.classList.remove("btn-group-disabled");
		}

		// Initialize step navigation for edit mode
		this.initializeStepNavigation();

		// Initialize review display
		this.initializeReviewDisplay();

		// Load file tree for files step
		this.loadFileTree();

		// Set up form field change listeners for real-time review updates
		this.setupFormChangeListeners();

		// Set up author management listeners
		this.setupAuthorManagementListeners();

		// Update submit button text for edit mode
		const submitBtn = document.getElementById("submitForm");
		if (!submitBtn) return;

		submitBtn.textContent = "Update Dataset";
	}

	/**
	 * Initialize create mode UI
	 */
	initializeCreateModeUI() {
		// Initialize step navigation for create mode
		this.initializeStepNavigation();

		// Hide submit button initially unless on last step
		const submitBtn = document.getElementById("submitForm");
		if (
			submitBtn &&
			this.handler.currentStep !== this.handler.steps.length - 1
		) {
			window.DOMUtils.hide(submitBtn, "display-inline-block");
		}
	}

	/**
	 * Initialize step navigation for both create and edit modes
	 */
	initializeStepNavigation() {
		// Get step navigation elements
		this.prevBtn = document.getElementById("prevStep");
		this.nextBtn = document.getElementById("nextStep");
		this.stepTabs = document.querySelectorAll("#stepTabs .btn");
		this.submitBtn = document.getElementById("submitForm");

		// Current step (0-based index)
		this.currentStep = this.step1;

		// Step configuration
		this.steps = [
			{ id: "step1", name: "Dataset Info" },
			{ id: "step2", name: "Select Captures" },
			{ id: "step3", name: "Select Artifact Files" },
			{
				id: "step4",
				name: this.isEditMode ? "Review and Update" : "Review and Create",
			},
		];

		// Set up event listeners
		this.setupStepNavigationListeners();

		// Initialize step display
		this.updateStepDisplay();
	}

	/**
	 * Set up step navigation event listeners
	 */
	setupStepNavigationListeners() {
		// Previous button
		if (this.prevBtn) {
			this.prevBtn.addEventListener("click", (e) => {
				e.preventDefault();
				this.navigateToStep(this.currentStep - 1);
			});
		}

		// Next button
		if (this.nextBtn) {
			this.nextBtn.addEventListener("click", (e) => {
				e.preventDefault();
				this.navigateToStep(this.currentStep + 1);
			});
		}

		// Step tabs
		for (const [index, tab] of this.stepTabs.entries()) {
			tab.addEventListener("click", () => {
				this.navigateToStep(index);
			});
		}

		// Submit button
		if (this.submitBtn) {
			this.submitBtn.addEventListener("click", (e) => {
				e.preventDefault();
				this.handleSubmit(e);
			});
		}
	}

	/**
	 * Navigate to a specific step
	 * @param {number} stepIndex - Step index to navigate to
	 */
	navigateToStep(stepIndex) {
		// Validate step index
		if (stepIndex < 0 || stepIndex >= this.steps.length) {
			return;
		}

		// Update current step
		this.currentStep = stepIndex;

		// Update step display
		this.updateStepDisplay();

		// Load file tree when accessing files step
		if (stepIndex === this.step3 && this.filesSearchHandler) {
			this.loadFileTree();
		}

		// Update review display when accessing review step (step 4 = index 3)
		if (stepIndex === this.step4) {
			this.updateReviewDatasetDisplay();
		}

		// Delegate to handler if it has navigation methods
		if (this.handler && typeof this.handler.navigateToStep === "function") {
			this.handler.navigateToStep(stepIndex);
		}
	}

	/**
	 * Update step display
	 */
	updateStepDisplay() {
		// Update step tabs
		for (const [index, tab] of this.stepTabs.entries()) {
			if (index === this.currentStep) {
				tab.classList.remove("btn-outline-primary", "inactive-tab");
				tab.classList.add("btn-primary", "active-tab");
			} else {
				tab.classList.remove("btn-primary", "active-tab");
				tab.classList.add("btn-outline-primary", "inactive-tab");
			}
		}

		// Update step content
		const stepPanes = document.querySelectorAll(
			"#stepTabsContentInner .tab-pane",
		);
		for (const [index, pane] of stepPanes.entries()) {
			if (index === this.currentStep) {
				pane.classList.add("show", "active");
			} else {
				pane.classList.remove("show", "active");
			}
		}

		// Update navigation buttons
		if (this.prevBtn) {
			if (this.currentStep === this.step1) {
				window.DOMUtils.hide(this.prevBtn, "display-inline-block");
			} else {
				window.DOMUtils.show(this.prevBtn, "display-inline-block");
				this.prevBtn.disabled = false;
			}
		}

		if (this.nextBtn) {
			if (this.isEditMode) {
				// In edit mode, always show next button (no validation needed)
				if (this.currentStep < this.steps.length - 1) {
					window.DOMUtils.show(this.nextBtn, "display-inline-block");
				} else {
					window.DOMUtils.hide(this.nextBtn, "display-inline-block");
				}
			} else {
				// In create mode, validate current step before allowing next
				if (this.currentStep < this.steps.length - 1) {
					window.DOMUtils.show(this.nextBtn, "display-inline-block");
				} else {
					window.DOMUtils.hide(this.nextBtn, "display-inline-block");
				}
			}
		}

		// Update submit button
		if (this.submitBtn) {
			if (this.currentStep === this.steps.length - 1) {
				window.DOMUtils.show(this.submitBtn, "display-inline-block");
			} else {
				window.DOMUtils.hide(this.submitBtn, "display-inline-block");
			}
		}
	}

	/**
	 * Initialize review display
	 */
	initializeReviewDisplay() {
		// Make updateReviewDatasetDisplay available globally
		window.updateReviewDatasetDisplay = () => {
			this.updateReviewDatasetDisplay();
		};

		// Don't call initial update here - wait until user navigates to review step
	}

	/**
	 * Update review dataset display
	 */
	updateReviewDatasetDisplay() {
		if (this.isEditMode && this.handler) {
			// Update pending dataset information
			this.updateDatasetInfo();

			// Update pending changes
			this.updatePendingChanges();
		} else {
			// Creation mode: update both dataset info and selected assets
			this.updateDatasetInfo();
			this.updateSelectedAssets();
		}
	}

	/**
	 * Update dataset information in review
	 */
	updateDatasetInfo() {
		// Get form data
		const nameField = document.getElementById("id_name");
		const statusField = document.getElementById("id_status");
		const descriptionField = document.getElementById("id_description");
		const authorsField = document.getElementById("id_authors");

		// Update dataset name
		this.updateDatasetName(nameField);

		// Update status
		this.updateDatasetStatus(statusField);

		// Update description
		this.updateDatasetDescription(descriptionField);

		// Update authors
		this.updateDatasetAuthors(authorsField);
	}

	/**
	 * Update dataset name with pending changes
	 */
	async updateDatasetName(nameField) {
		const nameElement = document.querySelector(".dataset-name");
		if (!nameElement) return;

		if (!nameField) {
			if (this.isEditMode) {
				nameElement.textContent =
					this.originalDatasetData?.name || "Untitled Dataset";
			}
			return;
		}

		const currentValue = nameField.value || "Untitled Dataset";
		const originalValue = this.originalDatasetData?.name || currentValue;

		if (this.isEditMode) {
			// Always show original value
			const currentSpan = document.createElement("span");
			currentSpan.className = "current-value";
			currentSpan.textContent = originalValue;
			nameElement.innerHTML = "";
			nameElement.appendChild(currentSpan);

			// Add pending changes if different from original
			if (currentValue !== originalValue) {
				try {
					const response = await window.APIClient.post("/users/render-html/", {
						template: "users/components/change_list.html",
						context: {
							changes: [
								{
									type: "change",
									parts: [
										{ text: 'Change Name: "' },
										{ text: originalValue },
										{ text: '" → ' },
										{ text: `"${currentValue}"`, css_class: "text-warning" },
									],
								},
							],
						},
					}, null, true); // true = send as JSON
					if (response.html) {
						nameElement.insertAdjacentHTML("beforeend", response.html);
					}
				} catch (error) {
					console.error("Error rendering name change:", error);
				}
			}
		} else {
			nameElement.textContent = currentValue;
		}
	}

	/**
	 * Update dataset status with pending changes
	 */
	async updateDatasetStatus(statusField) {
		const statusElement = document.querySelector(".dataset-status");
		if (!statusElement) return;

		if (!statusField) {
			if (this.isEditMode) {
				statusElement.textContent =
					this.originalDatasetData?.status || "Unknown";
			}
			return;
		}

		const selectedOption = statusField.options[statusField.selectedIndex];
		const currentValue = selectedOption ? selectedOption.text : "Unknown";
		const originalValue = this.originalDatasetData?.status || currentValue;

		if (this.isEditMode) {
			// Always show original value
			const currentSpan = document.createElement("span");
			currentSpan.className = "current-value";
			currentSpan.textContent = originalValue;
			statusElement.innerHTML = "";
			statusElement.appendChild(currentSpan);

			// Add pending changes if different from original
			if (currentValue !== originalValue) {
				try {
					const response = await window.APIClient.post("/users/render-html/", {
						template: "users/components/change_list.html",
						context: {
							changes: [
								{
									type: "change",
									parts: [
										{ text: 'Change Status: "' },
										{ text: originalValue },
										{ text: '" → ' },
										{ text: `"${currentValue}"`, css_class: "text-warning" },
									],
								},
							],
						},
					}, null, true); // true = send as JSON
					if (response.html) {
						statusElement.insertAdjacentHTML("beforeend", response.html);
					}
				} catch (error) {
					console.error("Error rendering status change:", error);
				}
			}
		} else {
			statusElement.textContent = currentValue;
		}
	}

	/**
	 * Update dataset description with pending changes
	 */
	async updateDatasetDescription(descriptionField) {
		const descriptionElement = document.querySelector(".dataset-description");
		if (!descriptionElement) return;

		if (!descriptionField) {
			if (this.isEditMode) {
				descriptionElement.textContent =
					this.originalDatasetData?.description || "No description provided.";
			}
			return;
		}

		const currentValue = descriptionField.value || "No description provided.";
		const originalValue = this.originalDatasetData?.description || currentValue;

		if (this.isEditMode) {
			// Always show original value
			const currentSpan = document.createElement("span");
			currentSpan.className = "current-value";
			currentSpan.textContent = originalValue;
			descriptionElement.innerHTML = "";
			descriptionElement.appendChild(currentSpan);

			// Add pending changes if different from original
			if (currentValue !== originalValue) {
				try {
					const response = await window.APIClient.post("/users/render-html/", {
						template: "users/components/change_list.html",
						context: {
							changes: [
								{
									type: "change",
									parts: [
										{ text: 'Change Description: "' },
										{ text: originalValue },
										{ text: '" → ' },
										{ text: `"${currentValue}"`, css_class: "text-warning" },
									],
								},
							],
						},
					}, null, true); // true = send as JSON
					if (response.html) {
						descriptionElement.insertAdjacentHTML("beforeend", response.html);
					}
				} catch (error) {
					console.error("Error rendering description change:", error);
				}
			}
		} else {
			descriptionElement.textContent = currentValue;
		}
	}

	/**
	 * Update dataset authors with pending changes
	 */
	updateDatasetAuthors(authorsField) {
		// Delegate to the appropriate handler's method
		if (
			window.updateDatasetAuthors &&
			typeof window.updateDatasetAuthors === "function"
		) {
			window.updateDatasetAuthors(authorsField);
		}
	}

	/**
	 * Set up author management listeners
	 */
	setupAuthorManagementListeners() {
		// Listen for author input changes
		document.addEventListener("input", (e) => {
			if (
				e.target.classList.contains("author-name-input") ||
				e.target.classList.contains("author-orcid-input")
			) {
				// Update review display when author fields change
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
			}
		});

		// Listen for author removal
		document.addEventListener("click", (e) => {
			if (e.target.closest(".remove-author")) {
				// Update review display when author is removed
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
			}
		});

		// Listen for author addition
		document.addEventListener("click", (e) => {
			if (
				e.target.id === "add-author-btn" ||
				e.target.closest("#add-author-btn")
			) {
				// Update review display when author is added
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
			}
		});
	}

	/**
	 * Update pending changes for edit mode
	 */
	async updatePendingChanges() {
		if (!this.handler || typeof this.handler.getPendingChanges !== "function") {
			return;
		}

		const pendingChanges = this.handler.getPendingChanges();
		const pendingTable = document.querySelector(".pending-changes-table tbody");
		const pendingCount = document.querySelector(".pending-changes-count");

		if (!pendingTable) return;

		// Normalize for generic table_rows template
		const rows = [];

		// Add capture changes
		for (const [id, change] of pendingChanges.captures) {
			rows.push({
				cells: [
					{ value: "Capture" },
					{
						html: `<span class="badge ${change.action === "add" ? "bg-success" : "bg-danger"}">
							${change.action === "add" ? "Add" : "Remove"}
						</span>`,
					},
					{ value: change.data.type || "Unknown" },
					{ value: change.data.directory || "" },
				],
				actions: [
					{
						label: "Cancel",
						css_class: "btn-outline-secondary",
						extra_class: "cancel-change",
						data_attrs: {
							capture_id: id,
							change_type: "capture",
						},
					},
				],
			});
		}

		// Add file changes
		for (const [id, change] of pendingChanges.files) {
			rows.push({
				cells: [
					{ value: "File" },
					{
						html: `<span class="badge ${change.action === "add" ? "bg-success" : "bg-danger"}">
							${change.action === "add" ? "Add" : "Remove"}
						</span>`,
					},
					{ value: change.data.name || "Unknown" },
					{ value: change.data.path || "" },
				],
				actions: [
					{
						label: "Cancel",
						css_class: "btn-outline-secondary",
						extra_class: "cancel-change",
						data_attrs: {
							file_id: id,
							change_type: "file",
						},
					},
				],
			});
		}

		// Render using DOMUtils
		const success = await window.DOMUtils.renderTable(pendingTable, rows, {
			empty_message: "No pending asset changes",
			empty_colspan: 5,
		});

		if (!success) {
			await window.DOMUtils.renderError(pendingTable, "Error loading changes", {
				format: "table",
				colspan: 5,
			});
		}

		// Update count
		if (pendingCount) {
			pendingCount.textContent = `${rows.length} change${rows.length !== 1 ? "s" : ""}`;
		}
	}

	/**
	 * Load file tree for files step
	 */
	loadFileTree() {
		// Load file tree when files step is accessed
		if (
			this.filesSearchHandler &&
			typeof this.filesSearchHandler.loadFileTree === "function"
		) {
			this.filesSearchHandler.loadFileTree();
		}
	}

	/**
	 * Set up form field change listeners for real-time review updates
	 */
	setupFormChangeListeners() {
		// Listen for changes to dataset info fields
		const formFields = ["id_name", "id_status", "id_description", "id_authors"];

		for (const fieldId of formFields) {
			const field = document.getElementById(fieldId);
			if (field) {
				// Listen for input changes
				field.addEventListener("input", () => {
					this.updateReviewDatasetDisplay();
				});

				// Listen for change events (for select fields)
				field.addEventListener("change", () => {
					this.updateReviewDatasetDisplay();
				});
			}
		}
	}

	/**
	 * Update selected assets for create mode
	 */
	updateSelectedAssets() {
		// Delegate to the creation handler's methods if available
		if (
			this.handler &&
			typeof this.handler.updateSelectedCapturesTable === "function"
		) {
			this.handler.updateSelectedCapturesTable();
		} else {
			// Fallback for empty state
			const capturesTable = document.querySelector(".captures-table tbody");
			if (capturesTable) {
				this.renderEmptyTableRow(capturesTable, 6, "No captures selected");
			}
		}

		if (
			this.handler &&
			typeof this.handler.updateSelectedFilesTable === "function"
		) {
			this.handler.updateSelectedFilesTable();
		} else {
			// Fallback for empty state
			const filesTable = document.querySelector(".files-table tbody");
			if (filesTable) {
				this.renderEmptyTableRow(filesTable, 5, "No files selected");
			}
		}

		// Update counts
		const capturesCount = document.querySelector(".captures-count");
		const filesCount = document.querySelector(".files-count");

		if (capturesCount) {
			const count = this.handler?.selectedCaptures
				? this.handler.selectedCaptures.size
				: 0;
			capturesCount.textContent = `${count} selected`;
		}

		if (!filesCount) return;

		const count = this.handler?.selectedFiles
			? this.handler.selectedFiles.size
			: 0;
		filesCount.textContent = `${count} selected`;
	}

	/**
	 * Render empty table row asynchronously
	 */
	async renderEmptyTableRow(tableElement, colspan, message) {
		try {
			const response = await window.APIClient.post("/users/render-html/", {
				template: "users/components/empty_table_row.html",
				context: {
					colspan: colspan,
					message: message,
				},
			}, null, true); // true = send as JSON

			if (response.html) {
				tableElement.innerHTML = response.html;
			}
		} catch (error) {
			console.error("Error rendering empty table row:", error);
			// Fallback
			tableElement.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-muted">${message}</td></tr>`;
		}
	}

	/**
	 * Update UI based on user permissions
	 */
	updateUIForPermissions() {
		const permissionSummary = this.permissions.getPermissionSummary();

		// Update permission display if element exists
		const permissionDisplay = document.getElementById(
			"user-permission-display",
		);
		if (permissionDisplay) {
			this.renderPermissionDisplay(permissionSummary, permissionDisplay);
		}

		// Disable/hide elements based on permissions
		this.updateFormElementsForPermissions();
		this.updateActionButtonsForPermissions();
	}

	/**
	 * Render permission display asynchronously
	 */
	async renderPermissionDisplay(permissionSummary, permissionDisplay) {
		try {
			const response = await window.APIClient.post("/users/render-html/", {
				template: "users/components/permission_display.html",
				context: {
					permission_summary: permissionSummary,
				},
			}, null, true); // true = send as JSON

			if (response.html) {
				permissionDisplay.innerHTML = response.html;
			}
		} catch (error) {
			console.error("Error rendering permission display:", error);
			// Fallback
			permissionDisplay.innerHTML = `
				<div class="d-flex align-items-center">
					<i class="bi ${permissionSummary.icon} me-2"></i>
					<span class="badge ${permissionSummary.badgeClass} me-2">
						${permissionSummary.displayName}
					</span>
					<small class="text-muted">${permissionSummary.description}</small>
				</div>
			`;
		}
	}

	/**
	 * Update form elements based on permissions
	 */
	updateFormElementsForPermissions() {
		// Dataset metadata fields
		const nameField = document.getElementById("id_name");
		const authorsField = document.getElementById("id_authors");
		const statusField = document.getElementById("id_status");
		const descriptionField = document.getElementById("id_description");

		if (!this.permissions.canEditMetadata()) {
			const fields = [nameField, authorsField, statusField, descriptionField];
			for (const field of fields) {
				if (field) {
					field.disabled = true;
					field.classList.add("form-control-plaintext");
				}
			}
		}

		// Asset selection areas
		const capturesSection = document.getElementById("captures-section");
		const filesSection = document.getElementById("files-section");

		if (!this.permissions.canAddAssets()) {
			if (capturesSection) {
				capturesSection.style.opacity = "0.5";
				capturesSection.style.pointerEvents = "none";
			}
			if (filesSection) {
				filesSection.style.opacity = "0.5";
				filesSection.style.pointerEvents = "none";
			}
		}
	}

	/**
	 * Update action buttons based on permissions
	 */
	updateActionButtonsForPermissions() {
		// Share button
		const shareButton = document.getElementById("share-dataset-btn");
		if (shareButton && !this.permissions.canShare()) {
			window.DOMUtils.hide(shareButton, "display-inline-block");
		}

		// Download button
		const downloadButton = document.getElementById("download-dataset-btn");
		if (!downloadButton) return;

		if (!this.permissions.canDownload()) {
			window.DOMUtils.hide(downloadButton, "display-inline-block");
		}
	}

	/**
	 * Get current handler
	 * @returns {Object} Current handler (creation or editing)
	 */
	getHandler() {
		return this.handler;
	}

	/**
	 * Get permissions manager
	 * @returns {PermissionsManager} Permissions manager instance
	 */
	getPermissions() {
		return this.permissions;
	}

	/**
	 * Check if in edit mode
	 * @returns {boolean} Whether in edit mode
	 */
	isInEditMode() {
		return this.isEditMode;
	}

	/**
	 * Get dataset UUID
	 * @returns {string|null} Dataset UUID
	 */
	getDatasetUuid() {
		return this.config.datasetUuid;
	}

	/**
	 * Update permissions (for dynamic permission changes)
	 * @param {Object} newPermissions - New permissions object
	 */
	updatePermissions(newPermissions) {
		this.permissions.updateDatasetPermissions(newPermissions);
		this.updateUIForPermissions();
	}

	/**
	 * Handle form submission (delegates to appropriate handler)
	 * @param {Event} e - Submit event
	 */
	async handleSubmit(e) {
		if (this.isEditMode) {
			// For edit mode, we need to handle the submission differently
			// This would typically be handled by the form's submit handler
			// which would collect pending changes from the editing handler
			return this.handler.handleSubmit ? this.handler.handleSubmit(e) : null;
		}
		// For create mode, delegate to creation handler
		return this.handler.handleSubmit(e);
	}

	/**
	 * Get pending changes (edit mode only)
	 * @returns {Object|null} Pending changes or null if not in edit mode
	 */
	getPendingChanges() {
		if (this.isEditMode && this.handler.getPendingChanges) {
			return this.handler.getPendingChanges();
		}
		return null;
	}

	/**
	 * Check if there are pending changes (edit mode only)
	 * @returns {boolean} Whether there are pending changes
	 */
	hasPendingChanges() {
		if (this.isEditMode && this.handler.hasChanges) {
			return this.handler.hasChanges();
		}
		return false;
	}

	/**
	 * Cleanup resources
	 */
	cleanup() {
		// Remove global reference
		if (window.datasetEditingHandler === this.handler) {
			window.datasetEditingHandler = undefined;
		}

		// Cleanup handler if it has cleanup method
		if (this.handler.cleanup) {
			this.handler.cleanup();
		}
	}
}

// Make class available globally
window.DatasetModeManager = DatasetModeManager;

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { DatasetModeManager };
}
