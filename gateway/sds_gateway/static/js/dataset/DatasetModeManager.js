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
		this.step5 = 4;

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
				permissionsConfig.userPermissionLevel = window.PermissionLevels.OWNER;
				permissionsConfig.datasetPermissions = {
					canEditMetadata: true,
					canAddAssets: true,
					canRemoveAnyAssets: true,
					canRemoveOwnAssets: true,
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
		// Update UI based on permissions (this also handles existing final status)
		this.updateUIForPermissions();

		// Initialize mode-specific UI elements
		if (this.isEditMode) {
			this.initializeEditModeUI();
		} else {
			this.initializeCreateModeUI();
		}

		// Update visibility toggle if this is an existing final dataset (not current session)
		if (this.isExistingFinalDataset()) {
			this.updateVisibilityToggleForFinal();
		}

		// Initialize publishing info handlers
		this.initializePublishingInfo();

		// Update title and card styling for already published/public datasets
		this.updateEditorTitleAndStyling();
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

		// Ensure submit button is hidden unless on final step
		const submitBtn = document.getElementById("submitForm");
		if (submitBtn) {
			// Hide initially (will be shown if on last step by updateStepDisplay)
			if (this.currentStep !== this.steps.length - 1) {
				window.DOMUtils.hide(submitBtn, "display-inline-block");
			}
		}
	}

	/**
	 * Initialize create mode UI
	 */
	initializeCreateModeUI() {
		// Initialize step navigation for create mode
		this.initializeStepNavigation();

		// Ensure submit button is hidden unless on final step
		const submitBtn = document.getElementById("submitForm");
		if (submitBtn) {
			// Hide initially (will be shown if on last step by updateStepDisplay)
			if (this.currentStep !== this.steps.length - 1) {
				window.DOMUtils.hide(submitBtn, "display-inline-block");
			}
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
			{ id: "step4", name: "Publishing Info" },
			{
				id: "step5",
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

		// Update review display when accessing review step (step 5 = index 4)
		if (stepIndex === this.step5) {
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

		// Update submit button - only show on final review step (step 5)
		if (this.submitBtn) {
			if (this.currentStep === this.step5) {
				window.DOMUtils.show(this.submitBtn, "display-inline-block");
				// Update button text and styling based on publishing status
				this.updateSubmitButton();
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
		
		// Update title and styling in case publishing status changed
		this.updateEditorTitleAndStyling();
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

		// Update publishing information
		this.updatePublishingInfo(statusField);

		// Update visibility (moved to publishing info panel)
		this.updateDatasetVisibility();

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
					const response = await window.APIClient.post(
						"/users/render-html/",
						{
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
						},
						null,
						true,
					); // true = send as JSON
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
	 * Update publishing information in review panel as alert banners
	 * Only shows warnings when dataset is being SET to final/public in current session
	 * Not when dataset is already final/public
	 */
	updatePublishingInfo(statusField) {
		const alertsContainer = document.getElementById("publishing-alerts-container");
		if (!alertsContainer) return;

		const publishToggle = document.getElementById("publish-dataset-toggle");
		const isPublishing = publishToggle ? publishToggle.checked : false;
		const statusValue = statusField ? statusField.value : "draft";
		const isPublic =
			document.querySelector('input[name="is_public"]:checked')?.value ===
			"true";

		// Check if dataset is already final/public (from database, not current session)
		const isExistingFinal = this.isExistingFinalDataset();
		const isExistingPublic = this.isDatasetPublic() && isExistingFinal;

		// Clear existing alerts
		alertsContainer.innerHTML = "";

		// Only show warnings if publishing in CURRENT session (not if already final/public)
		if (!isExistingFinal && (isPublishing || statusValue === "final")) {
			// Publishing alert - only show if being set to final in current session
			const publishingAlert = document.createElement("div");
			publishingAlert.className = "alert alert-warning mb-3";
			publishingAlert.innerHTML =
				'<div class="d-flex align-items-center">' +
				'<i class="bi bi-exclamation-triangle-fill me-3 fs-5"></i>' +
				'<div class="flex-grow-1">' +
				'<strong>This dataset will be published.</strong> ' +
				'The dataset status will be set to Final. This action is irreversible.' +
				"</div>" +
				"</div>";
			alertsContainer.appendChild(publishingAlert);

			// Public visibility alert (if making public in current session)
			if (!isExistingPublic && isPublic) {
				const publicAlert = document.createElement("div");
				publicAlert.className = "alert alert-danger mb-0";
				publicAlert.innerHTML =
					'<div class="d-flex align-items-center">' +
					'<i class="bi bi-exclamation-triangle-fill me-3 fs-5"></i>' +
					'<div class="flex-grow-1">' +
					'<strong>This dataset will be publicly viewable.</strong> ' +
					'Making this dataset public is irreversible and will make it viewable to anyone with access to the site.' +
					"</div>" +
					"</div>";
				alertsContainer.appendChild(publicAlert);
			}
		} else if (!isExistingFinal) {
			// Not publishing - optional info alert (only if not already final)
			const draftAlert = document.createElement("div");
			draftAlert.className = "alert alert-info mb-0";
			draftAlert.innerHTML =
				'<div class="d-flex align-items-center">' +
				'<i class="bi bi-info-circle-fill me-3 fs-5"></i>' +
				'<div class="flex-grow-1">' +
				'This dataset will remain in <strong>Draft</strong> status and will not be published.' +
				"</div>" +
				"</div>";
			alertsContainer.appendChild(draftAlert);
		}
		// If already final/public, don't show any alerts (indicators will be in title instead)
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
					const response = await window.APIClient.post(
						"/users/render-html/",
						{
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
						},
						null,
						true,
					); // true = send as JSON
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
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template: "users/components/empty_table_row.html",
					context: {
						colspan: colspan,
						message: message,
					},
				},
				null,
				true,
			); // true = send as JSON

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
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template: "users/components/permission_display.html",
					context: {
						permission_summary: permissionSummary,
					},
				},
				null,
				true,
			); // true = send as JSON

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
	 * Update form elements based on permissions and dataset status
	 * Note: View-only restrictions only apply when loading an existing final-status dataset,
	 * not during the current editing session
	 */
	updateFormElementsForPermissions() {
		// Dataset metadata fields
		const nameField = document.getElementById("id_name");
		const authorsField = document.getElementById("id_authors");
		const statusField = document.getElementById("id_status");
		const descriptionField = document.getElementById("id_description");

		// Check if this is an existing final-status dataset (from database, not current session)
		const isExistingFinal = this.isExistingFinalDataset();

		if (!this.permissions.canEditMetadata()) {
			const fields = [nameField, authorsField, statusField, descriptionField];
			for (const field of fields) {
				if (field) {
					field.disabled = true;
					field.classList.add("form-control-plaintext");
				}
			}
		} else if (isExistingFinal) {
			// Only apply view-only restrictions for existing final datasets (after submission)
			// NOT during current editing session
			const fields = [nameField, authorsField, statusField, descriptionField];
			for (const field of fields) {
				if (field) {
					field.disabled = true;
					field.classList.add("form-control-plaintext");
					field.setAttribute("readonly", "readonly");
				}
			}
			
			// Disable author add button
			const addAuthorBtn = document.getElementById("add-author-btn");
			if (addAuthorBtn) {
				addAuthorBtn.disabled = true;
				addAuthorBtn.classList.add("disabled");
			}

			// Disable all existing author inputs
			const authorsList = document.querySelector(".authors-list");
			if (authorsList) {
				const authorInputs = authorsList.querySelectorAll(
					".author-name-input, .author-orcid-input",
				);
				authorInputs.forEach((input) => {
					input.disabled = true;
					input.setAttribute("readonly", "readonly");
					input.classList.add("form-control-plaintext");
				});
				// Also disable remove buttons for authors
				const removeButtons = authorsList.querySelectorAll(
					".remove-author, .cancel-remove-author",
				);
				removeButtons.forEach((button) => {
					button.disabled = true;
					button.classList.add("disabled-element");
				});
			}

			// Disable publish toggle (can't unpublish)
			const publishToggle = document.getElementById("publish-dataset-toggle");
			if (publishToggle) {
				publishToggle.disabled = true;
			}

			// Handle visibility toggle based on current public/private status
			this.updateVisibilityToggleForFinal();
		}

		// Asset selection areas - disable if existing final OR if no permission
		const capturesSection = document.getElementById("captures-section");
		const filesSection = document.getElementById("files-section");
		const shouldDisableAssets = isExistingFinal || !this.permissions.canAddAssets();

		if (shouldDisableAssets) {
			// Disable captures section
			if (capturesSection) {
				capturesSection.classList.add("disabled-element");
				// Disable all interactive elements within
				const capturesInputs = capturesSection.querySelectorAll(
					"input, button, select, textarea, a",
				);
				capturesInputs.forEach((el) => {
					el.disabled = true;
					el.classList.add("disable-events");
				});
			}
			// Disable files section
			if (filesSection) {
				filesSection.classList.add("disabled-element");
				// Disable all interactive elements within
				const filesInputs = filesSection.querySelectorAll(
					"input, button, select, textarea, a",
				);
				filesInputs.forEach((el) => {
					el.disabled = true;
					el.classList.add("disable-events");
				});
			}
		}
	}

	/**
	 * Check if dataset is in final status
	 * This checks both the form field and the config (for existing datasets)
	 */
	isDatasetFinal() {
		const statusField = document.getElementById("id_status");
		if (statusField) {
			return statusField.value === "final";
		}
		// Check from config if available (for existing datasets loaded in editor after publishing)
		if (this.config.existingDatasetStatus) {
			return this.config.existingDatasetStatus === "final";
		}
		return false;
	}

	/**
	 * Check if this is an existing final-status dataset (loaded from database)
	 * This is different from isDatasetFinal() which also checks current form state
	 * This only returns true if the dataset was already final when loaded, not if user is publishing now
	 */
	isExistingFinalDataset() {
		// Only check config - this represents the dataset state from database
		// Don't check form field as that represents current editing session
		if (this.config.existingDatasetStatus) {
			return this.config.existingDatasetStatus === "final";
		}
		return false;
	}

	/**
	 * Check if dataset is currently public
	 * This checks both the form field and the config (for existing datasets)
	 */
	isDatasetPublic() {
		const publicOption = document.getElementById("public-option");
		if (publicOption) {
			return publicOption.checked;
		}
		// Check from config if available (for existing datasets loaded in editor)
		if (this.config.existingDatasetIsPublic !== undefined) {
			return this.config.existingDatasetIsPublic === true;
		}
		return false;
	}

	/**
	 * Update visibility toggle for final status datasets
	 * If private, allow changing to public only
	 * If public, make it view-only
	 */
	updateVisibilityToggleForFinal() {
		const publicOption = document.getElementById("public-option");
		const privateOption = document.getElementById("private-option");
		const visibilitySection = document.getElementById("visibility-toggle-section");

		// Only apply if visibility section is visible (dataset is published)
		if (!visibilitySection || visibilitySection.classList.contains("d-none")) {
			return;
		}

		// Check current public status from radio button or config
		let isCurrentlyPublic = false;
		if (publicOption && publicOption.checked) {
			isCurrentlyPublic = true;
		} else if (this.isDatasetPublic()) {
			isCurrentlyPublic = true;
		}

		if (isCurrentlyPublic) {
			// If already public, disable both options (can't change back to private)
			if (publicOption) {
				publicOption.disabled = true;
			}
			if (privateOption) {
				privateOption.disabled = true;
			}
		} else {
			// If private, disable private option (can only change to public)
			if (privateOption) {
				privateOption.disabled = true;
			}
			// Public option should remain enabled to allow changing to public
		}
	}

	/**
	 * Update editor title and card styling for already published/public datasets
	 */
	updateEditorTitleAndStyling() {
		const cardHeader = document.querySelector("#group-captures-card .card-header");
		const titleElement = cardHeader?.querySelector("h5");
		
		if (!cardHeader || !titleElement) return;

		const isExistingFinal = this.isExistingFinalDataset();
		// Check if dataset is already public from config (existing state, not current form state)
		const isExistingPublic = 
			(this.config && this.config.existingDatasetIsPublic === true) && isExistingFinal;

		// Remove any existing indicator classes
		cardHeader.classList.remove("bg-success", "bg-danger", "bg-warning", "bg-light");
		titleElement.classList.remove("text-white", "text-dark");

		// Get base title text (remove any existing badges)
		let baseTitle = titleElement.textContent.trim();
		// Remove any existing badge text patterns
		baseTitle = baseTitle.replace(/\s*Published\s*/gi, "").replace(/\s*Public\s*/gi, "").trim();

		if (isExistingFinal && isExistingPublic) {
			// Public and published - red/danger styling
			cardHeader.classList.add("bg-danger");
			titleElement.classList.add("text-white");
			
			// Add indicators to title
			titleElement.innerHTML = `${baseTitle} <span class="badge bg-light text-danger ms-2">Published</span> <span class="badge bg-light text-danger ms-1">Public</span>`;
		} else if (isExistingFinal) {
			// Published but private - success/green styling
			cardHeader.classList.add("bg-success");
			titleElement.classList.add("text-white");
			
			// Add indicator to title
			titleElement.innerHTML = `${baseTitle} <span class="badge bg-light text-success ms-2">Published</span>`;
		} else {
			// Not published - default styling
			cardHeader.classList.add("bg-light");
			titleElement.classList.add("text-dark");
			// Restore original title without badges
			titleElement.textContent = baseTitle;
		}
	}

	/**
	 * Initialize publishing info handlers
	 */
	initializePublishingInfo() {
		const publishToggle = document.getElementById("publish-dataset-toggle");
		const statusField = document.getElementById("id_status");
		const visibilitySection = document.getElementById("visibility-toggle-section");
		const publicOption = document.getElementById("public-option");
		const privateOption = document.getElementById("private-option");
		const publicWarning = document.getElementById("public-warning-message");
		const statusBadge = document.getElementById("current-status-badge");

		if (!publishToggle || !statusField) return;

		// Initialize status based on existing dataset or default to draft
		const currentStatus = statusField.value || "draft";

		// Check if this is an existing final dataset from database (not current session)
		const existingStatus =
			statusField.getAttribute("data-initial-status") ||
			(this.config && this.config.existingDatasetStatus) ||
			null;
		const isExistingFinal = existingStatus === "final";
		const isFinalInCurrentSession = currentStatus === "final";

		// Only apply restrictions if this is an existing final dataset (from database)
		// NOT if user is just publishing in current session
		if (isExistingFinal) {
			// Hide publishing question and warning for already published datasets
			const publishQuestion = publishToggle.closest(".mb-4");
			if (publishQuestion) {
				const publishLabel = publishQuestion.querySelector("#publish-question");
				const publishWarning = publishQuestion.querySelector("#publish-warning");
				const publishSwitch = publishQuestion.querySelector("#publish-toggle");
				const currentStatusBadge = publishQuestion.querySelector("#current-status-badge");

				if (publishLabel) window.DOMUtils.hide(publishLabel, "display-inline-block");
				if (publishWarning) window.DOMUtils.hide(publishWarning, "display-inline-block");
				if (publishSwitch) window.DOMUtils.hide(publishSwitch, "display-inline-block");
				if (currentStatusBadge) window.DOMUtils.hide(currentStatusBadge, "display-inline-block");
			}

			publishToggle.checked = true;
			// Disable publish toggle (can't unpublish existing final dataset)
			publishToggle.disabled = true;

			// Show visibility section if published
			if (visibilitySection) {
				visibilitySection.classList.remove("d-none");
			}
			this.updateStatusField("final");

			// Check if dataset is currently public or private (from database)
			const existingIsPublic =
				(this.config && this.config.existingDatasetIsPublic) || false;
			const isCurrentlyPublic =
				(publicOption && publicOption.checked) || existingIsPublic;

			if (isCurrentlyPublic) {
				// Already public - disable both options (view-only)
				if (publicOption) publicOption.disabled = true;
				if (privateOption) privateOption.disabled = true;
			} else {
				// Private - allow changing to public only
				if (privateOption) privateOption.disabled = true;
				// Public option remains enabled
			}
		} else if (isFinalInCurrentSession) {
			// User is publishing in current session - allow editing
			publishToggle.checked = true;
			// Don't disable publish toggle during current session
			if (visibilitySection) {
				visibilitySection.classList.remove("d-none");
			}
			this.updateStatusField("final");
		} else {
			this.updateStatusField("draft");
		}
		this.updateStatusBadge(currentStatus);

		// Handle publish toggle change
		publishToggle.addEventListener("change", () => {
			if (publishToggle.checked) {
				// Publishing - set status to final and show visibility options
				this.updateStatusField("final");
				this.updateStatusBadge("final");
				if (visibilitySection) {
					visibilitySection.classList.remove("d-none");
				}
			} else {
				// Not publishing - set status to draft and hide visibility options
				this.updateStatusField("draft");
				this.updateStatusBadge("draft");
				if (visibilitySection) {
					visibilitySection.classList.add("d-none");
				}
				// Reset visibility to private if unpublished
				if (publicOption && publicOption.checked) {
					if (privateOption) {
						privateOption.checked = true;
					}
					this.updateCardBorder(false);
					if (publicWarning) {
						publicWarning.classList.add("d-none");
					}
				}
			}
			// Update review display (submit button will be updated when reaching step 5)
			if (window.updateReviewDatasetDisplay) {
				window.updateReviewDatasetDisplay();
			}

			// Only update button if we're on step 5
			if (this.currentStep === this.step5) {
				this.updateSubmitButton();
			}
		});

		// Handle visibility toggle changes
		if (publicOption) {
			publicOption.addEventListener("change", () => {
				if (publicOption.checked) {
					this.updateCardBorder(true);
					if (publicWarning) {
						publicWarning.classList.remove("d-none");
					}

					// If dataset is final, disable private option permanently
					const statusField = document.getElementById("id_status");
					const currentStatus = statusField ? statusField.value : "draft";
					if (currentStatus === "final" && privateOption) {
						privateOption.disabled = true;
					}
				}
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
				// Only update button if we're on step 5
				if (this.currentStep === this.step5) {
					this.updateSubmitButton();
				}
			});
		}

		if (privateOption) {
			privateOption.addEventListener("change", () => {
				// Prevent changing to private if dataset is final and was public
				const statusField = document.getElementById("id_status");
				const currentStatus = statusField ? statusField.value : "draft";
				if (currentStatus === "final" && publicOption && publicOption.checked) {
					// Don't allow changing back to private for final datasets
					privateOption.checked = false;
					if (publicOption) {
						publicOption.checked = true;
					}
					return;
				}

				if (privateOption.checked) {
					this.updateCardBorder(false);
					if (publicWarning) {
						publicWarning.classList.add("d-none");
					}
				}
				if (window.updateReviewDatasetDisplay) {
					window.updateReviewDatasetDisplay();
				}
				// Only update button if we're on step 5
				if (this.currentStep === this.step5) {
					this.updateSubmitButton();
				}
			});
		}

		// Don't initialize submit button on page load - it will be updated when user reaches step 5
	}

	/**
	 * Update status field value
	 * @param {string} status - Status value ('draft' or 'final')
	 */
	updateStatusField(status) {
		const statusField = document.getElementById("id_status");
		if (statusField) {
			statusField.value = status;
		}
	}

	/**
	 * Update status badge display
	 * @param {string} status - Status value ('draft' or 'final')
	 */
	updateStatusBadge(status) {
		const statusBadge = document.getElementById("current-status-badge");
		if (statusBadge) {
			if (status === "final") {
				statusBadge.textContent = "Final";
				statusBadge.className = "badge bg-success";
			} else {
				statusBadge.textContent = "Draft";
				statusBadge.className = "badge bg-secondary";
			}
		}
	}

	/**
	 * Update card border styling based on public/private status
	 * @param {boolean} isPublic - Whether dataset is public
	 */
	updateCardBorder(isPublic) {
		const publishingCard = document.getElementById("publishing-info-card");
		if (publishingCard) {
			if (isPublic) {
				publishingCard.classList.add("border-danger", "border-3");
			} else {
				publishingCard.classList.remove("border-danger", "border-3");
			}
		}
	}

	/**
	 * Update submit button text and styling based on publishing status
	 */
	updateSubmitButton() {
		const submitBtn = document.getElementById("submitForm");
		const publishToggle = document.getElementById("publish-dataset-toggle");
		const publicOption = document.getElementById("public-option");

		if (!submitBtn) return;

		// Only update button if we're on step 5 (final review page)
		// Check if button is actually visible (which means we're on step 5)
		const isButtonVisible =
			!submitBtn.classList.contains("d-none") &&
			submitBtn.offsetParent !== null &&
			window.getComputedStyle(submitBtn).display !== "none";

		// Don't update if button shouldn't be visible
		if (!isButtonVisible) {
			return;
		}

		// Update button text/style based on publishing status
		// Note: Button visibility is controlled by step navigation (only shown on step 5)
		if (!publishToggle) {
			// Fallback if toggle not found - use default styling
			submitBtn.className = "btn btn-success";
			submitBtn.textContent = this.isEditMode
				? "Update Dataset"
				: "Create Dataset";
			return;
		}

		const isPublishing = publishToggle.checked;
		const isPublic = publicOption && publicOption.checked;

		if (isPublishing && isPublic) {
			// Publishing and making public - red button with "Publish Dataset"
			submitBtn.className = "btn btn-danger";
			submitBtn.textContent = "Publish Dataset";
		} else if (isPublishing) {
			// Publishing but private - warning style
			submitBtn.className = "btn btn-warning";
			submitBtn.textContent = "Publish Dataset";
		} else {
			// Not publishing - normal style
			submitBtn.className = "btn btn-success";
			submitBtn.textContent = this.isEditMode
				? "Update Dataset"
				: "Create Dataset";
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
if (typeof module !== "undefined" && module.exports) {
	module.exports = { DatasetModeManager };
}
