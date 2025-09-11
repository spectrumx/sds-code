/**
 * Dataset Details Modal Handler
 * Manages the dataset details modal with file tree display using file browser logic
 */
class DatasetDetailsModal {
	constructor() {
		this.currentDatasetUuid = null;
		this.currentTree = null;
		this.formHandler = {
			show: (container, showClass = "display-block") => {
				container.classList.remove("display-none");
				container.classList.add(showClass);
			},
			hide: (container, showClass = "display-block") => {
				container.classList.remove(showClass);
				container.classList.add("display-none");
			},
			formatFileSize: (bytes) => {
				if (bytes === 0) return "0 Bytes";
				const k = 1024;
				const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
				const i = Math.floor(Math.log(bytes) / Math.log(k));
				return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
			},
		};

		this.initializeEventListeners();
	}

	/**
	 * Initialize event listeners
	 */
	initializeEventListeners() {
		// Modal show event
		document.addEventListener("show.bs.modal", (event) => {
			if (event.target.id === "datasetDetailsModal") {
				const button = event.relatedTarget;
				const datasetUuid = button.getAttribute("data-dataset-uuid");
				if (datasetUuid) {
					this.openDatasetDetails(datasetUuid);
				}
			}
		});

		// Reset modal when it's hidden
		document
			.getElementById("datasetDetailsModal")
			.addEventListener("hidden.bs.modal", (event) => {
				if (event.target.id === "datasetDetailsModal") {
					this.resetModal();
				}
			});

		// Copy UUID button functionality
		document.addEventListener("click", (event) => {
			if (event.target.closest(".copy-uuid-btn")) {
				this.copyDatasetUuid();
			}
		});
	}

	/**
	 * Open dataset details modal with dataset information
	 */
	async openDatasetDetails(datasetUuid) {
		this.currentDatasetUuid = datasetUuid;

		try {
			// Show loading state
			this.showLoadingState();

			// Load dataset information
			await this.loadDatasetInfo(datasetUuid);

			// Load file tree
			await this.loadFileTree();
		} catch (error) {
			console.error("Error opening dataset details:", error);
			this.showError("Failed to load dataset details");
		}
	}

