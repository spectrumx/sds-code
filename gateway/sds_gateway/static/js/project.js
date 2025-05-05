import "../sass/project.scss";

/* Project specific Javascript goes here. */

/* js functions for group_captures.html */

class FormHandler {
	constructor(config) {
		this.form = document.getElementById(config.formId);
		this.steps = config.steps;
		this.currentStep = 0;
		this.onStepChange = config.onStepChange;

		// Store references to navigation elements
		this.prevBtn = document.getElementById("prevStep");
		this.nextBtn = document.getElementById("nextStep");
		this.submitBtn = document.getElementById("submitForm");
		this.stepTabs = document.querySelectorAll("#stepTabs .btn");

		// Store references to hidden fields
		this.selectedCapturesField = document.getElementById("selected_captures");
		this.selectedFilesField = document.getElementById("selected_files");

		// Initialize selections
		this.selectedCaptures = new Set();
		this.selectedFiles = new Set();

		// Store references to required fields
		this.nameField = document.getElementById("id_name");
		this.authorField = document.getElementById("id_author");

		this.initializeEventListeners();
		this.validateCurrentStep(); // Initial validation
	}

	initializeEventListeners() {
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

	updateHiddenFields() {
		// Update hidden fields with current selections
		if (this.selectedCapturesField) {
			this.selectedCapturesField.value = Array.from(this.selectedCaptures).join(
				",",
			);
		}
		if (this.selectedFilesField) {
			this.selectedFilesField.value = Array.from(this.selectedFiles).join(",");
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

	navigateStep(direction) {
		if (direction < 0 || this.validateCurrentStep()) {
			this.currentStep += direction;
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
			tab.classList.remove("active", "disabled");
			if (index === this.currentStep) {
				tab.classList.add("active");
			} else if (index > this.currentStep) {
				tab.classList.add("disabled");
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
			this.prevBtn.style.display = this.currentStep > 0 ? "block" : "none";
		}

		// Update next/submit buttons and validate current step
		const isValid = this.validateCurrentStep();
		if (this.nextBtn) {
			const isLastStep = this.currentStep === this.steps.length - 1;
			this.nextBtn.style.display = isLastStep ? "none" : "block";
			this.nextBtn.disabled = !isValid;
		}
		if (this.submitBtn) {
			const isLastStep = this.currentStep === this.steps.length - 1;
			this.submitBtn.style.display = isLastStep ? "block" : "none";
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
			// Update hidden fields one last time before submission
			this.updateHiddenFields();

			// Clear any existing errors
			const errorContainer = document.getElementById("formErrors");
			const errorContent = errorContainer?.querySelector(".error-content");
			if (errorContainer && errorContent) {
				errorContainer.style.display = "none";
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
							errorContainer.style.display = "block";
							errorContainer.scrollIntoView({
								behavior: "smooth",
								block: "start",
							});
						}
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
					errorContainer.style.display = "block";
					errorContainer.scrollIntoView({ behavior: "smooth", block: "start" });
				}
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
		this.selectedFiles = new Map(); // Change to Map to store file info
		this.confirmFileSelection = document.getElementById(
			config.confirmFileSelectionId,
		);
		this.currentTree = null;
		this.formHandler = config.formHandler;

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
			this.confirmFileSelection.addEventListener("click", () =>
				this.updateSelectedFilesList(),
			);
		}
	}

	initializeCapturesSearch() {
		// Initialize event listeners for captures search
		const searchButton = document.getElementById("search-captures");
		const clearButton = document.getElementById("clear-captures-search");
		if (searchButton && clearButton) {
			// Add click handler for search button
			searchButton.addEventListener("click", () => {
				const params = {
					directory: document.getElementById("search_directory_captures").value,
					capture_type: document.getElementById("search_capture_type").value,
					scan_group: document.getElementById("search_scan_group").value,
					channel: document.getElementById("search_channel").value,
				};
				this.fetchCaptures(params).then((data) =>
					this.updateCapturesTable(data),
				);
			});

			// Add click handler for clear button
			clearButton.addEventListener("click", () => {
				document.getElementById("search_directory_captures").value = "";
				document.getElementById("search_capture_type").value = "";
				document.getElementById("search_scan_group").value = "";
				document.getElementById("search_channel").value = "";
				this.fetchCaptures().then((data) => this.updateCapturesTable(data));
			});

			// Load initial data
			this.fetchCaptures().then((data) => this.updateCapturesTable(data));
		}
	}

	async loadFileTree(searchTerm = "") {
		try {
			const data = await this.fetchFiles({ search_term: searchTerm });
			if (!data.tree) {
				console.error("No tree data received:", data);
				return;
			}
			this.renderFileTree(data.tree);

			// Initialize search handlers after tree is loaded
			const searchBtn = document.getElementById("search-files-btn");
			const clearBtn = document.getElementById("clear-search-btn");
			const searchInput = document.getElementById("file-search");

			if (searchBtn && clearBtn && searchInput) {
				// Remove any existing listeners
				const newSearchBtn = searchBtn.cloneNode(true);
				const newClearBtn = clearBtn.cloneNode(true);
				searchBtn.parentNode.replaceChild(newSearchBtn, searchBtn);
				clearBtn.parentNode.replaceChild(newClearBtn, clearBtn);

				// Add new listeners
				newSearchBtn.addEventListener("click", () => {
					this.loadFileTree(searchInput.value);
				});

				newClearBtn.addEventListener("click", () => {
					searchInput.value = "";
					this.loadFileTree();
				});
			}
		} catch (error) {
			console.error("Error loading file tree:", error);
		}
	}

	// Helper function to get relative path
	getRelativePath(file, currentPath = "") {
		if (!currentPath) {
			return file.name;
		}
		return `${currentPath}/${file.name}`;
	}

	renderFileTree(tree, parentElement = null, level = 0, currentPath = "") {
		this.currentTree = tree;
		const targetElement =
			parentElement || document.querySelector("#file-tree-table tbody");
		if (!targetElement) {
			console.error("File tree table body not found");
			return;
		}

		targetElement.innerHTML = "";

		if (
			!tree ||
			((!tree.files || tree.files.length === 0) &&
				Object.keys(tree).length === 0)
		) {
			targetElement.innerHTML =
				'<tr><td colspan="5" class="text-center">No files or directories found</td></tr>';
			return;
		}

		// First render directories
		const directories = { ...tree };
		directories.files = undefined; // Use undefined instead of delete
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
			row.innerHTML = `
                <td>
                    <span class="folder-toggle">▶</span>
                </td>
                <td class="${level > 0 ? `ps-${level * 3}` : ""}">
                    <i class="bi bi-folder me-2"></i>
                    ${content.name || name}
                </td>
                <td>Directory</td>
                <td>${this.formatFileSize(content.size || 0)}</td>
                <td>${content.created_at ? new Date(content.created_at).toLocaleString() : "-"}</td>
            `;
			targetElement.appendChild(row);

			// Create container for nested content
			const nestedContainer = document.createElement("tr");
			nestedContainer.className = "nested-row";
			nestedContainer.style.display = "none";
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
				const newPath = currentPath
					? `${currentPath}/${content.name}`
					: content.name;
				const hasChildren = Object.keys(content.children).length > 0;
				const hasFiles = content.files && content.files.length > 0;
				const expandable = hasChildren || hasFiles;

				const toggle = row.querySelector(".folder-toggle");
				const isExpanded = toggle.textContent === "▼";

				if (expandable) {
					toggle.textContent = isExpanded ? "▶" : "▼";
					nestedContainer.style.display = isExpanded ? "none" : "table-row";
				} else {
					toggle.textContent = "▶";
					nestedContainer.style.display = "none";
				}

				// Load nested content if not already loaded
				if (expandable && !isExpanded && !nestedContainer.dataset.loaded) {
					const subTree = {
						files: content.files || [],
						...content.children,
					};
					this.renderFileTree(
						subTree,
						nestedContainer.querySelector("tbody"),
						level + 1,
						newPath,
					);
					nestedContainer.dataset.loaded = "true";
				}
			});
		}

		// Then render files
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
                    <td>${this.formatFileSize(file.size)}</td>
                    <td>${new Date(file.created_at).toLocaleString()}</td>
                `;

				const checkbox = row.querySelector('input[type="checkbox"]');

				// Add click handler for the checkbox
				checkbox.addEventListener("change", (e) => {
					e.stopPropagation(); // Prevent row click from firing
					if (checkbox.checked) {
						this.selectedFiles.set(file.id, {
							...file,
							relativePath: filePath,
						});
					} else {
						this.selectedFiles.delete(file.id);
					}
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
	}

	// Helper function to format file size
	formatFileSize(bytes) {
		if (bytes === 0) return "0 Bytes";
		const k = 1024;
		const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
	}

	// Function to update captures table
	updateCapturesTable(data) {
		const tbody = document.querySelector("#captures-table tbody");
		tbody.innerHTML = "";

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
			row.innerHTML = `
                <td>
                    <input type="checkbox" class="form-check-input" name="captures" value="${capture.id}" ${isSelected ? "checked" : ""} />
                </td>
                <td>${capture.capture_type === "rh" ? "RadioHound" : capture.capture_type === "drf" ? "DigitalRF" : capture.capture_type}</td>
                <td>${capture.top_level_dir.split("/").pop()}</td>
                <td>${capture.channel || "-"}</td>
                <td>${capture.scan_group || "-"}</td>
                <td>${new Date(capture.created_at).toLocaleString()}</td>
            `;

			// Add click handler for the row
			row.addEventListener("click", (e) => {
				// Don't toggle if clicking the checkbox directly
				if (e.target.type === "checkbox") return;

				const checkbox = row.querySelector('input[type="checkbox"]');
				checkbox.checked = !checkbox.checked;

				// Trigger the change event manually
				checkbox.dispatchEvent(new Event("change"));
			});

			// Add hover effect class
			row.classList.add("clickable-row");

			tbody.appendChild(row);
		}

		// Update pagination
		this.updatePagination("captures", data.pagination);
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

	// Function to find a file in the tree structure
	findFileInTree(tree, fileId) {
		// Check files in current directory
		const file = tree.files?.find((f) => f.id === fileId);
		if (file) return file;

		// Check subdirectories
		for (const dir of Object.values(tree.children || {})) {
			const found = this.findFileInTree(dir, fileId);
			if (found) return found;
		}

		return null;
	}

	// Function to update the selected files list based on files select in the tree
	updateSelectedFilesList() {
		const tbody = document.querySelector("#selected-files-table tbody");
		if (!tbody) {
			console.error("Selected files table body not found");
			return;
		}
		tbody.innerHTML = "";

		// Update the display count
		const displayElement = document.getElementById("selected-files-display");
		if (displayElement) {
			displayElement.value = `${this.selectedFiles.size} file(s) selected`;
		}

		// Update the form handler's selected files
		if (this.formHandler) {
			this.formHandler.selectedFiles = new Set(this.selectedFiles.keys());
			this.formHandler.updateHiddenFields();
		}

		// Update the selected files table
		this.selectedFiles.forEach((fileInfo, fileId) => {
			const row = document.createElement("tr");
			row.innerHTML = `
                <td>${fileInfo.name}</td>
                <td>${fileInfo.media_type || "Unknown"}</td>
                <td>${fileInfo.relativePath}</td>
                <td>${this.formatFileSize(fileInfo.size)}</td>
                <td>
                    <button class="btn btn-sm btn-danger remove-file" data-id="${fileId}">
                        Remove
                    </button>
                </td>
            `;

			// Add click handler for remove button
			const removeBtn = row.querySelector(".remove-file");
			if (removeBtn) {
				removeBtn.addEventListener("click", () => {
					this.selectedFiles.delete(fileId);
					this.updateSelectedFilesList();
					// Update checkbox in file tree
					const checkbox = document.querySelector(
						`input[type="checkbox"][value="${fileId}"]`,
					);
					if (checkbox) {
						checkbox.checked = false;
					}
				});
			}

			tbody.appendChild(row);
		});
	}

	// Function to update pagination
	updatePagination(type, pagination) {
		const paginationContainer = document.querySelector(`#${type}-pagination`);
		if (!paginationContainer) return;

		paginationContainer.innerHTML = "";
		if (pagination.num_pages <= 1) return;

		const ul = document.createElement("ul");
		ul.className = "pagination justify-content-center";

		// Add First/Previous buttons
		if (pagination.has_previous) {
			ul.innerHTML += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="1">First</a>
                </li>
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${pagination.previous_page_number}">Previous</a>
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

		// Add Next/Last buttons
		if (pagination.has_next) {
			ul.innerHTML += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${pagination.next_page_number}">Next</a>
                </li>
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${pagination.num_pages}">Last</a>
                </li>
            `;
		}

		paginationContainer.appendChild(ul);

		// Add click handlers for pagination
		const links = paginationContainer.querySelectorAll("a.page-link");
		for (const link of links) {
			link.addEventListener("click", async (e) => {
				e.preventDefault();
				const page = e.target.dataset.page;

				if (type === "captures") {
					// Get current search parameters
					const searchForm = document.getElementById("captures-search-form");
					const params = {
						directory:
							searchForm.querySelector("[name='search_directory_captures']")
								?.value || "",
						capture_type:
							searchForm.querySelector("[name='search_capture_type']")?.value ||
							"",
						scan_group:
							searchForm.querySelector("[name='search_scan_group']")?.value ||
							"",
						channel:
							searchForm.querySelector("[name='search_channel']")?.value || "",
						page: page,
					};

					const data = await this.fetchCaptures(params);
					this.updateCapturesTable(data);
				} else {
					const searchTerm =
						document.getElementById("file-search")?.value || "";
					const data = await this.fetchFiles({
						search_term: searchTerm,
						page: page,
					});
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
				if (data.tree) {
					this.renderFileTree(data.tree);
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
		// Get all form inputs within the container and clear them
		const inputs = this.searchForm.querySelectorAll("input, select, textarea");
		for (const input of inputs) {
			if (input.value) {
				input.value = "";
			}
		}
		this.handleSearch();
	}
}

// Make classes available globally
window.SearchHandler = SearchHandler;
window.FormHandler = FormHandler;

// Export the classes
export { FormHandler, SearchHandler };
