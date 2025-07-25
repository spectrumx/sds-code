/* js functions for group_captures.html */

class FormHandler {
	constructor(config) {
		this.form = document.getElementById(config.formId);
		this.steps = config.steps;
		this.currentStep = 0;
		this.onStepChange = config.onStepChange;
		this.isEditMode = config.isEditMode || false; // Whether this is an edit form
		this.capturesSearchHandler = null; // Reference to captures SearchHandler instance
		this.filesSearchHandler = null; // Reference to files SearchHandler instance
		this.searchHandler = null; // Current active SearchHandler

		// Store references to navigation elements
		this.prevBtn = document.getElementById("prevStep");
		this.nextBtn = document.getElementById("nextStep");
		this.submitBtn = document.getElementById("submitForm");
		this.stepTabs = document.querySelectorAll("#stepTabs .btn");

		// Store references to hidden fields
		this.selectedCapturesField = document.getElementById("selected_captures");
		this.selectedFilesField = document.getElementById("selected_files");

		// Initialize selections with initial values if provided
		this.selectedCaptures = config.initialCaptures || new Set();
		this.selectedFiles = config.initialFiles || new Set();
		this.selectedCaptureDetails = new Map(
			Object.entries(config.initialCaptureDetails || {}),
		);

		// Update hidden fields with initial values
		this.updateHiddenFields();

		// Store references to required fields
		this.nameField = document.getElementById("id_name");
		this.authorField = document.getElementById("id_author");

		this.initializeEventListeners();
		this.initializeErrorContainer();
		this.validateCurrentStep(); // Initial validation
		this.updateNavigation(); // Initial navigation button display

		// Hide the submit button at the start unless on the last step
		if (this.submitBtn && this.currentStep !== this.steps.length - 1) {
			this.hide(this.submitBtn);
		}
	}

	// Add method to set SearchHandler reference
	setSearchHandler(searchHandler, type) {
		if (type === "captures") {
			this.capturesSearchHandler = searchHandler;
		} else if (type === "files") {
			this.filesSearchHandler = searchHandler;
			this.filesSearchHandler.updateSelectedFilesList();
		}
		this.searchHandler = searchHandler;
	}

	initializeEventListeners() {
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
			this.prevBtn.addEventListener("click", () => this.navigateStep(-1));
		}
		if (this.nextBtn) {
			this.nextBtn.addEventListener("click", () => this.navigateStep(1));
		}
		if (this.submitBtn) {
			this.submitBtn.addEventListener("click", (e) => this.handleSubmit(e));
		}

		// Step tab handlers
		this.stepTabs.forEach((tab, index) => {
			tab.addEventListener("click", () => {
				if (index <= this.currentStep) {
					this.currentStep = index;
					this.updateNavigation();
				}
			});
		});

		// Dataset info validation
		if (this.nameField) {
			this.nameField.addEventListener("input", () =>
				this.validateCurrentStep(),
			);
		}
		if (this.authorField) {
			this.authorField.addEventListener("input", () =>
				this.validateCurrentStep(),
			);
		}

