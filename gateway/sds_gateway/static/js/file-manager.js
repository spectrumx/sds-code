class FileManager {
	constructor() {
		console.log("FileManager constructor called");
		this.droppedFiles = null;
		// Prevent browser from navigating away when user drags files over the whole window
		this.addGlobalDropGuards();
		this.init();
	}

	addGlobalDropGuards() {
		console.log("Adding global drop guards");
		// Prevent browser navigation on any drop event
		document.addEventListener(
			"dragover",
			(e) => {
				console.log("Dragover event on document");
				e.preventDefault();
			},
			false,
		);

		document.addEventListener(
			"drop",
			(e) => {
				console.log("Drop event on document");
				console.log("Drop target:", e.target);
				console.log("Drop target tagName:", e.target.tagName);
				console.log("Drop target className:", e.target.className);
				console.log("Drop coordinates:", e.clientX, e.clientY);
				e.preventDefault();
				e.stopPropagation();

				// Always handle global drops for testing
				console.log("Handling global drop - bypassing modal check for testing");
				this.handleGlobalDrop(e);
			},
			false,
		);

		console.log("Global drop guards added");
	}

	async handleGlobalDrop(e) {
		console.log("Global drop detected");

		const dt = e.dataTransfer;
		if (!dt) {
			console.warn("No dataTransfer in global drop");
			return;
		}

		console.log("Processing globally dropped files");
		const files = await this.collectFilesFromDataTransfer(dt);
		console.log("Collected files:", files);

		if (!files.length) {
			console.warn("No files collected from global drop");
			return;
		}

		// Store the dropped files globally
		window.selectedFiles = files;
		console.log("Stored files in window.selectedFiles:", files.length, "files");

		// Open the upload modal
		const uploadModalEl = document.getElementById("uploadCaptureModal");
		if (!uploadModalEl) {
			console.error("Upload modal element not found");
			return;
		}

		const uploadModal = new bootstrap.Modal(uploadModalEl);
		uploadModal.show();
		console.log("Opened upload modal");

		// Wait a bit for modal to fully open, then trigger file selection
		setTimeout(() => {
			this.handleGlobalFilesInModal(files);
		}, 200);
	}

	handleGlobalFilesInModal(files) {
		console.log("Handling global files in modal");

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
			console.log("Added has-files class to selected files section");
		}

		// Update the file input label to show selected files
		const fileInputLabel = fileInput?.nextElementSibling;
		if (fileInputLabel?.classList.contains("form-control")) {
			const fileNames = files
				.map((f) => f.webkitRelativePath || f.name)
				.join(", ");
			fileInputLabel.textContent = fileNames || "No directory selected.";
		}

		console.log("Global files loaded into modal:", files.length, "files");
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
			this.showError("Files container not found");
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
			this.showError("Upload elements not found");
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

				// Get CSRF token from DOM and add it when present
				const csrfEl = document.querySelector("[name=csrfmiddlewaretoken]");
				if (csrfEl?.value) {
					formData.append("csrfmiddlewaretoken", csrfEl.value);
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
				this.showError(`Upload failed: ${error.message}`);
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
				this.showError(`Upload failed: ${error.message}`);
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
				// Update modal text
				const nameEl = document.getElementById("downloadCaptureName");
				if (nameEl) nameEl.textContent = captureName;
				// Silently ignore if element is missing in DOM variant
				// Show modal using components.js helper or fallback
				if (
					window.components &&
					typeof window.components.openCustomModal === "function"
				) {
					window.components.openCustomModal("downloadModal");
				} else if (typeof openCustomModal === "function") {
					openCustomModal("downloadModal");
				} else if (window.openCustomModal) {
					window.openCustomModal("downloadModal");
				} else {
					const m = document.getElementById("downloadModal");
					if (m) m.style.display = "block";
				}
				// Confirm handler
				const confirmBtn = document.getElementById("confirmDownloadBtn");
				if (confirmBtn) {
					const onConfirm = () => {
						if (
							window.components &&
							typeof window.components.closeCustomModal === "function"
						) {
							window.components.closeCustomModal("downloadModal");
						} else if (typeof closeCustomModal === "function") {
							closeCustomModal("downloadModal");
						} else if (window.closeCustomModal) {
							window.closeCustomModal("downloadModal");
						} else {
							const m = document.getElementById("downloadModal");
							if (m) m.style.display = "none";
						}
						// Use unified download handler - much simpler!
						if (window.components?.handleDownload) {
							// Create a dummy button element for the unified handler
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
				if (
					window.components &&
					typeof window.components.openCustomModal === "function"
				) {
					window.components.openCustomModal("downloadModal");
				} else if (typeof openCustomModal === "function") {
					openCustomModal("downloadModal");
				} else if (window.openCustomModal) {
					window.openCustomModal("downloadModal");
				} else {
					const m = document.getElementById("downloadModal");
					if (m) m.style.display = "block";
				}
				const confirmBtn = document.getElementById("confirmDownloadBtn");
				if (confirmBtn) {
					const onConfirm = () => {
						if (
							window.components &&
							typeof window.components.closeCustomModal === "function"
						) {
							window.components.closeCustomModal("downloadModal");
						} else if (typeof closeCustomModal === "function") {
							closeCustomModal("downloadModal");
						} else if (window.closeCustomModal) {
							window.closeCustomModal("downloadModal");
						} else {
							const m = document.getElementById("downloadModal");
							if (m) m.style.display = "none";
						}
						fetch(
							`/users/download-item/dataset/${encodeURIComponent(datasetUuid)}/`,
							{
								method: "POST",
								headers: {
									"Content-Type": "application/json",
									"X-CSRFToken":
										document.querySelector("[name=csrfmiddlewaretoken]")
											?.value || "",
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
				// Use inline banner if available; otherwise, aria-live region
				if (
					window.components &&
					typeof window.components.showSuccess === "function"
				) {
					window.components.showSuccess(`Download starting: ${fileName}`);
				} else {
					const live = document.getElementById("aria-live-region");
					if (live) live.textContent = `Download starting: ${fileName}`;
				}
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
				xhr.setRequestHeader(
					"X-CSRFToken",
					document.querySelector("[name=csrfmiddlewaretoken]")?.value || "",
				);
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
			try {
				sessionStorage.setItem(
					"filesAlert",
					JSON.stringify({
						message: `Upload failed: ${error.message}`,
						type: "error",
					}),
				);
				// Reload to display the banner via template startup script
				window.location.reload();
			} catch (_) {
				this.showError(`Upload failed: ${error.message}`);
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
			const content = await this.fetchFileContent(fileUuid);
			this.showPreviewModal(fileName, content);
		} catch (error) {
			this.showError(error.message || "Failed to load file preview");
		}
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

		modalTitle.textContent = fileName;

		// Clear previous content
		previewContent.innerHTML = "";

		// Check if we should use syntax highlighting
		if (this.shouldUseSyntaxHighlighting(fileName)) {
			this.showSyntaxHighlightedContent(previewContent, content, fileName);
		} else {
			// Basic text display
			const preElement = document.createElement("pre");
			preElement.className = "preview-text";
			preElement.textContent = content;
			previewContent.appendChild(preElement);
		}

		new bootstrap.Modal(modal).show();
	}

	// Helper methods for syntax highlighting
	getFileExtension(fileName) {
		return fileName.split(".").pop().toLowerCase();
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
		const codeElement = document.createElement("code");
		codeElement.className = `language-${language}`;
		codeElement.textContent = content;

		// Create pre element
		const preElement = document.createElement("pre");
		preElement.className = "syntax-highlighted";
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
			const notebookContainer = document.createElement("div");
			notebookContainer.className = "jupyter-notebook-preview";

			// Add notebook metadata header
			const header = document.createElement("div");
			header.className = "notebook-header";
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
		const cellContainer = document.createElement("div");
		cellContainer.className = `notebook-cell ${cell.cell_type}`;

		// Cell header with type and execution count
		const cellHeader = document.createElement("div");
		cellHeader.className = "cell-header";

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
		const cellContent = document.createElement("div");
		cellContent.className = "cell-content";

		if (cell.cell_type === "code") {
			// Code cell with syntax highlighting
			const codeElement = document.createElement("code");
			codeElement.className = "language-python";

			// Handle different source formats (string vs array)
			let sourceText = "";
			if (Array.isArray(cell.source)) {
				sourceText = cell.source.join("") || "";
			} else if (typeof cell.source === "string") {
				sourceText = cell.source;
			} else {
				sourceText = String(cell.source || "");
			}

			codeElement.textContent = sourceText;

			const preElement = document.createElement("pre");
			preElement.appendChild(codeElement);
			cellContent.appendChild(preElement);

			// Apply syntax highlighting
			if (window.Prism) {
				window.Prism.highlightElement(codeElement);
			}

			// Add output if present
			if (cell.outputs && cell.outputs.length > 0) {
				const outputContainer = document.createElement("div");
				outputContainer.className = "cell-output";
				outputContainer.innerHTML = `<span class="output-label">Out [${cell.execution_count}]:</span>`;

				cell.outputs.forEach((output) => {
					if (output.output_type === "stream") {
						const streamElement = document.createElement("pre");
						streamElement.className = "output-stream";
						const streamText = Array.isArray(output.text)
							? output.text.join("")
							: String(output.text || "");
						streamElement.textContent = streamText;
						outputContainer.appendChild(streamElement);
					} else if (output.output_type === "execute_result") {
						const resultElement = document.createElement("pre");
						resultElement.className = "output-result";
						const resultText = output.data?.["text/plain"]
							? Array.isArray(output.data["text/plain"])
								? output.data["text/plain"].join("")
								: String(output.data["text/plain"])
							: "";
						resultElement.textContent = resultText;
						outputContainer.appendChild(resultElement);
					}
				});

				cellContent.appendChild(outputContainer);
			}
		} else {
			// Markdown cell
			const markdownElement = document.createElement("div");
			markdownElement.className = "markdown-content";

			// Handle different source formats (string vs array)
			let sourceText = "";
			if (Array.isArray(cell.source)) {
				sourceText = cell.source.join("") || "";
			} else if (typeof cell.source === "string") {
				sourceText = cell.source;
			} else {
				sourceText = String(cell.source || "");
			}

			markdownElement.textContent = sourceText;
			cellContent.appendChild(markdownElement);
		}

		cellContainer.appendChild(cellContent);
		return cellContainer;
	}

	showError(message) {
		if (
			window.components &&
			typeof window.components.showError === "function"
		) {
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
		const div = document.createElement("div");
		div.className = "alert alert-danger alert-dismissible fade show";
		div.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
		container.insertBefore(div, container.firstChild);
	}

	escapeHtml(unsafe) {
		return unsafe
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#039;");
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
			const hasExtension = /\.[^./]+$/.test(f.name);
			return f.size > 0 || hasExtension || (f.type && f.type.length > 0);
		});

		// If selection came from the file input (webkitdirectory browse), show all files.
		// If it came from drag-and-drop, we may have limited UI space; still show all for clarity.
		for (const file of realFiles) {
			const li = document.createElement("li");
			li.innerHTML = `
				<i class="bi bi-file-text"></i>
				<span>${file.webkitRelativePath || file.name}</span>
			`;
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
			const li = document.createElement("li");

			if (value instanceof File) {
				// Render file
				li.innerHTML = `
          <i class="bi bi-file-text"></i>
          <span>${name}</span>
        `;
			} else {
				// Render directory
				li.innerHTML = `
          <i class="bi bi-folder"></i>
          <span>${name}</span>
          <ul></ul>
        `;
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
		const isCapture = card.dataset.isCapture === "true";
		const isDataset = card.dataset.isDataset === "true";
		const captureUuid = card.dataset.captureUuid;

		if (type === "directory") {
			// Handle directory navigation
			if (path) {
				// Remove any duplicate slashes and ensure proper path format
				const cleanPath = path.replace(/\/+/g, "/").replace(/\/$/, "");
				// Build the navigation URL
				const navUrl = `/users/files/?dir=${encodeURIComponent(cleanPath)}`;
				// Navigate to the directory using the dir query parameter
				window.location.href = navUrl;
			}
		} else if (type === "dataset") {
			// Handle dataset click - show dataset contents
			if (uuid) {
				const datasetUrl = `/users/files/?dir=/datasets/${encodeURIComponent(uuid)}`;
				window.location.href = datasetUrl;
			}
		} else if (type === "file") {
			// Preview text-like files in modal, use H5 structure modal for .h5/.hdf5
			if (uuid) {
				// Prefer the exact text node for the filename and trim whitespace
				const rawName =
					card.querySelector(".file-name-text")?.textContent ||
					card.querySelector(".file-name")?.textContent ||
					"";
				const name = rawName.trim();
				const lower = name.toLowerCase();
				if (
					lower.endsWith(".json") ||
					lower.endsWith(".txt") ||
					lower.endsWith(".log") ||
					lower.endsWith(".py") ||
					lower.endsWith(".js") ||
					lower.endsWith(".md") ||
					lower.endsWith(".csv") ||
					lower.endsWith(".ipynb")
				) {
					this.showTextFilePreview(uuid, name);
				} else if (lower.endsWith(".h5") || lower.endsWith(".hdf5")) {
					// H5 files - no preview, no action
					console.log("H5 file clicked, no preview available");
				} else {
					const detailUrl = `/users/file-detail/${uuid}/`;
					window.location.href = detailUrl;
				}
			}
		}
	}
}

// Initialize file manager when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
	console.log("DOMContentLoaded event fired, creating FileManager");
	new FileManager();
	console.log("FileManager created");
});