	/**
	 * Load dataset information from view
	 */
	async loadDatasetInfo(datasetUuid) {
		try {
			const response = await fetch(
				`/users/dataset-details/?dataset_uuid=${datasetUuid}`,
				{
					method: "GET",
					headers: {
						"Content-Type": "application/json",
						"X-CSRFToken": this.getCSRFToken(),
					},
				},
			);

			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}

			const data = await response.json();
			this.populateDatasetInfo(data.dataset);
		} catch (error) {
			console.error("Error loading dataset info:", error);
			throw error;
		}
	}

	/**
	 * Populate dataset information in the modal
	 */
	populateDatasetInfo(dataset) {
		// Store dataset UUID for copy functionality
		this.currentDatasetUuid = dataset.uuid;

		// Dataset basic info
		document.querySelector(".dataset-details-name").textContent =
			dataset.name || "N/A";
		// Format authors with ORCID links
		const authorElement = document.querySelector(".dataset-details-author");
		if (dataset.authors && Array.isArray(dataset.authors)) {
			const authorNames = dataset.authors.map((author) => {
				if (typeof author === "string") {
					return author;
				}
				const name = author.name || "Unnamed Author";
				const orcid = author.orcid_id;
				if (orcid) {
					return `${name} (<a href="https://orcid.org/${orcid}" target="_blank" class="text-decoration-none">${orcid}</a>)`;
				}
				return name;
			});
			authorElement.innerHTML = authorNames.join(", ");
		} else if (dataset.authors) {
			// Handle legacy string format
			authorElement.textContent = dataset.authors;
		} else {
			authorElement.textContent = "N/A";
		}
		document.querySelector(".dataset-details-description").textContent =
			dataset.description || "No description available";

		// Format status with badge using database values
		const statusElement = document.querySelector(".dataset-details-status");
		if (dataset.status === "draft") {
			statusElement.innerHTML = `<span class="badge bg-secondary">${dataset.status_display || "Draft"}</span>`;
		} else if (dataset.status === "final") {
			statusElement.innerHTML = `<span class="badge bg-success">${dataset.status_display || "Final"}</span>`;
		} else {
			statusElement.textContent =
				dataset.status_display || dataset.status || "N/A";
		}

		// Format dates
		const createdDate = dataset.created_at
			? new Date(dataset.created_at).toLocaleString()
			: "N/A";
		const updatedDate = dataset.updated_at
			? new Date(dataset.updated_at).toLocaleString()
			: "N/A";

		document.querySelector(".dataset-details-created").textContent =
			createdDate;
		document.querySelector(".dataset-details-updated").textContent =
			updatedDate;
	}

	/**
	 * Copy dataset UUID to clipboard
	 */
	async copyDatasetUuid() {
		if (!this.currentDatasetUuid) {
			this.showAlert("No dataset UUID available to copy", "warning");
			return;
		}

		try {
			await navigator.clipboard.writeText(this.currentDatasetUuid);

			// Update button to show success state
			const copyBtn = document.querySelector(".copy-uuid-btn");
			const icon = copyBtn.querySelector("i");
			const originalIcon = icon.className;
			const originalTitle = copyBtn.getAttribute("title");
			const originalClasses = copyBtn.className;

			// Change icon, title, and button styling to show success
			icon.className = "bi bi-check-circle-fill";
			copyBtn.className = "btn btn-sm btn-success copy-uuid-btn";
			copyBtn.setAttribute("title", "UUID copied!");

			// Show success message to user
			this.showAlert(
				"Dataset UUID copied to clipboard successfully",
				"success",
			);

			// Reset after 2 seconds
			setTimeout(() => {
				icon.className = originalIcon;
				copyBtn.className = originalClasses;
				copyBtn.setAttribute("title", originalTitle);
			}, 2000);
		} catch (error) {
			console.error("Failed to copy UUID:", error);

			// Show error state briefly
			const copyBtn = document.querySelector(".copy-uuid-btn");
			const icon = copyBtn.querySelector("i");
			const originalIcon = icon.className;
			const originalTitle = copyBtn.getAttribute("title");
			const originalClasses = copyBtn.className;

			// Change to error state
			icon.className = "bi bi-x-circle-fill";
			copyBtn.className = "btn btn-sm btn-danger copy-uuid-btn";
			copyBtn.setAttribute("title", "Failed to copy");

			// Show user-visible error message
			let errorMessage = "Failed to copy UUID to clipboard";
			if (error.name === "NotAllowedError") {
				errorMessage =
					"Clipboard access denied. Please copy the UUID manually.";
			} else if (error.name === "NotSupportedError") {
				errorMessage =
					"Clipboard API not supported. Please copy the UUID manually.";
			} else if (error.name === "SecurityError") {
				errorMessage =
					"Clipboard access blocked by security policy. Please copy the UUID manually.";
			}
			this.showAlert(errorMessage, "error");

			// Reset after 2 seconds
			setTimeout(() => {
				icon.className = originalIcon;
				copyBtn.className = originalClasses;
				copyBtn.setAttribute("title", originalTitle);
			}, 2000);
		}
	}

	/**
	 * Load file tree for the dataset
	 */
	async loadFileTree() {
		if (!this.currentDatasetUuid) return;

		try {
			const params = {
				dataset_uuid: this.currentDatasetUuid,
			};

			const data = await this.fetchDatasetFiles(params);
			if (!data.tree) {
				console.error("No tree data received:", data);
				return;
			}

			// Render the file tree
			this.renderFileTree(data.tree, null, 0, "", false);

			// Update statistics
			this.updateFileStatistics(data);
		} catch (error) {
			console.error("Error loading file tree:", error);
			this.showError("Failed to load file tree");
		}
	}

	/**
	 * Fetch dataset files from view
	 */
	async fetchDatasetFiles(params) {
		const response = await fetch(
			`/users/dataset-details/?dataset_uuid=${this.currentDatasetUuid}`,
			{
				method: "GET",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": this.getCSRFToken(),
				},
			},
		);

		if (!response.ok) {
			throw new Error(`HTTP error! status: ${response.status}`);
		}

		return await response.json();
	}

	/**
	 * Helper function to get relative path
	 */
	getRelativePath(file, currentPath = "") {
		if (!currentPath) {
			return "";
		}
		return `/${currentPath}`;
	}

	/**
	 * Render file tree using the same logic as file browser
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
			parentElement || document.querySelector("#dataset-file-tree-table tbody");
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

				row.innerHTML = `
                    <td></td>
                    <td class="${level > 0 ? `ps-${level * 3}` : ""}">
                        <i class="bi bi-file-earmark me-2"></i>
                        ${file.name}
                    </td>
                    <td>${file.media_type || "Unknown"}</td>
                    <td>${this.formHandler.formatFileSize(file.size)}</td>
                    <td>${new Date(file.created_at).toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" })}</td>
                `;

				targetElement.appendChild(row);
			}
		}
	}

	/**
	 * Update file statistics
	 */
	updateFileStatistics(data) {
		const stats = data.statistics || {};

		document.getElementById("total-files-count").textContent =
			stats.total_files || 0;
		document.getElementById("captures-count").textContent = stats.captures || 0;
		document.getElementById("artifacts-count").textContent =
			stats.artifacts || 0;
		document.getElementById("total-size").textContent =
			this.formHandler.formatFileSize(stats.total_size || 0);
	}

	/**
	 * Handle download
	 */
	async handleDownload() {
		this.showAlert(
			"Download functionality not available in view-only mode",
			"info",
		);
	}

	/**
	 * Show loading state
	 */
	showLoadingState() {
		const tbody = document.querySelector("#dataset-file-tree-table tbody");
		if (tbody) {
			tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center py-4">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="mt-2 mb-0">Loading dataset files...</p>
                    </td>
                </tr>
            `;
		}
	}

	/**
	 * Show error message
	 */
	showError(message) {
		const tbody = document.querySelector("#dataset-file-tree-table tbody");
		if (tbody) {
			tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center text-danger py-4">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        ${this.escapeHtml(message)}
                    </td>
                </tr>
            `;
		}
	}

	/**
	 * Show alert message
	 */
	showAlert(message, type = "info") {
		if (window.showAlert) {
			window.showAlert(message, type);
		} else {
			console.log(`${type.toUpperCase()}: ${message}`);
		}
	}

	/**
	 * Reset modal state
	 */
	resetModal() {
		this.currentDatasetUuid = null;
		this.currentTree = null;

		// Clear form inputs
		const searchContainer = document.getElementById(
			"dataset-files-search-form",
		);
		if (searchContainer) {
			const inputs = searchContainer.querySelectorAll(
				"input, select, textarea",
			);
			for (const input of inputs) {
				input.value = "";
			}
		}

		// Clear table
		const tbody = document.querySelector("#dataset-file-tree-table tbody");
		if (tbody) {
			tbody.innerHTML = "";
		}

		// Reset statistics
		document.getElementById("total-files-count").textContent = "0";
		document.getElementById("captures-count").textContent = "0";
		document.getElementById("artifacts-count").textContent = "0";
		document.getElementById("total-size").textContent = "0 B";
	}

	/**
	 * Escape HTML to prevent XSS
	 */
	escapeHtml(text) {
		const div = document.createElement("div");
		div.textContent = text;
		return div.innerHTML;
	}

	/**
	 * Get CSRF token
	 */
	getCSRFToken() {
		const token = document.querySelector("[name=csrfmiddlewaretoken]");
		return token ? token.value : "";
	}
}

// Initialize the modal handler when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
	window.datasetDetailsModal = new DatasetDetailsModal();
});
