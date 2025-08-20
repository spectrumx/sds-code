class FileManager {
	constructor() {
		// Check browser compatibility before proceeding
		if (!this.checkBrowserSupport()) {
			this.showError(
				"Your browser doesn't support required features. Please use a modern browser.",
				null,
				"browser-compatibility",
			);
			return;
		}

		this.droppedFiles = null;
		this.boundHandlers = new Map(); // Track bound event handlers for cleanup
		this.activeModals = new Set(); // Track active modals

		// Prevent browser from navigating away when user drags files over the whole window
		this.addGlobalDropGuards();
		this.init();
	}

	addGlobalDropGuards() {
		// Prevent browser navigation on any drop event
		document.addEventListener(
			"dragover",
			(e) => {
				e.preventDefault();
			},
			false,
		);

		document.addEventListener(
			"drop",
			(e) => {
				e.preventDefault();
				e.stopPropagation();

				// Always handle global drops for testing
				this.handleGlobalDrop(e);
			},
			false,
		);
	}

	async handleGlobalDrop(e) {
		const dt = e.dataTransfer;
		if (!dt) {
			console.warn("No dataTransfer in global drop");
			return;
		}

		const files = await this.collectFilesFromDataTransfer(dt);

		if (!files.length) {
			console.warn("No files collected from global drop");
			return;
		}

		// Store the dropped files globally
		window.selectedFiles = files;

		// Open the upload modal
		const uploadModalEl = document.getElementById("uploadCaptureModal");
		if (!uploadModalEl) {
			console.error("Upload modal element not found");
			return;
		}

		const uploadModal = new bootstrap.Modal(uploadModalEl);
		uploadModal.show();

		// Wait a bit for modal to fully open, then trigger file selection
		setTimeout(() => {
			this.handleGlobalFilesInModal(files);
		}, 200);
	}

	handleGlobalFilesInModal(files) {
		// Update the file input to show selected files
		const fileInput = document.getElementById("captureFileInput");
		if (fileInput) {
			// Create a new FileList-like object
			const dataTransfer = new DataTransfer();
			for (const file of files) {
				dataTransfer.items.add(file);
			}
			fileInput.files = dataTransfer.files;
		}

		// Update the selected files display
		this.handleFileSelection(files);

		// Make sure the selected files section is visible
		const selectedFilesSection = document.getElementById("selectedFiles");
		if (selectedFilesSection) {
			selectedFilesSection.classList.add("has-files");
		}

		// Update the file input label to show selected files
		const fileInputLabel = fileInput?.nextElementSibling;
		if (fileInputLabel?.classList.contains("form-control")) {
			const fileNames = files
				.map((f) => f.webkitRelativePath || f.name)
				.join(", ");
			fileInputLabel.textContent = fileNames || "No directory selected.";
		}
	}

	convertToFiles(itemsOrFiles) {
		if (!itemsOrFiles) return [];
		// DataTransferItemList detection: items have getAsFile()
		const first = itemsOrFiles[0];
		if (first && typeof first.getAsFile === "function") {
			return Array.from(itemsOrFiles)
				.map((item) => item.getAsFile())
				.filter((f) => !!f);
		}
		return Array.from(itemsOrFiles);
	}

	// Collect files from a directory or mixed drop using the File System API (Chrome/WebKit)
	async collectFilesFromDataTransfer(dataTransfer) {
		const items = Array.from(dataTransfer.items || []);
		const supportsEntries =
			items.length > 0 && typeof items[0].webkitGetAsEntry === "function";
		if (!supportsEntries) {
			return this.convertToFiles(
				dataTransfer.files?.length ? dataTransfer.files : dataTransfer.items,
			);
		}

		const allFiles = [];
		for (const item of items) {
			if (item.kind !== "file") continue;
			const entry = item.webkitGetAsEntry();
			if (!entry) continue;
			const files = await this.traverseEntry(entry);
			allFiles.push(...files);
		}
		return allFiles;
	}

	async traverseEntry(entry) {
		if (entry.isFile) {
			return new Promise((resolve) => {
				entry.file((file) => {
					// Preserve folder structure on drop by injecting webkitRelativePath
					try {
						const relative = (entry.fullPath || file.name).replace(/^\//, "");
						Object.defineProperty(file, "webkitRelativePath", {
							value: relative,
							configurable: true,
						});
					} catch (_) {}
					resolve([file]);
				});
			});
		}

		if (entry.isDirectory) {
			const reader = entry.createReader();
			const entries = await this.readAllEntries(reader);
			const nestedFiles = [];
			for (const child of entries) {
				const files = await this.traverseEntry(child);
				nestedFiles.push(...files);
			}
			return nestedFiles;
		}

		return [];
	}

	readAllEntries(reader) {
		return new Promise((resolve) => {
			const entries = [];
			const readChunk = () => {
				reader.readEntries((results) => {
					if (!results.length) {
						resolve(entries);
						return;
					}
					entries.push(...results);
					readChunk();
				});
			};
			readChunk();
		});
	}

	stripHtml(html) {
		if (!html) return "";
		const div = document.createElement("div");
		div.innerHTML = html;
		return (div.textContent || div.innerText || "").trim();
	}

	init() {
		// Get container and data
		this.container = document.querySelector(".files-container");
		if (!this.container) {
			this.showError("Files container not found", null, "initialization");
			return;
		}

		// Get data attributes
		this.currentDir = this.container.dataset.currentDir;
		this.userEmail = this.container.dataset.userEmail;

		// Get all file cards for data
		const fileCards = document.querySelectorAll(".file-card:not(.header)");
		const items = Array.from(fileCards).map((card) => ({
			type: card.dataset.type,
			name: card.querySelector(".file-name").textContent,
			path: card.dataset.path,
			uuid: card.dataset.uuid,
			is_capture: card.dataset.isCapture === "true",

			is_shared: card.dataset.isShared === "true",
			capture_uuid: card.dataset.captureUuid,
			description: card.dataset.description,
			modified_at: card.querySelector(".file-meta").textContent.trim(),
			shared_by: card.querySelector(".file-shared").textContent.trim(),
		}));

		// Get dataset options
		const datasetSelect = document.getElementById("datasetSelect");
		const datasets = datasetSelect
			? Array.from(datasetSelect.options)
					.slice(1)
					.map((opt) => ({
						name: opt.text,
						uuid: opt.value,
					}))
			: [];

		// Initialize all handlers
		this.initializeEventListeners();
		this.initializeUploadHandlers();
		this.initializeFileClicks();
	}

	initializeEventListeners() {
		const fileCards = document.querySelectorAll(".file-card");

		for (const card of fileCards) {
			if (!card.classList.contains("header")) {
				const type = card.dataset.type;
				// Add click handlers to directories and files
				card.addEventListener("click", (e) =>
					this.handleFileCardClick(e, card),
				);
				// Basic keyboard accessibility
				card.setAttribute("tabindex", "0");
				card.addEventListener("keydown", (e) => {
					if (e.key === "Enter" || e.key === " ") {
						e.preventDefault();
						this.handleFileCardClick(e, card);
					}
				});

				if (type === "directory") {
					card.style.cursor = "pointer";
					card.classList.add("clickable-directory");
				} else if (type === "file") {
					card.style.cursor = "pointer";
					card.classList.add("clickable-file");
				}
			}
		}
	}

	initializeUploadHandlers() {
		// Initialize capture upload
		const captureElements = {
			uploadZone: document.getElementById("uploadZone"),
			fileInput: document.getElementById("captureFileInput"),
			// browseButton is optional in Files modal styling
			browseButton: document.querySelector(
				"#uploadCaptureModal .browse-button",
			),
			selectedFilesList: document.getElementById("selectedFilesList"),
			uploadForm: document.getElementById("uploadCaptureForm"),
		};

		// Only require the essentials; browseButton may be missing
		const essentials = [
			captureElements.uploadZone,
			captureElements.fileInput,
			captureElements.selectedFilesList,
			captureElements.uploadForm,
		];
		// Skip initialization if we're on the files page which has its own custom handler
		const isFilesPage = window.location.pathname.includes("/users/files/");
		if (essentials.every((el) => el) && !isFilesPage) {
			this.initializeCaptureUpload(captureElements);
		}

		// Initialize text file upload
		const textUploadForm = document.getElementById("uploadFileForm");
		if (textUploadForm) {
			this.initializeTextFileUpload(textUploadForm);
		}
	}

	initializeCaptureUpload(elements) {
		const {
			uploadZone,
			fileInput,
			browseButton,
			selectedFilesList,
			uploadForm,
		} = elements;

		if (!uploadZone || !fileInput || !selectedFilesList || !uploadForm) {
			this.showError(
				"Upload elements not found",
				null,
				"upload-initialization",
			);
			return;
		}

		// Handle browse button click (if present)
		if (browseButton) {
			browseButton.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();
				fileInput.click();
			});
		}

		// Handle drag and drop
		uploadZone.addEventListener("dragover", (e) => {
			e.preventDefault();
			uploadZone.classList.add("drag-over");
		});

		uploadZone.addEventListener("dragleave", () => {
			uploadZone.classList.remove("drag-over");
		});

		uploadZone.addEventListener("drop", async (e) => {
			e.preventDefault();
			uploadZone.classList.remove("drag-over");
			const dt = e.dataTransfer;
			if (dt) {
				const files = await this.collectFilesFromDataTransfer(dt);
				this.droppedFiles = files;
				// Clear any existing input selection so we rely on dropped files on submit
				try {
					fileInput.value = "";
				} catch (_) {}
				this.handleFileSelection(files);
			}
		});

		// Handle file input change
		fileInput.addEventListener("change", (e) => {
			this.droppedFiles = null; // prefer explicit file input selection
			this.handleFileSelection(this.convertToFiles(e.target.files));
		});

		// Toggle DRF/RH input groups
		const typeSelect = document.getElementById("captureTypeSelect");
		const channelGroup = document.getElementById("channelInputGroup");
		const scanGroup = document.getElementById("scanGroupInputGroup");
		const channelInput = document.getElementById("captureChannelsInput");

		if (typeSelect) {
			typeSelect.addEventListener("change", () => {
				const v = typeSelect.value;

				// Use Bootstrap classes instead of inline styles
				if (channelGroup) {
					if (v === "drf") {
						channelGroup.classList.remove("d-none");
						channelGroup.style.display = "";
					} else {
						channelGroup.classList.add("d-none");
					}
				}

				if (scanGroup) {
					if (v === "rh") {
						scanGroup.classList.remove("d-none");
						scanGroup.style.display = "";
					} else {
						scanGroup.classList.add("d-none");
					}
				}

				if (channelInput) {
					if (v === "drf") {
						channelInput.setAttribute("required", "required");
					} else {
						channelInput.removeAttribute("required");
					}
				}
			});

			// Trigger change event to set initial state
			typeSelect.dispatchEvent(new Event("change"));
		}

		// Check for globally dropped files when modal opens
		if (window.selectedFiles?.length) {
			this.handleFileSelection(window.selectedFiles);
		}

		// Handle form submission
		uploadForm.addEventListener("submit", async (e) => {
			e.preventDefault();

			const formData = new FormData();
			const submitBtn = uploadForm.querySelector('button[type="submit"]');
			const uploadText = submitBtn.querySelector(".upload-text");
			const uploadSpinner = submitBtn.querySelector(".upload-spinner");

			try {
				submitBtn.disabled = true;
				uploadText.classList.add("d-none");
				uploadSpinner.classList.remove("d-none");

				// Get CSRF token and add it when present
				const csrfToken = this.getCsrfToken();
				if (csrfToken) {
					formData.append("csrfmiddlewaretoken", csrfToken);
				}

				// Add capture type and channels from the form
				const captureType = document.getElementById("captureTypeSelect").value;
				const channels =
					document.getElementById("captureChannelsInput")?.value || "";
				const scanGroupVal =
					document.getElementById("captureScanGroupInput")?.value || "";
				formData.append("capture_type", captureType);
				formData.append("channels", channels);
				if (captureType === "rh" && scanGroupVal) {
					formData.append("scan_group", scanGroupVal);
				}

				// Add files and their relative paths - check for globally dropped files first
				const files = window.selectedFiles?.length
					? Array.from(window.selectedFiles)
					: this.droppedFiles?.length
						? Array.from(this.droppedFiles)
						: Array.from(fileInput.files);

				// Create an array of relative paths in the same order as files
				const relativePaths = files.map(
					(file) => file.webkitRelativePath || file.name,
				);

				// Add each file
				for (const [index, file] of files.entries()) {
					formData.append("files", file);
					formData.append("relative_paths", relativePaths[index]);
				}

				await this.handleUpload(formData, submitBtn, "uploadCaptureModal", {
					files,
				});
			} catch (error) {
				const userMessage = this.getUserFriendlyErrorMessage(
					error,
					"capture-upload",
				);
				this.showError(
					`Upload failed: ${userMessage}`,
					error,
					"capture-upload",
				);
			} finally {
				submitBtn.disabled = false;
				uploadText.classList.remove("d-none");
				uploadSpinner.classList.add("d-none");
				this.droppedFiles = null;
				window.selectedFiles = null; // Clear global files after upload
			}
		});
	}

	initializeTextFileUpload(uploadForm) {
		uploadForm.addEventListener("submit", async (e) => {
			e.preventDefault();

			const formData = new FormData(uploadForm);
			const submitBtn = uploadForm.querySelector('button[type="submit"]');
			const uploadText = submitBtn.querySelector(".upload-text");
			const uploadSpinner = submitBtn.querySelector(".upload-spinner");

			try {
				submitBtn.disabled = true;
				uploadText.classList.add("d-none");
				uploadSpinner.classList.remove("d-none");

				// CSRF token attached in handleUpload

				await this.handleUpload(formData, submitBtn, "uploadFileModal");
			} catch (error) {
				const userMessage = this.getUserFriendlyErrorMessage(
					error,
					"text-upload",
				);
				this.showError(`Upload failed: ${userMessage}`, error, "text-upload");
			} finally {
				submitBtn.disabled = false;
				uploadText.classList.remove("d-none");
				uploadSpinner.classList.add("d-none");
			}
		});
	}

	initializeFileClicks() {
		// Wire up download confirmation for dataset and capture buttons
		document.addEventListener("click", (e) => {
			if (
				e.target.matches(".download-capture-btn") ||
				e.target.closest(".download-capture-btn")
			) {
				e.preventDefault();
				e.stopPropagation();
				const btn = e.target.matches(".download-capture-btn")
					? e.target
					: e.target.closest(".download-capture-btn");
				const captureUuid = btn.dataset.captureUuid;
				const captureName = btn.dataset.captureName || captureUuid;

				// Validate UUID before proceeding
				if (!this.isValidUuid(captureUuid)) {
					console.warn("Invalid capture UUID:", captureUuid);
					this.showError("Invalid capture identifier", null, "download");
					return;
				}

				// Validate UUID before proceeding
				if (!this.isValidUuid(captureUuid)) {
					console.warn("Invalid capture UUID:", captureUuid);
					this.showError("Invalid capture identifier", null, "download");
					return;
				}

				// Update modal text
				const nameEl = document.getElementById("downloadCaptureName");
				if (nameEl) nameEl.textContent = captureName;

				// Show modal using helper method
				this.openModal("downloadModal");

				// Confirm handler
				const confirmBtn = document.getElementById("confirmDownloadBtn");
				if (confirmBtn) {
					const onConfirm = () => {
						this.closeModal("downloadModal");

						// Use unified download handler if available
						if (window.components?.handleDownload) {
							const dummyButton = document.createElement("button");
							dummyButton.style.display = "none";
							window.components.handleDownload(
								"capture",
								captureUuid,
								dummyButton,
							);
						}
					};
					confirmBtn.addEventListener("click", onConfirm, { once: true });
				}
			}

			if (
				e.target.matches(".download-dataset-btn") ||
				e.target.closest(".download-dataset-btn")
			) {
				e.preventDefault();
				e.stopPropagation();
				const btn = e.target.matches(".download-dataset-btn")
					? e.target
					: e.target.closest(".download-dataset-btn");
				const datasetUuid = btn.dataset.datasetUuid;

				// Validate UUID before proceeding
				if (!this.isValidUuid(datasetUuid)) {
					console.warn("Invalid dataset UUID:", datasetUuid);
					this.showError("Invalid dataset identifier", null, "download");
					return;
				}
				// Show modal using helper method
				this.openModal("downloadModal");
				const confirmBtn = document.getElementById("confirmDownloadBtn");
				if (confirmBtn) {
					const onConfirm = () => {
						this.closeModal("downloadModal");
						fetch(
							`/users/download-item/dataset/${encodeURIComponent(datasetUuid)}/`,
							{
								method: "POST",
								headers: {
									"Content-Type": "application/json",
									"X-CSRFToken": this.getCsrfToken(),
								},
							},
						)
							.then(async (r) => {
								try {
									return await r.json();
								} catch (_) {
									return {};
								}
							})
							.catch(() => {});
					};
					confirmBtn.addEventListener("click", onConfirm, { once: true });
				}
			}

			// Single file direct download link (GET)
			const fileDownloadLink =
				e.target.closest(
					'a.dropdown-item[href^="/users/files/"][href$="/download/"]',
				) ||
				e.target.closest(
					'.dropdown-menu a[href^="/users/files/"][href$="/download/"]',
				) ||
				e.target.closest('a[href^="/users/files/"][href$="/download/"]');
			if (fileDownloadLink) {
				e.preventDefault();
				e.stopPropagation();
				const card = fileDownloadLink.closest(".file-card");
				const fileName =
					card?.querySelector(".file-name")?.textContent?.trim() || "File";
				// Use helper method to show success message
				this.showSuccessMessage(`Download starting: ${fileName}`);
				const href = fileDownloadLink.getAttribute("href");
				try {
					window.open(href, "_blank");
				} catch (_) {
					window.location.href = href;
				}
				return;
			}
		});
	}

	async handleUpload(formData, submitBtn, modalId, options = {}) {
		const uploadText = submitBtn.querySelector(".upload-text");
		const uploadSpinner = submitBtn.querySelector(".upload-spinner");

		try {
			// Update UI
			submitBtn.disabled = true;
			uploadText.classList.add("d-none");
			uploadSpinner.classList.remove("d-none");

			// Make request with progress (XHR for upload progress events)
			const response = await new Promise((resolve, reject) => {
				const xhr = new XMLHttpRequest();
				xhr.open("POST", "/users/upload-files/");
				xhr.withCredentials = true;
				xhr.setRequestHeader("X-CSRFToken", this.getCsrfToken());
				xhr.setRequestHeader("Accept", "application/json");

				// Progress UI elements + smoothing state
				const wrap = document.getElementById("captureUploadProgressWrap");
				const bar = document.getElementById("captureUploadProgressBar");
				const text = document.getElementById("captureUploadProgressText");
				if (wrap) wrap.classList.remove("d-none");
				if (bar) {
					bar.classList.add("progress-bar-striped", "progress-bar-animated");
					bar.style.width = "100%";
					bar.setAttribute("aria-valuenow", "100");
					bar.textContent = "";
				}
				if (text) text.textContent = "Uploading…";

				xhr.upload.onprogress = () => {
					// Keep indeterminate to match button spinner timing (no file count)
					if (text) text.textContent = "Uploading…";
				};

				xhr.onerror = () => reject(new Error("Network error during upload"));
				xhr.upload.onloadstart = () => {
					if (text) text.textContent = "Starting upload…";
				};
				xhr.upload.onloadend = () => {
					if (bar) {
						bar.classList.add("progress-bar-striped", "progress-bar-animated");
						bar.style.width = "100%";
						bar.setAttribute("aria-valuenow", "100");
						bar.textContent = "";
					}
					if (text) text.textContent = "Processing on server…";
				};
				xhr.onload = () => {
					// Build a Response-like object compatible with existing code
					const status = xhr.status;
					const headers = new Headers({
						"content-type": xhr.getResponseHeader("content-type") || "",
					});
					const bodyText = xhr.responseText || "";
					const responseLike = {
						ok: status >= 200 && status < 300,
						status,
						headers,
						json: async () => {
							try {
								return JSON.parse(bodyText);
							} catch {
								return {};
							}
						},
						text: async () => bodyText,
					};
					resolve(responseLike);
				};

				xhr.send(formData);
			});

			let result = null;
			let fallbackText = "";
			try {
				const contentType = response.headers.get("content-type") || "";
				if (contentType.includes("application/json")) {
					result = await response.json();
				} else {
					fallbackText = await response.text();
				}
			} catch (_) {}

			if (response.ok) {
				// Build a concise success message for inline banner
				let successMessage = "Upload complete.";
				if (result && (result.files_uploaded || result.total_files)) {
					const uploaded = result.files_uploaded ?? result.total_uploaded ?? 0;
					const total = result.total_files ?? result.total_uploaded ?? 0;
					successMessage = `Upload complete: ${uploaded} / ${total} file${total === 1 ? "" : "s"} uploaded.`;
					if (Array.isArray(result.errors) && result.errors.length) {
						successMessage += " Some items were skipped or failed.";
					}
				}
				try {
					sessionStorage.setItem(
						"filesAlert",
						JSON.stringify({
							message: successMessage,
							type: "success",
						}),
					);
				} catch (_) {}
				// Reload to show inline banner on main page
				window.location.reload();
			} else {
				let message = "";
				if (result && (result.detail || result.error || result.message)) {
					message = result.detail || result.error || result.message;
				} else if (fallbackText) {
					message = this.stripHtml(fallbackText)
						.split("\n")
						.slice(0, 3)
						.join(" ");
				}
				if (!message) message = `Upload failed (${response.status})`;
				// Friendly mapping for common statuses
				if (response.status === 409) {
					message =
						"Upload skipped: a file with the same checksum already exists. Use PATCH to replace, or change the file.";
				}
				throw new Error(message);
			}
		} catch (error) {
			const userMessage = this.getUserFriendlyErrorMessage(
				error,
				"upload-handler",
			);
			try {
				sessionStorage.setItem(
					"filesAlert",
					JSON.stringify({
						message: `Upload failed: ${userMessage}`,
						type: "error",
					}),
				);
				// Reload to display the banner via template startup script
				window.location.reload();
			} catch (_) {
				this.showError(
					`Upload failed: ${userMessage}`,
					error,
					"upload-handler",
				);
			}
		} finally {
			// Reset UI
			submitBtn.disabled = false;
			uploadText.classList.remove("d-none");
			uploadSpinner.classList.add("d-none");
		}
	}

	showUploadSuccess(result, modalId) {
		const resultModal = new bootstrap.Modal(
			document.getElementById("uploadResultModal"),
		);
		const resultBody = document.getElementById("uploadResultModalBody");

		resultBody.innerHTML = `
            <div class="alert alert-success">
              <h6>Upload Complete!</h6>
        ${
					result.files_uploaded
						? `<p>Files uploaded: ${result.files_uploaded} / ${result.total_files}</p>`
						: "<p>File uploaded successfully!</p>"
				}
              ${result.errors ? `<p>Errors: ${result.errors.join("<br>")}</p>` : ""}
            </div>
          `;

		// Close upload modal and show result (guard instance)
		const uploadModalEl = document.getElementById(modalId);
		const uploadModalInstance = uploadModalEl
			? bootstrap.Modal.getInstance(uploadModalEl)
			: null;
		if (uploadModalInstance) {
			uploadModalInstance.hide();
		}
		resultModal.show();
	}

	// File preview methods
	async showTextFilePreview(fileUuid, fileName) {
		try {
			// Check if this is a file we should preview
			if (!this.shouldPreviewFile(fileName)) {
				this.showError("This file type cannot be previewed");
				return;
			}

			const content = await this.fetchFileContent(fileUuid);
			this.showPreviewModal(fileName, content);
		} catch (error) {
			if (error.message === "File too large to preview") {
				this.showError(
					"File is too large to preview. Please download it instead.",
					error,
					"file-preview",
				);
			} else {
				const userMessage = this.getUserFriendlyErrorMessage(
					error,
					"file-preview",
				);
				this.showError(userMessage, error, "file-preview");
			}
		}
	}

	shouldPreviewFile(fileName) {
		const extension = this.getFileExtension(fileName);
		return this.isPreviewableFileType(extension);
	}

	async fetchFileContent(fileUuid) {
		const response = await fetch(`/users/files/${fileUuid}/content/`);

		if (!response.ok) {
			const error = await response.json();
			throw new Error(error.error || "Failed to fetch file content");
		}

		return response.text();
	}

	showPreviewModal(fileName, content) {
		const modal = document.getElementById("filePreviewModal");
		const modalTitle = modal.querySelector(".modal-title");
		const previewContent = modal.querySelector(".preview-content");

		// Enhanced accessibility
		modal.setAttribute("aria-label", `Preview of ${fileName}`);
		modal.setAttribute("aria-describedby", "preview-content");
		modal.setAttribute("role", "dialog");

		modalTitle.textContent = fileName;
		modalTitle.setAttribute("id", "preview-modal-title");

		// Clear previous content
		previewContent.innerHTML = "";
		previewContent.setAttribute("id", "preview-content");
		previewContent.setAttribute("aria-label", `Content of ${fileName}`);

		// Check if we should use syntax highlighting
		if (this.shouldUseSyntaxHighlighting(fileName)) {
			this.showSyntaxHighlightedContent(previewContent, content, fileName);
		} else {
			// Basic text display
			const preElement = this.createElement("pre", "preview-text", content);
			preElement.setAttribute("aria-label", `Text content of ${fileName}`);
			previewContent.appendChild(preElement);
		}

		new bootstrap.Modal(modal).show();
	}

	// Helper methods for syntax highlighting
	getFileExtension(fileName) {
		return fileName.split(".").pop().toLowerCase();
	}

	// Helper method to open modal with fallbacks
	openModal(modalId) {
		this.activeModals.add(modalId);

		if (window.components?.openCustomModal) {
			window.components.openCustomModal(modalId);
		} else if (typeof openCustomModal === "function") {
			openCustomModal(modalId);
		} else if (window.openCustomModal) {
			window.openCustomModal(modalId);
		} else {
			const modal = document.getElementById(modalId);
			if (modal) modal.style.display = "block";
		}
	}

	// Helper method to close modal with fallbacks
	closeModal(modalId) {
		this.activeModals.delete(modalId);

		if (window.components?.closeCustomModal) {
			window.components.closeCustomModal(modalId);
		} else if (typeof closeCustomModal === "function") {
			closeCustomModal(modalId);
		} else if (window.closeCustomModal) {
			window.closeCustomModal(modalId);
		} else {
			const modal = document.getElementById(modalId);
			if (modal) modal.style.display = "none";
		}
	}

	// Helper method to show success message with fallbacks
	showSuccessMessage(message) {
		if (window.components?.showSuccess) {
			window.components.showSuccess(message);
		} else {
			const live = document.getElementById("aria-live-region");
			if (live) live.textContent = message;
		}
	}

	// Helper method to get CSRF token
	getCsrfToken() {
		return document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
	}

	// Helper method to check if file has extension
	hasFileExtension(fileName) {
		return /\.[^./]+$/.test(fileName);
	}

	// Input validation methods
	isValidUuid(uuid) {
		if (!uuid || typeof uuid !== "string") return false;
		const uuidRegex =
			/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
		return uuidRegex.test(uuid);
	}

	isValidFileName(fileName) {
		if (!fileName || typeof fileName !== "string") return false;
		// Check for invalid characters and length
		const invalidChars = /[<>:"/\\|?*]/;
		return !invalidChars.test(fileName) && fileName.length <= 255;
	}

	isValidPath(path) {
		if (!path || typeof path !== "string") return false;
		// Check for path traversal attempts and invalid characters
		const invalidPathPatterns = /\.\.|[<>:"|?*]/;
		return !invalidPathPatterns.test(path) && path.length <= 4096;
	}

	sanitizeFileName(fileName) {
		if (!fileName) return "";
		// Remove or replace invalid characters
		return fileName.replace(/[<>:"/\\|?*]/g, "_");
	}

	// Helper method to create DOM element with attributes
	createElement(tag, className, innerHTML) {
		const element = document.createElement(tag);
		if (className) element.className = className;
		if (innerHTML) element.innerHTML = innerHTML;
		return element;
	}

	// Helper method to check if file type is previewable
	isPreviewableFileType(extension) {
		const nonPreviewableExtensions = [
			"h5",
			"hdf5",
			"hdf",
			"nc",
			"netcdf",
			"mat",
			"sav",
			"rdata",
			"rds",
			"bin",
			"dat",
			"raw",
			"img",
			"iso",
			"dmg",
			"pkg",
			"deb",
			"rpm",
			"zip",
			"tar",
			"gz",
			"bz2",
			"7z",
			"rar",
			"exe",
			"dll",
			"so",
			"dylib",
			"pdb",
			"obj",
			"lib",
			"a",
			"o",
			"class",
			"jar",
			"war",
			"ear",
			"pdf",
			"doc",
			"docx",
			"xls",
			"xlsx",
			"ppt",
			"pptx",
			"odt",
			"ods",
			"odp",
			"psd",
			"ai",
			"eps",
			"svg",
			"mp3",
			"mp4",
			"avi",
			"mov",
			"wmv",
			"flv",
			"db",
			"sqlite",
			"mdb",
			"accdb",
			"bak",
			"tmp",
			"temp",
			"log",
			"out",
		];
		return !nonPreviewableExtensions.includes(extension);
	}

	// Helper method to extract text from notebook cell source
	extractCellSourceText(source) {
		if (Array.isArray(source)) {
			return source.join("") || "";
		}
		if (typeof source === "string") {
			return source;
		}
		return String(source || "");
	}

	// Helper method to extract text from notebook cell output
	extractCellOutputText(output) {
		if (output.output_type === "stream") {
			return Array.isArray(output.text)
				? output.text.join("")
				: String(output.text || "");
		}
		if (output.output_type === "execute_result") {
			return output.data?.["text/plain"]
				? Array.isArray(output.data["text/plain"])
					? output.data["text/plain"].join("")
					: String(output.data["text/plain"])
				: "";
		}
		return "";
	}

	getLanguageFromExtension(extension) {
		const languageMap = {
			js: "javascript",
			jsx: "javascript",
			ts: "typescript",
			tsx: "typescript",
			py: "python",
			pyw: "python",
			ipynb: "json", // Jupyter notebooks are JSON
			json: "json",
			xml: "markup",
			html: "markup",
			htm: "markup",
			css: "css",
			scss: "css",
			sass: "css",
			sh: "bash",
			bash: "bash",
			zsh: "bash",
			fish: "bash",
			c: "c",
			cpp: "cpp",
			cc: "cpp",
			cxx: "cpp",
			h: "c",
			hpp: "cpp",
			java: "java",
			php: "php",
			rb: "ruby",
			go: "go",
			rs: "rust",
			swift: "swift",
			kt: "kotlin",
			scala: "scala",
			clj: "clojure",
			hs: "haskell",
			ml: "ocaml",
			fs: "fsharp",
			cs: "csharp",
			vb: "vbnet",
			sql: "sql",
			r: "r",
			m: "matlab",
			pl: "perl",
			tcl: "tcl",
			lua: "lua",
			vim: "vim",
			yaml: "yaml",
			yml: "yaml",
			toml: "toml",
			ini: "ini",
			cfg: "ini",
			conf: "ini",
			md: "markdown",
			markdown: "markdown",
			txt: "text",
			log: "text",
		};
		return languageMap[extension] || "text";
	}

	shouldUseSyntaxHighlighting(fileName) {
		const extension = this.getFileExtension(fileName);
		const highlightableExtensions = [
			"js",
			"jsx",
			"ts",
			"tsx",
			"py",
			"pyw",
			"ipynb",
			"json",
			"xml",
			"html",
			"htm",
			"css",
			"scss",
			"sass",
			"sh",
			"bash",
			"zsh",
			"fish",
			"c",
			"cpp",
			"cc",
			"cxx",
			"h",
			"hpp",
			"java",
			"php",
			"rb",
			"go",
			"rs",
			"swift",
			"kt",
			"scala",
			"clj",
			"hs",
			"ml",
			"fs",
			"cs",
			"vb",
			"sql",
			"r",
			"m",
			"pl",
			"tcl",
			"lua",
			"vim",
			"yaml",
			"yml",
			"toml",
			"ini",
			"cfg",
			"conf",
			"md",
			"markdown",
		];
		return highlightableExtensions.includes(extension);
	}

	showSyntaxHighlightedContent(container, content, fileName) {
		const extension = this.getFileExtension(fileName);
		const language = this.getLanguageFromExtension(extension);

		// Special handling for Jupyter notebooks
		if (extension === "ipynb") {
			this.showJupyterNotebookPreview(container, content, fileName);
			return;
		}

		// Create code element with language class
		const codeElement = this.createElement("code", `language-${language}`);
		codeElement.textContent = content;

		// Create pre element
		const preElement = this.createElement("pre", "syntax-highlighted");
		preElement.appendChild(codeElement);

		// Add to container
		container.appendChild(preElement);

		// Apply Prism.js highlighting
		if (window.Prism) {
			window.Prism.highlightElement(codeElement);
		}
	}

	showJupyterNotebookPreview(container, content, fileName) {
		try {
			// Parse the JSON content
			const notebook = JSON.parse(content);

			// Create a container for the notebook preview
			const notebookContainer = this.createElement(
				"div",
				"jupyter-notebook-preview",
			);

			// Add notebook metadata header
			const header = this.createElement("div", "notebook-header");
			header.innerHTML = `
				<div class="notebook-title">
					<i class="bi bi-journal-code"></i>
					${notebook.metadata?.title || fileName}
				</div>
				<div class="notebook-info">
					<span class="notebook-kernel">${notebook.metadata?.kernelspec?.display_name || "Python"}</span>
					<span class="notebook-cells">${notebook.cells?.length || 0} cells</span>
				</div>
			`;
			notebookContainer.appendChild(header);

			// Process each cell
			if (notebook.cells && Array.isArray(notebook.cells)) {
				notebook.cells.forEach((cell, index) => {
					const cellElement = this.createNotebookCell(cell, index);
					notebookContainer.appendChild(cellElement);
				});
			}

			container.appendChild(notebookContainer);
		} catch (error) {
			// Fallback to JSON display if parsing fails
			console.warn(
				"Failed to parse Jupyter notebook, falling back to JSON:",
				error,
			);
			this.showSyntaxHighlightedContent(container, content, "fallback.json");
		}
	}

	createNotebookCell(cell, index) {
		const cellContainer = this.createElement(
			"div",
			`notebook-cell ${cell.cell_type}`,
		);
		const cellHeader = this.createElement("div", "cell-header");

		let headerContent = "";
		if (cell.cell_type === "code") {
			const execCount =
				cell.execution_count !== null ? cell.execution_count : " ";
			headerContent = `
				<span class="cell-type code">Code</span>
				<span class="execution-count">In [${execCount}]:</span>
			`;
		} else {
			headerContent = `<span class="cell-type markdown">Markdown</span>`;
		}

		cellHeader.innerHTML = headerContent;
		cellContainer.appendChild(cellHeader);

		// Cell content
		const cellContent = this.createElement("div", "cell-content");

		if (cell.cell_type === "code") {
			// Code cell with syntax highlighting
			const codeElement = this.createElement("code", "language-python");
			const sourceText = this.extractCellSourceText(cell.source);
			codeElement.textContent = sourceText;

			const preElement = this.createElement("pre");
			preElement.appendChild(codeElement);
			cellContent.appendChild(preElement);

			// Apply syntax highlighting
			if (window.Prism) {
				window.Prism.highlightElement(codeElement);
			}

			// Add output if present
			if (cell.outputs && cell.outputs.length > 0) {
				const outputContainer = this.createElement("div", "cell-output");
				outputContainer.innerHTML = `<span class="output-label">Out [${cell.execution_count}]:</span>`;

				for (const output of cell.outputs) {
					const outputText = this.extractCellOutputText(output);
					if (outputText) {
						const outputElement = this.createElement(
							"pre",
							output.output_type === "stream"
								? "output-stream"
								: "output-result",
						);
						outputElement.textContent = outputText;
						outputContainer.appendChild(outputElement);
					}
				}

				cellContent.appendChild(outputContainer);
			}
		} else {
			// Markdown cell
			const markdownElement = this.createElement("div", "markdown-content");
			const sourceText = this.extractCellSourceText(cell.source);
			markdownElement.textContent = sourceText;
			cellContent.appendChild(markdownElement);
		}

		cellContainer.appendChild(cellContent);
		return cellContainer;
	}

	showError(message, error = null, context = "") {
		// Log error details for debugging
		if (error) {
			console.error(`FileManager Error [${context}]:`, {
				message: error.message,
				stack: error.stack,
				userMessage: message,
				timestamp: new Date().toISOString(),
				userAgent: navigator.userAgent,
			});
		} else {
			console.warn(`FileManager Warning [${context}]:`, message);
		}

		// Show user-friendly error message
		if (window.components?.showError) {
			window.components.showError(message);
			return;
		}
		const live = document.getElementById("aria-live-region");
		if (live) {
			live.textContent = message;
			return;
		}
		// Final fallback: inline banner near top
		const container =
			document.querySelector(".container-fluid") || document.body;
		const div = this.createElement(
			"div",
			"alert alert-danger alert-dismissible fade show",
			`${message}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`,
		);
		container.insertBefore(div, container.firstChild);
	}

	// Enhanced error message formatting
	getUserFriendlyErrorMessage(error, context = "") {
		if (!error) return "An unexpected error occurred";

		// Handle common error types
		if (error.name === "NetworkError" || error.message.includes("fetch")) {
			return "Network error: Please check your connection and try again";
		}
		if (error.name === "TypeError" && error.message.includes("JSON")) {
			return "Invalid response format: Please try again or contact support";
		}
		if (error.message.includes("403") || error.message.includes("Forbidden")) {
			return "Access denied: You don't have permission to perform this action";
		}
		if (error.message.includes("404") || error.message.includes("Not Found")) {
			return "Resource not found: The requested file or directory may have been moved or deleted";
		}
		if (
			error.message.includes("500") ||
			error.message.includes("Internal Server Error")
		) {
			return "Server error: Please try again later or contact support";
		}

		// Default user-friendly message
		return error.message || "An unexpected error occurred";
	}

	escapeHtml(unsafe) {
		return unsafe
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#039;");
	}

	// Memory management and cleanup
	cleanup() {
		// Remove all bound event handlers
		for (const [element, handler] of this.boundHandlers) {
			if (element?.removeEventListener) {
				element.removeEventListener("click", handler);
			}
		}
		this.boundHandlers.clear();

		// Close all active modals
		for (const modalId of this.activeModals) {
			this.closeModal(modalId);
		}
		this.activeModals.clear();

		// Clear file references
		this.droppedFiles = null;
		window.selectedFiles = null;

		console.log("FileManager cleanup completed");
	}

	// Browser compatibility check
	checkBrowserSupport() {
		const requiredFeatures = {
			"File API": "File" in window,
			FileReader: "FileReader" in window,
			FormData: "FormData" in window,
			"Fetch API": "fetch" in window,
			Promise: "Promise" in window,
			Map: "Map" in window,
			Set: "Set" in window,
		};

		const missingFeatures = Object.entries(requiredFeatures)
			.filter(([name, supported]) => !supported)
			.map(([name]) => name);

		if (missingFeatures.length > 0) {
			console.warn("Missing browser features:", missingFeatures);
			return false;
		}

		return true;
	}

	// Track event handler for cleanup
	bindEventHandler(element, event, handler) {
		this.boundHandlers.set(element, handler);
		element.addEventListener(event, handler);
	}

	handleFileSelection(files) {
		const selectedFilesList = document.getElementById("selectedFilesList");
		const selectedFiles = document.getElementById("selectedFiles");
		if (!selectedFilesList || !selectedFiles) return;
		selectedFilesList.innerHTML = "";

		const allFiles = Array.from(files || []);
		// Filter out likely directory placeholders that some browsers expose on drop
		const realFiles = allFiles.filter((f) => {
			// Keep if size > 0 or has a known extension or MIME type
			const hasExtension = this.hasFileExtension(f.name);
			return f.size > 0 || hasExtension || (f.type && f.type.length > 0);
		});

		// If selection came from the file input (webkitdirectory browse), show all files.
		// If it came from drag-and-drop, we may have limited UI space; still show all for clarity.
		for (const file of realFiles) {
			const li = this.createElement(
				"li",
				"",
				`
				<i class="bi bi-file-text"></i>
				<span>${file.webkitRelativePath || file.name}</span>
			`,
			);
			selectedFilesList.appendChild(li);
		}

		if (realFiles.length > 0) {
			selectedFiles.classList.add("has-files");
		} else {
			selectedFiles.classList.remove("has-files");
		}
	}

	renderFileTree(node, container, path = "") {
		for (const [name, value] of Object.entries(node)) {
			let li;
			if (value instanceof File) {
				// Render file
				li = this.createElement(
					"li",
					"",
					`
          <i class="bi bi-file-text"></i>
          <span>${name}</span>
        `,
				);
			} else {
				// Render directory
				li = this.createElement(
					"li",
					"",
					`
          <i class="bi bi-folder"></i>
          <span>${name}</span>
          <ul></ul>
        `,
				);
				this.renderFileTree(value, li.querySelector("ul"), `${path + name}/`);
			}
			container.appendChild(li);
		}
	}

	handleFileCardClick(e, card) {
		// Ignore clicks originating from the actions area (dropdown/buttons)
		if (e.target.closest(".file-actions")) {
			return;
		}

		const type = card.dataset.type;
		const path = card.dataset.path;
		const uuid = card.dataset.uuid;

		if (type === "directory") {
			this.handleDirectoryClick(path);
		} else if (type === "dataset") {
			this.handleDatasetClick(uuid);
		} else if (type === "file") {
			this.handleFileClick(card, uuid);
		}
	}

	handleDirectoryClick(path) {
		if (path && this.isValidPath(path)) {
			// Remove any duplicate slashes and ensure proper path format
			const cleanPath = path.replace(/\/+/g, "/").replace(/\/$/, "");
			// Build the navigation URL
			const navUrl = `/users/files/?dir=${encodeURIComponent(cleanPath)}`;
			// Navigate to the directory using the dir query parameter
			window.location.href = navUrl;
		} else {
			console.warn("Invalid directory path:", path);
			this.showError("Invalid directory path", null, "navigation");
		}
	}

	handleDatasetClick(uuid) {
		if (uuid && this.isValidUuid(uuid)) {
			const datasetUrl = `/users/files/?dir=/datasets/${encodeURIComponent(uuid)}`;
			window.location.href = datasetUrl;
		} else {
			console.warn("Invalid dataset UUID:", uuid);
			this.showError("Invalid dataset identifier", null, "navigation");
		}
	}

	handleFileClick(card, uuid) {
		if (uuid && this.isValidUuid(uuid)) {
			// Prefer the exact text node for the filename and trim whitespace
			const rawName =
				card.querySelector(".file-name-text")?.textContent ||
				card.querySelector(".file-name")?.textContent ||
				"";
			const name = rawName.trim();

			// Validate and sanitize filename
			if (!this.isValidFileName(name)) {
				console.warn("Invalid filename:", name);
				this.showError("Invalid filename", null, "file-preview");
				return;
			}

			const sanitizedName = this.sanitizeFileName(name);
			const lower = sanitizedName.toLowerCase();

			if (this.shouldPreviewFile(sanitizedName)) {
				this.showTextFilePreview(uuid, sanitizedName);
			} else if (lower.endsWith(".h5") || lower.endsWith(".hdf5")) {
				// H5 files - no preview, no action
			} else {
				const detailUrl = `/users/file-detail/${uuid}/`;
				window.location.href = detailUrl;
			}
		} else {
			console.warn("Invalid file UUID:", uuid);
			this.showError("Invalid file identifier", null, "file-preview");
		}
	}
}

// Initialize file manager when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
	new FileManager();
});