		// Capture selection handler
		document.addEventListener("change", (e) => {
			if (e.target.matches('input[name="captures"]')) {
				if (e.target.checked) {
					this.selectedCaptures.add(e.target.value);
				} else {
					this.selectedCaptures.delete(e.target.value);
				}
				this.updateHiddenFields();
			}
		});
	}

	initializeErrorContainer() {
		const errorContainer = document.getElementById("formErrors");
		if (errorContainer) {
			this.hide(errorContainer);
		}
	}

	show(container, showClass = "display-block") {
		container.classList.remove("display-none");
		container.classList.add(showClass);
	}

	hide(container, showClass = "display-block") {
		container.classList.remove(showClass);
		container.classList.add("display-none");
	}

	updateHiddenFields() {
		// Update hidden fields with current selections
		if (this.selectedCapturesField) {
			this.selectedCapturesField.value = Array.from(this.selectedCaptures).join(
				",",
			);
		}
		if (this.selectedFilesField) {
			this.selectedFilesField.value = Array.from(this.selectedFiles)
				.map((file) => file.id)
				.join(",");
		}
	}

	dataSetNameDisplay() {
		const nameDisplays = document.getElementsByClassName(
			"dataset-name-display",
		);
		const nameInput = document.getElementById("id_name");
		if (nameInput && nameDisplays.length > 0) {
			for (const nameDisplay of Array.from(nameDisplays)) {
				nameDisplay.textContent = nameInput.value || "Untitled Dataset";
			}
		}
	}

	async navigateStep(direction) {
		if (direction < 0 || this.validateCurrentStep()) {
			const nextStep = this.currentStep + direction;

			// If moving to review step (step 4), update the review content
			if (nextStep === 3) {
				// Update form values in review step
				document.querySelector("#step4 .dataset-name").textContent =
					this.nameField.value;
				document.querySelector("#step4 .dataset-author").textContent =
					this.authorField.value;
				document.querySelector("#step4 .dataset-description").textContent =
					document.getElementById("id_description").value ||
					"No description provided.";

				// Update captures table
				const capturesTableBody = document.querySelector(
					"#step4 .captures-table tbody",
				);

				if (
					capturesTableBody &&
					this.selectedCaptures.size > 0 &&
					this.capturesSearchHandler
				) {
					capturesTableBody.innerHTML = Array.from(this.selectedCaptures)
						.map((captureId) => {
							const data =
								this.capturesSearchHandler.selectedCaptureDetails.get(
									captureId,
								) || {
									type: "Unknown",
									directory: "Unknown",
									channel: "-",
									scan_group: "-",
									created_at: new Date().toISOString(),
								};
							return `
							<tr>
								<td>${data.type}</td>
								<td>${data.directory}</td>
								<td>${data.channel}</td>
								<td>${data.scan_group}</td>
								<td>${new Date(data.created_at).toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" })}</td>
								<td>
									<button class="btn btn-sm btn-danger remove-capture" data-id="${captureId}">
										Remove
									</button>
								</td>
							</tr>
						`;
						})
						.join("");

					// Add event listeners for capture removal
					const removeButtons =
						capturesTableBody.querySelectorAll(".remove-capture");
					for (const button of removeButtons) {
						button.addEventListener("click", () => {
							const captureId = button.dataset.id;
							// Remove from selected captures
							this.selectedCaptures.delete(captureId);
							// Remove from capture details
							if (this.capturesSearchHandler) {
								this.capturesSearchHandler.selectedCaptureDetails.delete(
									captureId,
								);
							}
							// Update hidden field
							this.updateHiddenFields();
							// Update checkbox and row styling in captures table if visible
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
							// Remove the row
							button.closest("tr").remove();
							// Update count
							const capturesCount = this.selectedCaptures.size;
							document.querySelector("#step4 .captures-count").textContent =
								`${capturesCount} selected`;
							// Show "No captures selected" if none left
							if (capturesCount === 0) {
								capturesTableBody.innerHTML =
									"<tr><td colspan='6' class='text-center'>No captures selected</td></tr>";
							}
							// Update the selected captures pane in step 2 if it exists
							if (this.capturesSearchHandler) {
								this.capturesSearchHandler.updateSelectedCapturesPane();
							}
						});
					}
				} else {
					capturesTableBody.innerHTML =
						"<tr><td colspan='6' class='text-center'>No captures selected</td></tr>";
				}

				// Update files table
				const filesTableBody = document.querySelector(
					"#step4 .files-table tbody",
				);
				if (filesTableBody && this.selectedFiles.size > 0) {
					filesTableBody.innerHTML = Array.from(this.selectedFiles)
						.map(
							(file) => `
						<tr>
							<td>${file.name}</td>
							<td>${file.media_type || "Unknown"}</td>
							<td>${file.relative_path}</td>
							<td>${this.formatFileSize(file.size)}</td>
							<td>
								<button class="btn btn-sm btn-danger remove-file" data-id="${file.id}">
									Remove
								</button>
							</td>
						</tr>
					`,
						)
						.join("");

					// Add event listeners for file removal
					const removeFileButtons =
						filesTableBody.querySelectorAll(".remove-file");
					for (const button of removeFileButtons) {
						button.addEventListener("click", () => {
							const fileId = button.dataset.id;
							const fileToRemove = Array.from(this.selectedFiles).find(
								(f) => f.id === fileId,
							);
							if (fileToRemove) {
								// Remove from selected files
								this.selectedFiles.delete(fileToRemove);
								// Update SearchHandler's selectedFiles Map
								if (this.filesSearchHandler) {
									this.filesSearchHandler.selectedFiles.delete(fileId);
									// Update the selected files list in SearchHandler
									this.filesSearchHandler.updateSelectedFilesList();
								}
								// Update hidden field
								this.updateHiddenFields();
								// Update checkbox in file tree if visible
								const checkbox = document.querySelector(
									`input[name="files"][value="${fileId}"]`,
								);
								if (checkbox) {
									checkbox.checked = false;
								}
								// Remove the row
								button.closest("tr").remove();
								// Update count
								const filesCount = this.selectedFiles.size;
								document.querySelector("#step4 .files-count").textContent =
									`${filesCount} selected`;
								// Show "No files selected" if none left
								if (filesCount === 0) {
									filesTableBody.innerHTML =
										"<tr><td colspan='5' class='text-center'>No files selected</td></tr>";
								}
							}
						});
					}
				} else {
					filesTableBody.innerHTML =
						"<tr><td colspan='5' class='text-center'>No files selected</td></tr>";
				}

				// Update selection counts
				const capturesCount = this.selectedCaptures.size;
				const filesCount = this.selectedFiles.size;
				document.querySelector("#step4 .captures-count").textContent =
					`${capturesCount} selected`;
				document.querySelector("#step4 .files-count").textContent =
					`${filesCount} selected`;
			}

			this.currentStep = nextStep;
			this.updateNavigation();
			this.dataSetNameDisplay();
			if (this.onStepChange) {
				this.onStepChange(this.currentStep);
			}
		}
	}

	updateNavigation() {
		// Update step tabs
		this.stepTabs.forEach((tab, index) => {
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
				// Previous tabs get a light blue color and are disabled
				tab.classList.add("btn-primary", "inactive-tab");
			}
		});

		// Update content panes
		document.querySelectorAll(".tab-pane").forEach((pane, index) => {
			pane.classList.remove("show", "active");
			if (index === this.currentStep) {
				pane.classList.add("show", "active");
			}
		});

		// Update navigation buttons
		if (this.prevBtn) {
			this.currentStep > 0 ? this.show(this.prevBtn) : this.hide(this.prevBtn);
		}

		// Update next/submit buttons and validate current step
		const isValid = this.validateCurrentStep();
		if (this.nextBtn) {
			const isLastStep = this.currentStep === this.steps.length - 1;
			isLastStep ? this.hide(this.nextBtn) : this.show(this.nextBtn);
			this.nextBtn.disabled = !isValid;
		}
		if (this.submitBtn) {
			const isLastStep = this.currentStep === this.steps.length - 1;
			isLastStep ? this.show(this.submitBtn) : this.hide(this.submitBtn);
			this.submitBtn.disabled = !isValid;
		}
	}

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

		// Update button states based on validation
		if (this.nextBtn) {
			this.nextBtn.disabled = !isValid;
		}
		if (this.submitBtn && this.currentStep === this.steps.length - 1) {
			this.submitBtn.disabled = !isValid;
		}

		return isValid;
	}

	validateDatasetInfo() {
		// Only check if both fields have non-empty values
		const nameValue = this.nameField?.value.trim() || "";
		const authorValue = this.authorField?.value.trim() || "";
		return nameValue !== "" && authorValue !== "";
	}

	validateCapturesSelection() {
		return true; // Keep as is per requirements
	}

	validateFilesSelection() {
		return true; // Keep as is per requirements
	}

	async handleSubmit(e) {
		e.preventDefault();
		if (this.validateCurrentStep()) {
			// Set loading state
			this.setSubmitButtonLoading(true);

			// Update hidden fields one last time before submission
			this.updateHiddenFields();

			// Clear any existing errors
			const errorContainer = document.getElementById("formErrors");
			const errorContent = errorContainer?.querySelector(".error-content");
			if (errorContainer && errorContent) {
				this.hide(errorContainer);
				errorContent.innerHTML = "";
			}

			const formData = new FormData(this.form);
			try {
				const response = await fetch(this.form.action, {
					method: "POST",
					body: formData,
					headers: {
						"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")
							.value,
					},
				});

				const data = await response.json();

				if (!response.ok) {
					if (response.status === 400 && data.errors) {
						// Show errors in the error container
						let errorHtml = '<ul class="mb-0 list-unstyled">';
						for (const [field, messages] of Object.entries(data.errors)) {
							if (Array.isArray(messages)) {
								for (const message of messages) {
									errorHtml += `<li>${field === "non_field_errors" ? "" : `<strong>${field}:</strong> `}${message}</li>`;
								}
							} else if (typeof messages === "string") {
								errorHtml += `<li>${field === "non_field_errors" ? "" : `<strong>${field}:</strong> `}${messages}</li>`;
							}
						}
						errorHtml += "</ul>";

						if (errorContainer && errorContent) {
							errorContent.innerHTML = errorHtml;
							this.show(errorContainer);
							errorContainer.scrollIntoView({
								behavior: "smooth",
								block: "start",
							});
						}
						// Reset loading state on error
						this.setSubmitButtonLoading(false);
						return;
					}
					throw new Error("Server error");
				}

				if (data.success) {
					window.location.href = data.redirect_url;
				} else if (data.errors) {
					throw new Error(data.errors.join(", "));
				}
			} catch (error) {
				console.error("Error submitting form:", error);
				if (errorContainer && errorContent) {
					errorContent.innerHTML =
						'<ul class="mb-0 list-unstyled"><li>An unexpected error occurred. Please try again.</li></ul>';
					this.show(errorContainer);
					errorContainer.scrollIntoView({ behavior: "smooth", block: "start" });
				}
				// Reset loading state on error
				this.setSubmitButtonLoading(false);
			}
		}
	}

	// Helper function to format file size
	formatFileSize(bytes) {
		if (bytes === 0) return "0 Bytes";
		const k = 1024;
		const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
	}

	// Set loading state for submit button
	setSubmitButtonLoading(isLoading) {
		if (!this.submitBtn) return;

		if (isLoading) {
			// Store original text
			this.submitBtn.dataset.originalText = this.submitBtn.textContent;
			// Set loading state
			this.submitBtn.disabled = true;
			const busyText = this.isEditMode ? 'Updating...' : 'Creating...';
			this.submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>' + busyText;
		} else {
			// Restore original state
			this.submitBtn.disabled = false;
			if (this.submitBtn.dataset.originalText) {
				this.submitBtn.textContent = this.submitBtn.dataset.originalText;
			}
		}
	}
}

