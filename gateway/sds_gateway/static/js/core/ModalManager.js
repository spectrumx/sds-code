/**
 * Capture detail modal and related API calls.
 * Migrated from deprecated/components.js.
 */

class ModalManager {
	constructor(config) {
		this.modalId = config.modalId;
		this.modal = document.getElementById(this.modalId);
		this.modalTitle = this.modal?.querySelector(".modal-title");
		this.modalBody = this.modal?.querySelector(".modal-body");

		if (this.modal && window.bootstrap) {
			this.bootstrapModal = new bootstrap.Modal(this.modal);
		}
	}

	show(title, content) {
		if (!this.modal) return;

		if (this.modalTitle) {
			this.modalTitle.textContent = title;
		}

		if (this.modalBody) {
			this.modalBody.innerHTML = content;
		}

		if (this.bootstrapModal) {
			this.bootstrapModal.show();
		}
	}

	hide() {
		if (this.bootstrapModal) {
			this.bootstrapModal.hide();
		}
	}

	openCaptureModal(linkElement) {
		if (!linkElement) return;

		try {
			// Reset visualize button to hidden state
			const visualizeBtn = document.getElementById("visualize-btn");
			if (visualizeBtn) {
				visualizeBtn.classList.add("d-none");
			}

			// Get all data attributes from the link with sanitization
			const data = {
				uuid: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-uuid") || "",
				),
				name: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-name") || "",
				),
				channel: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-channel") || "",
				),
				scanGroup: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-scan-group") || "",
				),
				captureType: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-capture-type") || "",
				),
				topLevelDir: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-top-level-dir") || "",
				),
				owner: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-owner") || "",
				),
				origin: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-origin") || "",
				),
				dataset: ComponentUtils.escapeHtml(
					linkElement.getAttribute("data-dataset") || "",
				),
				createdAt: linkElement.getAttribute("data-created-at") || "",
				updatedAt: linkElement.getAttribute("data-updated-at") || "",
				isPublic: linkElement.getAttribute("data-is-public") || "",
				centerFrequencyGhz:
					linkElement.getAttribute("data-center-frequency-ghz") || "",
				isMultiChannel: linkElement.getAttribute("data-is-multi-channel") || "",
				channels: linkElement.getAttribute("data-channels") || "",
			};

			// Parse owner field safely
			const ownerDisplay = data.owner
				? data.owner.split("'").find((part) => part.includes("@")) || "N/A"
				: "N/A";

			// Check if this is a composite capture
			const isComposite =
				data.isMultiChannel === "True" || data.isMultiChannel === "true";

			let modalContent = `
				<div class="mb-4">
					<div class="d-flex align-items-center mb-3">
						<h6 class="mb-0 fw-bold">
							<i class="bi bi-info-circle me-2"></i>Basic Information
						</h6>
					</div>
					<div class="mb-3">
						<label for="capture-name-input" class="form-label fw-medium">
							<strong>Name:</strong>
						</label>
						<div class="input-group">
							<input type="text"
								   class="form-control"
								   id="capture-name-input"
								   value="${data.name || ""}"
								   placeholder="Enter capture name"
								   maxlength="255"
								   data-uuid="${data.uuid}">
							<button class="btn btn-outline-secondary edit-name-btn"
									type="button"
									id="edit-name-btn"
									title="Edit capture name">
								<i class="bi bi-pencil"></i>
							</button>
							<button class="btn btn-outline-danger d-none"
									type="button"
									id="cancel-name-btn"
									title="Cancel editing">
								<i class="bi bi-x-lg"></i>
							</button>
							<button class="btn btn-outline-primary save-name-btn d-none"
									type="button"
									id="save-name-btn"
									title="Save changes">
								<i class="bi bi-check-lg"></i>
							</button>
						</div>
						<div class="form-text">Click the edit button to modify the capture name</div>
					</div>
					<div class="row">
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Capture Type:</span>
								<span class="ms-2">${data.captureType || "N/A"}</span>
							</p>
							<p class="mb-2">
								<span class="fw-medium text-muted">Origin:</span>
								<span class="ms-2">${data.origin || "N/A"}</span>
							</p>
						</div>
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Owner:</span>
								<span class="ms-2">${ownerDisplay}</span>
							</p>
						</div>
					</div>
			`;

			// Handle composite vs single capture display
			if (isComposite) {
				modalContent += `
					<div class="mb-2">
						<span class="fw-medium text-muted">Channels:</span>
						<span class="ms-2">${data.channel || "N/A"}</span>
					</div>
				`;
			} else {
				modalContent += `
					<div class="mb-2">
						<span class="fw-medium text-muted">Channel:</span>
						<span class="ms-2">${data.channel || "N/A"}</span>
					</div>
				`;
			}

			modalContent += `
				</div>
				<div class="mb-4">
					<div class="d-flex align-items-center mb-3">
						<h6 class="mb-0 fw-bold">
							<i class="bi bi-gear me-2"></i>Technical Details
						</h6>
					</div>
					<div class="row">
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Scan Group:</span>
								<span class="ms-2">${data.scanGroup || "N/A"}</span>
							</p>
							<p class="mb-2">
								<span class="fw-medium text-muted">Dataset:</span>
								<span class="ms-2">${data.dataset || "N/A"}</span>
							</p>
							<p class="mb-2">
								<span class="fw-medium text-muted">Is Public:</span>
								<span class="ms-2">${data.isPublic === "True" ? "Yes" : "No"}</span>
							</p>
						</div>
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Top Level Directory:</span>
								<span class="ms-2 text-break">${data.topLevelDir || "N/A"}</span>
							</p>
							<p class="mb-2">
								<span class="fw-medium text-muted">Center Frequency:</span>
								<span class="ms-2">
									${data.centerFrequencyGhz && data.centerFrequencyGhz !== "None" ? `${Number.parseFloat(data.centerFrequencyGhz).toFixed(3)} GHz` : "N/A"}
								</span>
							</p>
						</div>
					</div>
				</div>
				<div class="mb-4">
					<div class="d-flex align-items-center mb-3">
						<h6 class="mb-0 fw-bold">
							<i class="bi bi-clock me-2"></i>Timestamps
						</h6>
					</div>
					<div class="row">
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Created At:</span>
								<br>
								<small class="text-muted">
									${ComponentUtils.formatDateForModal(data.createdAt)}
								</small>
							</p>
						</div>
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Updated At:</span>
								<br>
								<small class="text-muted">
									${ComponentUtils.formatDateForModal(data.updatedAt)}
								</small>
							</p>
						</div>
					</div>
				</div>
				<!-- Files section placeholder -->
				<div id="files-section-placeholder" class="mt-4">
					<div class="d-flex justify-content-center py-3">
						<div class="spinner-border spinner-border-sm me-2" role="status" style="color: #005a9c;">
							<span class="visually-hidden">Loading files...</span>
						</div>
						<span class="text-muted">Loading files...</span>
					</div>
				</div>
			`;

			// Add composite-specific information if available
			if (isComposite && data.channels) {
				try {
					// Convert Python dict syntax to valid JSON
					let channelsData;
					if (typeof data.channels === "string") {
						// Handle Python dict syntax: {'key': 'value'} -> {"key": "value"}
						const pythonDict = data.channels
							.replace(/'/g, '"') // Replace single quotes with double quotes
							.replace(/True/g, "true") // Replace Python True with JSON true
							.replace(/False/g, "false") // Replace Python False with JSON false
							.replace(/None/g, "null"); // Replace Python None with JSON null

						channelsData = JSON.parse(pythonDict);
					} else {
						channelsData = data.channels;
					}

					if (Array.isArray(channelsData) && channelsData.length > 0) {
						modalContent += `
							<div class="mt-4">
								<h6>Channel Details</h6>
								<div class="accordion" id="channelsAccordion">
						`;

						for (let i = 0; i < channelsData.length; i++) {
							const channel = channelsData[i];
							const channelId = `channel-${i}`;

							// Format channel metadata as key-value pairs
							let metadataDisplay = "N/A";
							if (
								channel.channel_metadata &&
								typeof channel.channel_metadata === "object"
							) {
								const metadata = channel.channel_metadata;
								const metadataItems = [];

								// Helper function to format values dynamically
								const formatValue = (value, fieldName = "") => {
									if (value === null || value === undefined) {
										return "N/A";
									}

									if (typeof value === "boolean") {
										return value ? "Yes" : "No";
									}

									// Handle string representations of booleans
									if (typeof value === "string") {
										if (value.toLowerCase() === "true") {
											return "Yes";
										}
										if (value.toLowerCase() === "false") {
											return "No";
										}
									}

									if (typeof value === "number") {
										const absValue = Math.abs(value);
										const valueStr = value.toString();
										const timeIndicators = [
											"computer_time",
											"start_bound",
											"end_bound",
											"init_utc_timestamp",
										];
										// Only format as timestamp if the field name contains "time"
										if (
											timeIndicators.includes(fieldName.toLowerCase()) &&
											valueStr.length >= 10 &&
											valueStr.length <= 13
										) {
											// Convert to milliseconds if it's in seconds
											const timestamp =
												valueStr.length === 10 ? value * 1000 : value;
											return new Date(timestamp).toLocaleString();
										}

										// Only format for Giga (1e9) and Mega (1e6) ranges
										if (absValue >= 1e9) {
											return `${(value / 1e9).toFixed(3)} GHz`;
										}
										if (absValue >= 1e6) {
											return `${(value / 1e6).toFixed(1)} MHz`;
										}
										return value.toString();
									}

									if (Array.isArray(value)) {
										return value
											.map((item) => formatValue(item, fieldName))
											.join(", ");
									}

									if (typeof value === "object") {
										return JSON.stringify(value);
									}

									return String(value);
								};

								// Helper function to format field names
								const formatFieldName = (fieldName) => {
									return fieldName
										.replace(/_/g, " ")
										.replace(/\b\w/g, (l) => l.toUpperCase());
								};

								// Loop through all metadata fields
								if (Object.keys(metadata).length > 0) {
									for (const [key, value] of Object.entries(metadata)) {
										if (value !== undefined && value !== null) {
											const formattedValue = formatValue(value, key);
											const formattedKey = formatFieldName(key);
											metadataItems.push(
												`<strong>${formattedKey}:</strong> ${formattedValue}`,
											);
										}
									}
								} else {
									metadataItems.push("<em>No metadata available</em>");
								}

								if (metadataItems.length > 0) {
									metadataDisplay = metadataItems.join("<br>");
								}
							}

							modalContent += `
								<div class="accordion-item">
									<h2 class="accordion-header" id="heading-${channelId}">
										<button class="accordion-button ${i === 0 ? "" : "collapsed"}" type="button"
												data-bs-toggle="collapse"
												data-bs-target="#collapse-${channelId}"
												aria-expanded="${i === 0 ? "true" : "false"}"
												aria-controls="collapse-${channelId}">
											<strong>${ComponentUtils.escapeHtml(channel.channel || "N/A")}</strong>
											<small class="text-muted ms-2">(Click to expand metadata)</small>
										</button>
									</h2>
									<div id="collapse-${channelId}"
										 class="accordion-collapse collapse ${i === 0 ? "show" : ""}"
										 aria-labelledby="heading-${channelId}"
										 data-bs-parent="#channelsAccordion">
										<div class="accordion-body">
											<div style="max-width: 100%; word-wrap: break-word;">
												${metadataDisplay}
											</div>
										</div>
									</div>
								</div>
							`;
						}

						modalContent += `
								</div>
							</div>
						`;
					}
				} catch (e) {
					console.error("Could not parse channels data for modal:", e);
					console.error(
						"Raw channels data that failed to parse:",
						data.channels,
					);

					// Show a fallback message in the modal
					modalContent += `
						<div class="mt-4">
							<h6>Channel Details</h6>
							<div class="alert alert-warning">
								<i class="fas fa-exclamation-triangle"></i>
								Unable to display channel details due to data format issues.
								<br><small>Raw data: ${ComponentUtils.escapeHtml(String(data.channels).substring(0, 100))}...</small>
							</div>
						</div>
					`;
				}
			}

			const title = data.name
				? data.name
				: data.topLevelDir || "Unnamed Capture";
			this.show(title, modalContent);

			// Store capture data for later use
			this.currentCaptureData = data;

			// Setup name editing handlers after modal content is loaded
			this.setupNameEditingHandlers();

			// Setup visualize button for Digital RF captures
			this.setupVisualizeButton(data);

			// Load and display files for this capture
			this.loadCaptureFiles(data.uuid);
		} catch (error) {
			console.error("Error opening capture modal:", error);
			this.show("Error", "Error displaying capture details");
		}
	}

	/**
	 * Setup visualize button for Digital RF captures
	 */
	setupVisualizeButton(captureData) {
		const visualizeBtn = document.getElementById("visualize-btn");
		if (!visualizeBtn) return;

		// Show button only for Digital RF captures
		if (captureData.captureType === "drf") {
			visualizeBtn.classList.remove("d-none");

			// Set up click handler to open visualization modal
			visualizeBtn.onclick = () => {
				// Use the VisualizationModal instance to open with capture data
				if (window.visualizationModalInstance) {
					window.visualizationModalInstance.openWithCaptureData(
						captureData.uuid,
						captureData.captureType,
					);
				}
			};
		} else {
			visualizeBtn.classList.add("d-none");
		}
	}

	/**
	 * Setup handlers for name editing functionality
	 */
	setupNameEditingHandlers() {
		const nameInput = document.getElementById("capture-name-input");
		const editBtn = document.getElementById("edit-name-btn");
		const saveBtn = document.getElementById("save-name-btn");
		const cancelBtn = document.getElementById("cancel-name-btn");

		if (!nameInput || !editBtn || !saveBtn || !cancelBtn) return;

		// Initially disable the input
		nameInput.disabled = true;
		let originalName = nameInput.value;
		let isEditing = false;

		const startEditing = () => {
			nameInput.disabled = false;
			nameInput.focus();
			nameInput.select();
			editBtn.classList.add("d-none");
			saveBtn.classList.remove("d-none");
			cancelBtn.classList.remove("d-none");
			isEditing = true;
		};

		const stopEditing = () => {
			nameInput.disabled = true;
			editBtn.classList.remove("d-none");
			saveBtn.classList.add("d-none");
			cancelBtn.classList.add("d-none");
			isEditing = false;
		};

		const cancelEditing = () => {
			nameInput.value = originalName;
			stopEditing();
		};

		// Edit button handler
		editBtn.addEventListener("click", () => {
			if (!isEditing) {
				startEditing();
			}
		});

		// Cancel button handler
		cancelBtn.addEventListener("click", cancelEditing);

		// Save button handler
		saveBtn.addEventListener("click", async () => {
			const newName = nameInput.value.trim();
			const uuid = nameInput.getAttribute("data-uuid");

			if (!uuid) {
				console.error("No UUID found for capture");
				return;
			}

			// Disable buttons during save
			editBtn.disabled = true;
			saveBtn.disabled = true;
			cancelBtn.disabled = true;
			saveBtn.innerHTML =
				'<span class="spinner-border spinner-border-sm"></span>';

			try {
				await this.updateCaptureName(uuid, newName);

				// Success - update UI
				originalName = newName;
				stopEditing();

				// Update the table display
				this.updateTableNameDisplay(uuid, newName);

				// Update modal title using stored capture data
				if (this.modalTitle && this.currentCaptureData) {
					this.currentCaptureData.name = newName;
					this.modalTitle.textContent =
						newName || this.currentCaptureData.topLevelDir || "Unnamed Capture";
				}

				// Show success message
				this.showSuccessMessage("Capture name updated successfully!");
			} catch (error) {
				console.error("Error updating capture name:", error);
				this.showErrorMessage(
					"Failed to update capture name. Please try again.",
				);
				// Revert to original name
				nameInput.value = originalName;
			} finally {
				// Re-enable buttons and restore icons
				editBtn.disabled = false;
				saveBtn.disabled = false;
				cancelBtn.disabled = false;
				saveBtn.innerHTML = '<i class="bi bi-check-lg"></i>';
			}
		});

		// Handle Enter key to save
		nameInput.addEventListener("keypress", (e) => {
			if (e.key === "Enter" && !nameInput.disabled) {
				saveBtn.click();
			}
		});

		// Handle Escape key to cancel
		nameInput.addEventListener("keydown", (e) => {
			if (e.key === "Escape" && !nameInput.disabled) {
				cancelEditing();
			}
		});
	}

	/**
	 * Update capture name via API
	 */
	async updateCaptureName(uuid, newName) {
		const response = await fetch(`/api/v1/assets/captures/${uuid}/`, {
			method: "PATCH",
			headers: {
				"Content-Type": "application/json",
				"X-CSRFToken": this.getCSRFToken(),
			},
			body: JSON.stringify({ name: newName }),
		});

		if (!response.ok) {
			const errorData = await response.json();
			throw new Error(errorData.detail || "Failed to update capture name");
		}

		return response.json();
	}

	/**
	 * Update the table display with the new name
	 */
	updateTableNameDisplay(uuid, newName) {
		// Find all elements with this UUID and update their display
		const captureLinks = document.querySelectorAll(`[data-uuid="${uuid}"]`);

		for (const link of captureLinks) {
			// Update data attribute
			link.dataset.name = newName;

			// Update display text if it's a capture link
			if (link.classList.contains("capture-link")) {
				link.textContent = newName || "Unnamed Capture";
				link.setAttribute(
					"aria-label",
					`View details for capture ${newName || uuid}`,
				);
				link.setAttribute("title", `View capture details: ${newName || uuid}`);
			}
		}
	}

	/**
	 * Clear existing alert messages from the modal
	 */
	clearAlerts() {
		const modalBody = document.getElementById("capture-modal-body");
		if (modalBody) {
			const existingAlerts = modalBody.querySelectorAll(".alert");
			for (const alert of existingAlerts) {
				alert.remove();
			}
		}
	}

	/**
	 * Show success message
	 */
	showSuccessMessage(message) {
		// Clear existing alerts first
		this.clearAlerts();

		// Create a temporary alert
		const alert = document.createElement("div");
		alert.className = "alert alert-success alert-dismissible fade show";
		alert.innerHTML = `
			${message}
			<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
		`;

		// Insert at the top of the modal body
		const modalBody = document.getElementById("capture-modal-body");
		if (modalBody) {
			modalBody.insertBefore(alert, modalBody.firstChild);

			// Auto-dismiss after 3 seconds
			setTimeout(() => {
				if (alert.parentNode) {
					alert.remove();
				}
			}, 3000);
		}
	}

	/**
	 * Show error message
	 */
	showErrorMessage(message) {
		// Clear existing alerts first
		this.clearAlerts();

		// Create a temporary alert
		const alert = document.createElement("div");
		alert.className = "alert alert-danger alert-dismissible fade show";
		alert.innerHTML = `
			${message}
			<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
		`;

		// Insert at the top of the modal body
		const modalBody = document.getElementById("capture-modal-body");
		if (modalBody) {
			modalBody.insertBefore(alert, modalBody.firstChild);

			// Auto-dismiss after 5 seconds
			setTimeout(() => {
				if (alert.parentNode) {
					alert.remove();
				}
			}, 5000);
		}
	}

	/**
	 * Load and display files associated with the capture
	 */
	async loadCaptureFiles(captureUuid) {
		try {
			const response = await fetch(`/api/v1/assets/captures/${captureUuid}/`, {
				method: "GET",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": this.getCSRFToken(),
				},
			});

			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}

			const captureData = await response.json();
			console.log("Raw capture data:", captureData);

			const files = captureData.files || [];
			const filesCount = captureData.files_count || 0;
			const totalSize = captureData.total_file_size || 0;

			console.log("Files info:", {
				filesCount,
				totalSize,
				numFiles: files.length,
			});

			// Update files section with simple summary
			const filesSection = document.getElementById("files-section-placeholder");
			if (filesSection) {
				filesSection.innerHTML = `
					<div class="row">
						<div class="col-12">
							<h6 class="mb-3">
								<i class="bi bi-files me-2"></i>Files Summary
							</h6>
						</div>
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Number of Files:</span>
								<span class="ms-2">${filesCount}</span>
							</p>
						</div>
						<div class="col-md-6">
							<p class="mb-2">
								<span class="fw-medium text-muted">Total Size:</span>
								<span class="ms-2">${window.DOMUtils.formatFileSize(totalSize)}</span>
							</p>
						</div>
					</div>
				`;
			}
		} catch (error) {
			console.error("Error loading capture files:", error);
			const filesSection = document.getElementById("files-section-placeholder");
			if (filesSection) {
				filesSection.innerHTML = `
					<div class="alert alert-warning">
						<i class="bi bi-exclamation-triangle me-2"></i>
						Error loading files information
					</div>
				`;
			}
		}
	}

	/**
	 * Format file metadata for display
	 */
	formatFileMetadata(file) {
		const metadata = [];

		// Primary file information - most useful for users
		if (file.size) {
			metadata.push(
				`<strong>Size:</strong> ${window.DOMUtils.formatFileSize(file.size)} (${file.size.toLocaleString()} bytes)`,
			);
		}

		if (file.media_type) {
			metadata.push(
				`<strong>Media Type:</strong> ${ComponentUtils.escapeHtml(file.media_type)}`,
			);
		}

		if (file.created_at) {
			metadata.push(`<strong>Created:</strong> ${file.created_at}`);
		}

		if (file.updated_at) {
			metadata.push(`<strong>Updated:</strong> ${file.updated_at}`);
		}

		// File properties and attributes
		if (file.name) {
			metadata.push(
				`<strong>Name:</strong> ${ComponentUtils.escapeHtml(file.name)}`,
			);
		}

		if (file.directory || file.relative_path) {
			metadata.push(
				`<strong>Directory:</strong> ${ComponentUtils.escapeHtml(file.directory || file.relative_path)}`,
			);
		}

		// Removed permissions display
		// if (file.permissions) {
		// 	metadata.push(`<strong>Permissions:</strong> <span style="color: #005a9c; font-family: monospace;">${ComponentUtils.escapeHtml(file.permissions)}</span>`);
		// }

		if (file.owner?.username) {
			metadata.push(
				`<strong>Owner:</strong> ${ComponentUtils.escapeHtml(file.owner.username)}`,
			);
		}

		if (file.expiration_date) {
			metadata.push(
				`<strong>Expires:</strong> ${new Date(file.expiration_date).toLocaleDateString()}`,
			);
		}

		if (file.bucket_name) {
			metadata.push(
				`<strong>Storage Bucket:</strong> ${ComponentUtils.escapeHtml(file.bucket_name)}`,
			);
		}

		// Removed checksum display
		// if (file.sum_blake3) {
		// 	metadata.push(`<strong>Checksum:</strong> <span style="color: #005a9c; font-family: monospace;">${ComponentUtils.escapeHtml(file.sum_blake3)}</span>`);
		// }

		// Associated resources
		// TODO: Refactor this to handle multiple associations
		if (file.capture?.name) {
			metadata.push(
				`<strong>Associated Capture:</strong> ${ComponentUtils.escapeHtml(file.capture.name)}`,
			);
		}

		if (file.dataset?.name) {
			metadata.push(
				`<strong>Associated Dataset:</strong> ${ComponentUtils.escapeHtml(file.dataset.name)}`,
			);
		}

		// Additional metadata if available
		if (file.metadata && typeof file.metadata === "object") {
			for (const [key, value] of Object.entries(file.metadata)) {
				if (value !== null && value !== undefined) {
					const formattedKey = key
						.replace(/_/g, " ")
						.replace(/\b\w/g, (l) => l.toUpperCase());
					let formattedValue;

					// Format different types of values
					if (typeof value === "boolean") {
						formattedValue = value ? "Yes" : "No";
					} else if (typeof value === "number") {
						formattedValue = value.toLocaleString();
					} else if (typeof value === "object") {
						formattedValue = `<span style="color: #005a9c; font-family: monospace;">${JSON.stringify(value, null, 2)}</span>`;
					} else {
						formattedValue = ComponentUtils.escapeHtml(String(value));
					}

					metadata.push(`<strong>${formattedKey}:</strong> ${formattedValue}`);
				}
			}
		}

		if (metadata.length === 0) {
			return '<p class="text-muted mb-0">No metadata available for this file.</p>';
		}

		return `<div class="metadata-list">${metadata.join("<br>")}</div>`;
	}

	/**
	 * Get CSRF token for API requests
	 */
	getCSRFToken() {
		if (window.APIClient) {
			try {
				return new window.APIClient().getCSRFToken();
			} catch (_) {}
		}
		const token = document.querySelector("[name=csrfmiddlewaretoken]");
		return token ? token.value : "";
	}

	/**
	 * Load and display file metadata for a specific file in the modal
	 */
	async loadFileMetadata(fileUuid, fileName) {
		const fileMetadataSection = document.getElementById(
			`file-metadata-${fileUuid}`,
		);
		const metadataContent =
			fileMetadataSection?.querySelector(".metadata-content");

		if (!fileMetadataSection || !metadataContent) return;

		// Toggle visibility
		if (fileMetadataSection.style.display === "none") {
			fileMetadataSection.style.display = "block";

			// Check if metadata is already loaded
			if (metadataContent.innerHTML.includes("Click to load metadata...")) {
				// Show loading state
				metadataContent.innerHTML = `
					<div class="d-flex justify-content-center py-2">
						<div class="spinner-border spinner-border-sm me-2" role="status">
							<span class="visually-hidden">Loading...</span>
						</div>
						<span class="text-muted">Loading metadata...</span>
					</div>
				`;

				try {
					const response = await fetch(`/api/v1/assets/files/${fileUuid}/`, {
						method: "GET",
						headers: {
							"Content-Type": "application/json",
							"X-CSRFToken": this.getCSRFToken(),
						},
					});

					if (!response.ok) {
						throw new Error(`HTTP error! status: ${response.status}`);
					}

					const fileData = await response.json();

					// Format and display the metadata
					const formattedMetadata = this.formatFileMetadata(fileData);
					metadataContent.innerHTML = formattedMetadata;
				} catch (error) {
					console.error("Error loading file metadata:", error);
					metadataContent.innerHTML = `
						<div class="alert alert-warning mb-0">
							<i class="bi bi-exclamation-triangle me-2"></i>
							Failed to load metadata for ${ComponentUtils.escapeHtml(fileName)}.
							<br><small>Error: ${ComponentUtils.escapeHtml(error.message)}</small>
						</div>
					`;
				}
			}
		} else {
			fileMetadataSection.style.display = "none";
		}
	}
}

if (typeof window !== "undefined") {
	window.ModalManager = ModalManager;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { ModalManager };
}

