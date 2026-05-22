/**
 * Files browser: grid navigation, previews, drag/drop, capture modal UI extras.
 */
class FilesBrowserManager extends ModalManager {
	constructor(config = {}) {
		super(config);
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

		const hasFilesBrowser = Boolean(
			document.querySelector(".files-container"),
		);
		if (hasFilesBrowser) {
			// Prevent browser from navigating away when user drags files over the whole window
			this.addGlobalDropGuards();
			this.init();
			window.filesBrowserManager = this;
		}

		
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

		const files = await UploadUtils.collectFilesFromDataTransfer(dt);

		if (!files.length) {
			console.warn("No files collected from global drop");
			return;
		}

		// Store the dropped files globally
		window.captureUploadController?.setSelectedFiles(files);

		// Open the upload modal
		const uploadModalEl = document.getElementById("uploadCaptureModal");
		if (!uploadModalEl) {
			console.error("Upload modal element not found");
			return;
		}

		window.ModalManager.openModal("uploadCaptureModal");

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

	init() {
		// Get container and data
		this.container = document.querySelector(".files-container");
		if (!this.container) {
			this.showError("Files container not found", null, "initialization");
			return;
		}

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

		const essentials = [
			captureElements.uploadZone,
			captureElements.fileInput,
			captureElements.selectedFilesList,
			captureElements.uploadForm,
		];

		if (essentials.every((el) => el)) {
			this.initializeCaptureUploadUIOnly(captureElements);
		}
	}

	initializeCaptureUploadUIOnly(elements) {
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
				const files = await UploadUtils.collectFilesFromDataTransfer(dt);
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
			this.handleFileSelection(UploadUtils.convertToFiles(e.target.files));
		});

		// Check for globally dropped files when modal opens
		if (window.captureUploadController?.getSelectedFiles()?.length) {
			this.handleFileSelection(window.captureUploadController.getSelectedFiles());
		}

		// Submit is handled by UploadCaptureModalController (chunked upload).
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

				// Update modal text
				const nameEl = document.getElementById("downloadCaptureName");
				if (nameEl) nameEl.textContent = captureName;

				// Show modal using helper method
				this.activeModals.add("downloadModal");
				this.openModal("downloadModal");

				// Confirm handler
				const confirmBtn = document.getElementById("confirmDownloadBtn");
				if (confirmBtn) {
					const onConfirm = () => {
						this.closeModal("downloadModal");
						this.activeModals.delete("downloadModal");
						this.postDownloadItem("capture", captureUuid);
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
				this.activeModals.add("downloadModal");
				this.openModal("downloadModal");
				const confirmBtn = document.getElementById("confirmDownloadBtn");
				if (confirmBtn) {
					const onConfirm = () => {
						this.closeModal("downloadModal");
						this.activeModals.delete("downloadModal");
						this.postDownloadItem("dataset", datasetUuid);
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

	postDownloadItem(itemType, itemUuid) {
		const csrf = window.APIClient?.getCSRFToken?.() || "";
		fetch(
			`/users/download-item/${itemType}/${encodeURIComponent(itemUuid)}/`,
			{
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": csrf,
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
				const userMessage =
					window.DOMUtils?.getUserFriendlyErrorMessage(error, "file-preview") ||
					error?.message ||
					"An unexpected error occurred";
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
		const previewModalId = "filePreviewModal";
		const modal = document.getElementById(previewModalId);
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

		this.openModal(previewModalId);
	}

	// Helper methods for syntax highlighting
	getFileExtension(fileName) {
		return fileName.split(".").pop().toLowerCase();
	}

	showSuccessMessage(message) {
		if (window.DOMUtils?.showMessage) {
			void window.DOMUtils.showMessage(message, {
				variant: "success",
				placement: "toast",
			});
			return;
		}
		const live = document.getElementById("aria-live-region");
		if (live) live.textContent = message;
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
			"7z",
			"a",
			"accdb",
			"ai",
			"avi",
			"bak",
			"bin",
			"bz2",
			"class",
			"dll",
			"dmg",
			"doc",
			"docx",
			"ear",
			"eps",
			"exe",
			"flv",
			"gz",
			"h5",
			"hdf",
			"hdf5",
			"img",
			"iso",
			"jar",
			"lib",
			"log",
			"mat",
			"mdb",
			"mov",
			"mp3",
			"mp4",
			"nc",
			"netcdf",
			"obj",
			"odp",
			"ods",
			"odt",
			"o",
			"out",
			"pdf",
			"pdb",
			"pkg",
			"ppt",
			"pptx",
			"psd",
			"r",
			"rar",
			"rdata",
			"rds",
			"raw",
			"rpm",
			"sav",
			"so",
			"sqlite",
			"svg",
			"tar",
			"temp",
			"tmp",
			"war",
			"wmv",
			"xls",
			"xlsx",
			"zip",
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
			console.error(`FilesBrowserManager Error [${context}]:`, {
				message: error.message,
				stack: error.stack,
				userMessage: message,
				timestamp: new Date().toISOString(),
				userAgent: navigator.userAgent,
			});
		} else {
			console.warn(`FilesBrowserManager Warning [${context}]:`, message);
		}

		if (window.DOMUtils?.showMessage) {
			void window.DOMUtils.showMessage(message, {
				variant: "danger",
				placement: "toast",
			});
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
		window.captureUploadController?.resetSession?.();

		console.log("FilesBrowserManager cleanup completed");
	}

	// Browser compatibility (see core/PageGate.js)
	checkBrowserSupport() {
		if (
			window.PageGate &&
			typeof window.PageGate.checkUploadFeatures === "function"
		) {
			return window.PageGate.checkUploadFeatures();
		}
		return false;
	}

	handleFileSelection(files) {
		const allFiles = Array.from(files || []);
		// Filter out likely directory placeholders that some browsers expose on drop
		const realFiles = allFiles.filter((f) => {
			// Keep if size > 0 or has a known extension or MIME type
			const hasExtension = this.hasFileExtension(f.name);
			return f.size > 0 || hasExtension || (f.type && f.type.length > 0);
		});

		window.captureUploadController?.setSelectedFiles(realFiles);

		const selectedFilesList = document.getElementById("selectedFilesList");
		const selectedFiles = document.getElementById("selectedFiles");
		if (!selectedFilesList || !selectedFiles) return;
		selectedFilesList.innerHTML = "";

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

if (typeof window !== "undefined") {
	window.FilesBrowserManager = FilesBrowserManager;
	window.UploadManager = FilesBrowserManager;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { FilesBrowserManager };
}