class SearchHandler {
	constructor(config) {
		this.searchForm = document.getElementById(config.searchFormId);
		this.searchButton = document.getElementById(config.searchButtonId);
		this.clearButton = document.getElementById(config.clearButtonId);
		this.tableBody = document.getElementById(config.tableBodyId);
		this.paginationContainer = document.getElementById(
			config.paginationContainerId,
		);
		this.type = config.type;
		this.selectedFiles = new Map(
			Object.entries(config.initialFileDetails || {}),
		);
		this.confirmFileSelection = document.getElementById(
			config.confirmFileSelectionId,
		);
		this.currentTree = null;
		this.formHandler = config.formHandler;
		this.currentFilters = {}; // Store current capture filters
		this.selectedCaptureDetails = new Map(
			Object.entries(config.initialCaptureDetails || {}),
		);

		// Set the form handler's reference to this SearchHandler instance
		if (config.formHandler) {
			config.formHandler.setSearchHandler(this, config.type);
		}

		this.initializeEventListeners();
	}

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

			const response = await fetch(
				`${window.location.pathname}?${searchParams.toString()}`,
				{
					headers: {
						"X-Requested-With": "XMLHttpRequest",
					},
				},
			);

			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}

			return await response.json();
		} catch (error) {
			console.error("Error fetching captures:", error);
			return { results: [], pagination: {} };
		}
	}

	async fetchFiles(params = {}) {
		try {
			const searchParams = new URLSearchParams(params);
			const response = await fetch(
				`${window.location.pathname}?${searchParams.toString()}&search_files=true`,
				{
					headers: {
						"X-Requested-With": "XMLHttpRequest",
					},
				},
			);

			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}

			return await response.json();
		} catch (error) {
			console.error("Error fetching files:", error);
			return { tree: {}, pagination: {} };
		}
	}

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
				this.updateSelectedFilesList();
				this.handleClear();
			});
		}
		this.initializeEnterKeyListener();
	}

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

	initializeSelectAllCheckbox() {
		const selectAllCheckbox = document.getElementById(
			"select-all-files-checkbox",
		);
		if (selectAllCheckbox) {
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
	}

	initializeRemoveAllButton() {
		const removeAllButton = document.getElementById(
			"remove-all-selected-files-button",
		);
		if (removeAllButton) {
			removeAllButton.addEventListener("click", () => {
				//deselect all files
				const fileCheckboxes = document.querySelectorAll(
					'#file-tree-table tbody input[type="checkbox"]',
				);
				for (const checkbox of fileCheckboxes) {
					checkbox.checked = false;
					checkbox.dispatchEvent(new Event("change"));
				}

				this.selectedFiles.clear();
				this.updateSelectedFilesList();
			});
		}
	}

	initializeCapturesSearch() {
		// Initialize event listeners for captures search
		const searchButton = document.getElementById("search-captures");
		const clearButton = document.getElementById("clear-captures-search");

		if (searchButton && clearButton) {
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

			// Check if the selected captures pane exists
			if (!document.getElementById("selected-captures-pane")) {
				// Create selected captures pane
				this.createSelectedCapturesPane();
			}

			// Load initial data
			this.fetchCaptures().then((data) => this.updateCapturesTable(data));
		}
	}

	createSelectedCapturesPane() {
		// Create the selected captures pane next to the captures table
		const capturesContainer = document.querySelector("#step2 .row");
		if (!capturesContainer) return;

		// Create the selected captures pane
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

		// Add the selected pane
		capturesContainer.appendChild(selectedPane);
	}

	updateSelectedCapturesPane() {
		const selectedList = document.getElementById("selected-captures-list");
		const countBadge = document.querySelector(".selected-captures-count");
		if (!selectedList || !countBadge || !this.formHandler) return;

		const selectedCaptures = this.formHandler.selectedCaptures;
		countBadge.textContent = `${selectedCaptures.size} selected`;

		if (selectedCaptures.size === 0) {
			selectedList.innerHTML =
				'<tr><td colspan="3" class="text-center">No captures selected</td></tr>';
			return;
		}

		selectedList.innerHTML = Array.from(selectedCaptures)
			.map((captureId) => {
				const data = this.selectedCaptureDetails.get(captureId) || {
					type: "Unknown",
					directory: "Unknown",
				};
				return `
				<tr>
					<td>${data.type}</td>
					<td>${data.directory}</td>
					<td>
						<button class="btn btn-sm btn-danger remove-selected-capture" data-id="${captureId}">
							Remove
						</button>
					</td>
				</tr>
			`;
			})
			.join("");

		// Add remove handlers
		const removeSelectedButtons = selectedList.querySelectorAll(
			".remove-selected-capture",
		);
		for (const button of removeSelectedButtons) {
			button.addEventListener("click", () => {
				const captureId = button.dataset.id;
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
			});
		}
	}

	updateCapturesTable(data) {
		const tbody = document.querySelector("#captures-table tbody");
		tbody.innerHTML = "";

		// Update the results count
		this.updateResultsCount(data.results.length);

		if (data.results.length === 0) {
			tbody.innerHTML =
				'<tr><td colspan="6" class="text-center">No captures found</td></tr>';
			return;
		}

		for (const capture of data.results) {
			const row = document.createElement("tr");
			const isSelected = this.formHandler?.selectedCaptures.has(
				capture.id.toString(),
			);

			// Add hover class and selected class if applicable
			row.classList.add("capture-row");
			if (isSelected) {
				row.classList.add("table-warning");
			}

			row.innerHTML = `
				<td>
					<input type="checkbox" class="form-check-input" name="captures" value="${capture.id}" ${isSelected ? "checked" : ""} />
				</td>
				<td>${capture.type}</td>
				<td>${capture.directory}</td>
				<td>${capture.channel}</td>
				<td>${capture.scan_group}</td>
				<td>${new Date(capture.created_at).toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" })}</td>
			`;

			const handleSelection = (e) => {
				const checkbox = row.querySelector('input[type="checkbox"]');
				if (e.target.type !== "checkbox") {
					checkbox.checked = !checkbox.checked;
				}

				const captureId = capture.id.toString();
				if (checkbox.checked) {
					this.formHandler.selectedCaptures.add(captureId);
					row.classList.add("table-warning");
					// Store capture details when selected, using the serialized data directly
					this.selectedCaptureDetails.set(captureId, {
						type: capture.type,
						directory: capture.directory,
						channel: capture.channel,
						scan_group: capture.scan_group,
						created_at: capture.created_at,
					});
				} else {
					this.formHandler.selectedCaptures.delete(captureId);
					row.classList.remove("table-warning");
					this.selectedCaptureDetails.delete(captureId);
				}

				this.formHandler.updateHiddenFields();
				this.updateSelectedCapturesPane();
			};

			// Add click handler for the row
			row.addEventListener("click", handleSelection);

			// Add specific handler for checkbox to prevent double-triggering
			const checkbox = row.querySelector('input[type="checkbox"]');
			checkbox.addEventListener("change", (e) => {
				e.stopPropagation();
				handleSelection(e);
			});

			tbody.appendChild(row);
		}

		// Update pagination with current filters
		this.updatePagination("captures", data.pagination);

		// Update selected captures pane
		this.updateSelectedCapturesPane();
	}

	updatePagination(type, pagination) {
		const paginationContainer = document.querySelector(`#${type}-pagination`);
		if (!paginationContainer) return;

		paginationContainer.innerHTML = "";
		if (pagination.num_pages <= 1) return;

		const ul = document.createElement("ul");
		ul.className = "pagination justify-content-center";

		// Add Previous button with arrow
		if (pagination.has_previous) {
			ul.innerHTML += `
				<li class="page-item">
					<a class="page-link" href="#" data-page="${pagination.number - 1}" aria-label="Previous">
						<span aria-hidden="true">&laquo;</span>
					</a>
				</li>
			`;
		}

		// Add page numbers
		const startPage = Math.max(1, pagination.number - 2);
		const endPage = Math.min(pagination.num_pages, pagination.number + 2);

		for (let i = startPage; i <= endPage; i++) {
			ul.innerHTML += `
				<li class="page-item ${i === pagination.number ? "active" : ""}">
					<a class="page-link" href="#" data-page="${i}">${i}</a>
				</li>
			`;
		}

		// Add Next button with arrow
		if (pagination.has_next) {
			ul.innerHTML += `
				<li class="page-item">
					<a class="page-link" href="#" data-page="${pagination.number + 1}" aria-label="Next">
						<span aria-hidden="true">&raquo;</span>
					</a>
				</li>
			`;
		}

		paginationContainer.appendChild(ul);

		// Add click handlers for pagination
		const links = paginationContainer.querySelectorAll("a.page-link");
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

			const response = await fetch(
				`${window.location.pathname}?${params.toString()}`,
				{
					headers: {
						"X-Requested-With": "XMLHttpRequest",
					},
				},
			);

			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}

			const data = await response.json();

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
						extensionSelect.innerHTML = data.extension_choices
							.map(
								([value, label]) =>
									`<option value="${value}" ${value === currentValue ? "selected" : ""}>${label}</option>`,
							)
							.join("");
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

	updateSelectedFilesList() {
		// Update form handler's selectedFiles with current selection
		if (this.formHandler) {
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

		// Update selected files table if it exists
		const selectedFilesTable = document.getElementById("selected-files-table");
		const selectedFilesBody = selectedFilesTable?.querySelector("tbody");
		if (selectedFilesBody) {
			if (this.selectedFiles.size === 0) {
				selectedFilesBody.innerHTML =
					'<tr><td colspan="5" class="text-center">No files selected</td></tr>';
			} else {
				selectedFilesBody.innerHTML = Array.from(this.selectedFiles.entries())
					.map(
						([id, file]) => `
					<tr>
						<td>${file.name}</td>
						<td>${file.media_type}</td>
						<td>${file.relative_path}</td>
						<td>${this.formHandler.formatFileSize(file.size)}</td>
						<td>
							<button class="btn btn-sm btn-danger remove-selected-file" data-id="${id}">
								Remove
							</button>
						</td>
					</tr>
				`,
					)
					.join("");

				// Add event listeners for file removal
				const removeSelectedFileButtons = selectedFilesBody.querySelectorAll(
					".remove-selected-file",
				);
				for (const button of removeSelectedFileButtons) {
					button.addEventListener("click", () => {
						const fileId = button.dataset.id;
						// Remove from selected files
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
					});
				}
			}
		}

		// Update count badge
		const countBadge = document.querySelector(".selected-files-count");
		if (countBadge) {
			countBadge.textContent = `${this.selectedFiles.size} selected`;
		}
	}

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
				extensionSelect.innerHTML = data.extension_choices
					.map(([value, label]) => `<option value="${value}">${label}</option>`)
					.join("");
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

	// Helper function to get relative path
	getRelativePath(file, currentPath = "") {
		if (!currentPath) {
			return "";
		}
		return `/${currentPath}`;
	}

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

			// Set initial toggle state based on search term
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
			row.addEventListener("click", () => {
				const hasChildren = Object.keys(content.children || {}).length > 0;
				const hasFiles = content.files && content.files.length > 0;
				const expandable = hasChildren || hasFiles;

				const toggle = row.querySelector(".folder-toggle");
				const isExpanded = toggle.textContent === "▼";

				if (expandable) {
					toggle.textContent = isExpanded ? "▶" : "▼";
					isExpanded
						? this.formHandler.hide(nestedContainer, "display-table-row")
						: this.formHandler.show(nestedContainer, "display-table-row");
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

			// If there's a search term, automatically load and expand the content
			if (searchTermEntered && !nestedContainer.dataset.loaded) {
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
						this.selectedFiles.set(file.id, {
							...file,
							relative_path: filePath,
						});
					} else {
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

	// Function to update files table
	updateFilesTable(data) {
		const tbody = document.querySelector("#file-tree-table tbody");
		if (!tbody) {
			console.error("File tree table body not found");
			return;
		}
		tbody.innerHTML = "";

		if (!data.tree) {
			tbody.innerHTML =
				'<tr><td colspan="5" class="text-center">No files or directories found</td></tr>';
			return;
		}

		this.renderFileTree(data.tree);
	}

	showError(message) {
		const errorContainer = document.getElementById("formErrors");
		const errorContent = errorContainer?.querySelector(".error-content");
		if (errorContainer && errorContent) {
			errorContent.innerHTML = `<ul class="mb-0 list-unstyled"><li>${message}</li></ul>`;
			this.formHandler.show(errorContainer);
			errorContainer.scrollIntoView({ behavior: "smooth", block: "start" });
		}
	}

	// Helper function to update select all checkbox state
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

	updateResultsCount(count) {
		const resultsCountElement = document.getElementById("results-count");
		if (resultsCountElement) {
			const captureText = count === 1 ? "capture" : "captures";
			resultsCountElement.textContent = `${count} ${captureText} found`;
		}
	}
}

// Make classes available globally
window.SearchHandler = SearchHandler;
window.FormHandler = FormHandler;

// Export the classes (commented out to avoid syntax error in non-module context)
// export { FormHandler, SearchHandler };
