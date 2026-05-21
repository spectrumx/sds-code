/**
 * Files browser: grid navigation, previews, drag/drop, upload modal wiring.
 * Primary entry script for the files page (replaces the former FileManager module).
 */
class UploadManager extends ModalManager {
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

		UploadManager.initSharedUploadArtifacts({ hasFilesBrowser });
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
		window.selectedFiles = files;

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
		if (window.selectedFiles?.length) {
			this.handleFileSelection(window.selectedFiles);
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
		const csrf = window.APIClient
			? new window.APIClient().getCSRFToken()
			: document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
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
			console.error(`UploadManager Error [${context}]:`, {
				message: error.message,
				stack: error.stack,
				userMessage: message,
				timestamp: new Date().toISOString(),
				userAgent: navigator.userAgent,
			});
		} else {
			console.warn(`UploadManager Warning [${context}]:`, message);
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
		window.selectedFiles = null;

		console.log("UploadManager cleanup completed");
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

	static wireCaptureModalFileInputStore() {
		const modal = document.getElementById("uploadCaptureModal");
		if (!modal) return;
		modal.addEventListener("shown.bs.modal", () => {
			const fileInput = document.getElementById("captureFileInput");
			if (!fileInput) return;
			if (window._blake3CaptureHandler) {
				fileInput.removeEventListener("change", window._blake3CaptureHandler);
			}
			window._blake3CaptureHandler = (event) => {
				const files = event.target.files;
				if (!files?.length) return;
				window.selectedFiles = Array.from(files);
			};
			fileInput.addEventListener("change", window._blake3CaptureHandler);
		});
	}

	static initSharedUploadArtifacts({ hasFilesBrowser } = {}) {
		UploadManager.wireCaptureModalFileInputStore();
		if (document.getElementById("uploadCaptureModal")) {
			const ctrl = new UploadCaptureModalController({});
			ctrl.init();
			window.captureUploadController = ctrl;
		}
		if (document.getElementById("captureTypeSelect")) {
			window.captureTypeSelectorInstance = new CaptureTypeSelector();
		}
		if (hasFilesBrowser && document.getElementById("uploadFileForm")) {
			window.fileUploadHandlerInstance = new FileUploadHandler();
			window.fileUploadHandler = window.fileUploadHandlerInstance;
		}
	}
}

/** Capture type dropdown for upload modal. Migrated from deprecated/files-ui.js */
/**
 * Capture Type Selection Handler
 * Manages capture type dropdown and conditional form fields
 */
class CaptureTypeSelector {
	constructor() {
		this.boundHandlers = new Map(); // Track event handlers for cleanup
		this.initializeElements();
		this.setupEventListeners();
	}

	initializeElements() {
		this.captureTypeSelect = document.getElementById("captureTypeSelect");
		this.channelInputGroup = document.getElementById("channelInputGroup");
		this.scanGroupInputGroup = document.getElementById("scanGroupInputGroup");
		this.captureChannelsInput = document.getElementById("captureChannelsInput");
		this.captureScanGroupInput = document.getElementById(
			"captureScanGroupInput",
		);
		this.uploadModal = document.getElementById("uploadCaptureModal");
	}

	setupEventListeners() {
		// Ensure boundHandlers is initialized
		if (!this.boundHandlers) {
			this.boundHandlers = new Map();
		}

		if (this.captureTypeSelect) {
			const changeHandler = (e) => this.handleTypeChange(e);
			this.boundHandlers.set(this.captureTypeSelect, changeHandler);
			this.captureTypeSelect.addEventListener("change", changeHandler);
			this.handleTypeChange({ target: this.captureTypeSelect });
		}

		if (this.uploadModal) {
			const hiddenHandler = () => this.resetForm();
			this.boundHandlers.set(this.uploadModal, hiddenHandler);
			this.uploadModal.addEventListener("hidden.bs.modal", hiddenHandler);
		}
	}

	handleTypeChange(event) {
		const selectedType = event.target.value;

		if (!selectedType) {
			this.hideInputGroups();
			this.clearRequiredAttributes();
			return;
		}

		if (!this.validateCaptureType(selectedType)) {
			console.warn("Invalid capture type selected:", selectedType);
			this.hideInputGroups();
			this.clearRequiredAttributes();
			return;
		}

		// Hide both input groups initially
		this.hideInputGroups();

		// Clear required attributes
		this.clearRequiredAttributes();

		// Show appropriate input group based on selection
		if (selectedType === "drf") {
			this.showChannelInput();
		} else if (selectedType === "rh") {
			this.showScanGroupInput();
		}
	}

	hideInputGroups() {
		if (this.channelInputGroup) {
			this.channelInputGroup.classList.add("hidden-input-group");
		}
		if (this.scanGroupInputGroup) {
			this.scanGroupInputGroup.classList.add("hidden-input-group");
		}
	}

	clearRequiredAttributes() {
		if (this.captureChannelsInput) {
			this.captureChannelsInput.removeAttribute("required");
		}
		if (this.captureScanGroupInput) {
			this.captureScanGroupInput.removeAttribute("required");
		}
	}

	showChannelInput() {
		if (this.channelInputGroup) {
			this.channelInputGroup.classList.remove("hidden-input-group");
		}
		if (this.captureChannelsInput) {
			this.captureChannelsInput.setAttribute("required", "required");
		}
	}

	showScanGroupInput() {
		if (this.scanGroupInputGroup) {
			this.scanGroupInputGroup.classList.remove("hidden-input-group");
		}
		// scan_group is optional for RadioHound captures, so no required attribute
	}

	// Input validation methods
	validateCaptureType(type) {
		const validTypes = ["drf", "rh"];
		return validTypes.includes(type);
	}

	// Memory management and cleanup
	cleanup() {
		// Remove all bound event handlers
		for (const [element, handler] of this.boundHandlers) {
			if (element?.removeEventListener) {
				element.removeEventListener("change", handler);
				element.removeEventListener("hidden.bs.modal", handler);
			}
		}
		this.boundHandlers.clear();
		console.log("CaptureTypeSelector cleanup completed");
	}

	resetForm() {
		// Reset the form
		const form = document.getElementById("uploadCaptureForm");
		if (form) {
			form.reset();
		}

		// Hide input groups
		this.hideInputGroups();

		// Clear required attributes
		this.clearRequiredAttributes();

		// Clear global variables if they exist
		this.cleanupGlobalState();
	}

	// Better global state management
	cleanupGlobalState() {
		const globalVars = ["filesToSkip", "fileCheckResults", "selectedFiles"];

		for (const varName of globalVars) {
			if (window[varName]) {
				if (typeof window[varName].clear === "function") {
					window[varName].clear();
				} else if (Array.isArray(window[varName])) {
					window[varName].length = 0;
				} else {
					window[varName] = null;
				}
				console.log(`Cleaned up global variable: ${varName}`);
			}
		}
	}
}

/** Single-file upload modal (not capture batch). */
class FileUploadHandler extends ModalManager {
	constructor() {
		super();
		this.uploadForm = document.getElementById("uploadFileForm");
		this.fileInput = document.getElementById("fileInput");
		this.folderInput = document.getElementById("folderInput");
		this.submitBtn = document.getElementById("uploadFileSubmitBtn");
		this.clearBtn = document.getElementById("clearUploadBtn");
		this.uploadText = this.submitBtn?.querySelector(".upload-text");
		this.uploadSpinner = this.submitBtn?.querySelector(".upload-spinner");
		this.validationFeedback = document.getElementById(
			"uploadValidationFeedback",
		);
		this._onSubmit = (e) => this.handleSubmit(e);

		if (this.fileInput) {
			this.fileInput.addEventListener("change", () =>
				this.updateSubmitButton(),
			);
		}
		if (this.folderInput) {
			this.folderInput.addEventListener("change", () =>
				this.updateSubmitButton(),
			);
		}

		if (this.clearBtn) {
			this.clearBtn.addEventListener("click", () => this.clearModal());
		}

		if (this.uploadForm) {
			this.uploadForm.addEventListener("submit", this._onSubmit);
		}
	}

	updateSubmitButton() {
		if (this.submitBtn) {
			const hasFiles = this.fileInput?.files.length > 0;
			const hasFolders = this.folderInput?.files.length > 0;
			this.submitBtn.disabled = !hasFiles && !hasFolders;

			if (hasFiles || hasFolders) {
				this.hideValidationFeedback();
			}
		}
	}

	showValidationFeedback() {
		if (this.validationFeedback) {
			this.validationFeedback.classList.add("d-block");
		}
		this.fileInput?.classList.add("is-invalid");
		this.folderInput?.classList.add("is-invalid");
	}

	hideValidationFeedback() {
		if (this.validationFeedback) {
			this.validationFeedback.classList.remove("d-block");
		}
		this.fileInput?.classList.remove("is-invalid");
		this.folderInput?.classList.remove("is-invalid");
	}

	clearModal() {
		if (this.uploadForm) {
			this.uploadForm.reset();
		}
		if (this.fileInput) {
			this.fileInput.value = "";
		}
		if (this.folderInput) {
			this.folderInput.value = "";
		}
		this.hideValidationFeedback();
		this.updateSubmitButton();
	}

	async handleSubmit(event) {
		event.preventDefault();

		const files = Array.from(this.fileInput?.files || []);
		const folderFiles = Array.from(this.folderInput?.files || []);

		if (files.length === 0 && folderFiles.length === 0) {
			this.showValidationFeedback();
			return;
		}

		this.setUploadingState(true);

		try {
			let csrfToken = window.csrfToken;
			if (!csrfToken) {
				const csrfInput = document.querySelector("[name=csrfmiddlewaretoken]");
				csrfToken = csrfInput ? csrfInput.value : null;
			}

			if (!csrfToken) {
				throw new Error("CSRF token not found");
			}

			const formData = new FormData();
			const allFiles = [...files, ...folderFiles];
			const allRelativePaths = [];

			for (const file of allFiles) {
				formData.append("files", file);
				const relativePath = file.webkitRelativePath || file.name;
				allRelativePaths.push(relativePath);
			}

			for (const relativePath of allRelativePaths) {
				formData.append("relative_paths", relativePath);
			}
			for (const relativePath of allRelativePaths) {
				formData.append("all_relative_paths", relativePath);
			}

			formData.append("capture_type", "");
			formData.append("channels", "");
			formData.append("scan_group", "");
			formData.append("csrfmiddlewaretoken", csrfToken);

			const response = await fetch(window.uploadFilesUrl, {
				method: "POST",
				body: formData,
				headers: {
					"X-CSRFToken": csrfToken,
				},
			});

			const result = await response.json();

			if (response.ok) {
				const fileCount = allFiles.length;
				const successMsg =
					fileCount === 1
						? "1 file uploaded successfully!"
						: `${fileCount} files uploaded successfully!`;
				this.showResult("success", successMsg);
				this.clearModal();
				this.closeModal("uploadFileModal");

				if (window.filesBrowserManager?.loadFiles) {
					window.filesBrowserManager.loadFiles();
				} else {
					window.location.reload();
				}
			} else {
				this.showResult(
					"error",
					result.error || "Upload failed. Please try again.",
				);
			}
		} catch (error) {
			console.error("Upload error:", error);
			this.showResult(
				"error",
				"Upload failed. Please check your connection and try again.",
			);
		} finally {
			this.setUploadingState(false);
		}
	}

	setUploadingState(uploading) {
		if (this.submitBtn) {
			this.submitBtn.disabled = uploading;
		}
		if (this.uploadText && this.uploadSpinner) {
			this.uploadText.classList.toggle("d-none", uploading);
			this.uploadSpinner.classList.toggle("d-none", !uploading);
		}
	}

	showResult(type, message) {
		const resultModalId = "uploadResultModal";
		const resultModal = document.getElementById(resultModalId);
		const resultBody = document.getElementById("uploadResultModalBody");

		if (resultModal && resultBody) {
			resultBody.innerHTML = `
				<div class="alert alert-${type === "success" ? "success" : "danger"}">
					${message}
				</div>
			`;
			this.openModal(resultModalId);
		} else {
			alert(message);
		}
	}

	cleanup() {
		if (this.uploadForm) {
			this.uploadForm.removeEventListener("submit", this._onSubmit);
		}
	}
}

class UploadCaptureModalController extends ModalManager {
	constructor(options = {}) {
		super();
		this.options = options;

		this.isProcessing = false;
		this.uploadInProgress = false;
		this.cancelRequested = false;
		this.currentAbortController = null;

		this.uploadModal = null;
		this.cancelButton = null;
		this.closeButton = null;
		this.submitButton = null;
		this.fileInput = null;

		this._beforeUnloadHandler = null;
		this._visibilityHandler = null;
	}

	init() {
		this.uploadModal = document.getElementById(
			this.options.uploadModalId || "uploadCaptureModal",
		);
		if (!this.uploadModal) {
			console.warn("uploadCaptureModal not found");
			return;
		}

		this.cancelButton =
			this.uploadModal.querySelector(this.options.cancelButtonSelector) ||
			this.uploadModal.querySelector(".btn-secondary");
		this.closeButton =
			this.uploadModal.querySelector(this.options.closeButtonSelector) ||
			this.uploadModal.querySelector(".btn-close");
		this.submitButton = document.getElementById(
			this.options.submitButtonId || "uploadSubmitBtn",
		);
		this.fileInput = document.getElementById(
			this.options.fileInputId || "captureFileInput",
		);

		if (!this.cancelButton || !this.closeButton || !this.submitButton) {
			console.warn("Required buttons not found in upload modal");
			return;
		}

		this.clearExistingResultModal();
		this.clearUploadSessionStorage();
		this.addBeforeUnloadGuard();
		this.addVisibilityListener();
		this.addModalStateResetHandlers();
		this.addCancelHandlers();
		this.addSubmitHandler();
		this.addFileSelectionHandler();
	}

	clearExistingResultModal() {
		const resultModalId = "uploadResultModal";
		const existingResultModal = document.getElementById(resultModalId);
		if (!existingResultModal) return;
		this.closeModal(resultModalId);
	}

	clearUploadSessionStorage() {
		try {
			if (sessionStorage.getItem("uploadInProgress")) {
				sessionStorage.removeItem("uploadInProgress");
			}
		} catch (_) {}
	}

	addBeforeUnloadGuard() {
		if (this._beforeUnloadHandler) {
			window.removeEventListener("beforeunload", this._beforeUnloadHandler);
		}
		this._beforeUnloadHandler = (e) => {
			let inProgress = false;
			try {
				inProgress =
					this.isProcessing ||
					this.uploadInProgress ||
					Boolean(sessionStorage.getItem("uploadInProgress"));
			} catch (_) {
				inProgress = this.isProcessing || this.uploadInProgress;
			}
			if (!inProgress) return;
			e.preventDefault();
			e.returnValue =
				"Upload in progress will be aborted. Are you sure you want to leave?";
			return e.returnValue;
		};
		window.addEventListener("beforeunload", this._beforeUnloadHandler);
	}

	addVisibilityListener() {
		if (this._visibilityHandler) {
			document.removeEventListener("visibilitychange", this._visibilityHandler);
		}
		this._visibilityHandler = () => {
			// Preserve legacy behavior (no-op but keeps a hook if needed later)
			if (document.visibilityState === "hidden" && this.uploadInProgress) {
				// page hidden during upload
			}
		};
		document.addEventListener("visibilitychange", this._visibilityHandler);
	}

	addModalStateResetHandlers() {
		this.uploadModal.addEventListener("show.bs.modal", () => {
			this.isProcessing = false;
			this.currentAbortController = null;
		});
		this.uploadModal.addEventListener("hidden.bs.modal", () => {
			this.isProcessing = false;
			this.currentAbortController = null;
		});
	}

	addFileSelectionHandler() {
		if (!this.fileInput) return;
		this.fileInput.addEventListener("change", () => {
			this.isProcessing = false;
			this.currentAbortController = null;
		});
	}

	addCancelHandlers() {
		this.cancelButton.addEventListener("click", () => {
			this.handleCancellation("cancel");
		});
		this.closeButton.addEventListener("click", () => {
			this.handleCancellation("close");
		});
	}

	addSubmitHandler() {
		const uploadForm = document.getElementById(
			this.options.uploadFormId || "uploadCaptureForm",
		);
		if (!uploadForm) return;

		uploadForm.addEventListener("submit", async (e) => {
			e.preventDefault();

			this.isProcessing = true;
			this.uploadInProgress = true;
			this.cancelRequested = false;
			try {
				sessionStorage.setItem("uploadInProgress", "true");
			} catch (_) {}

			try {
				if (!window.selectedFiles || window.selectedFiles.length === 0) {
					alert("Please select files to upload.");
					return;
				}

				const files = window.selectedFiles;

				if (this.checkForLargeFiles(files, this.cancelButton, this.submitButton)) {
					return;
				}

				await this.checkFilesForDuplicates(files);

				const { filesToUpload, relativePathsToUpload, allRelativePaths, skippedFilesCount } =
					this.partitionFilesForUpload(files);

				const uploadResults = await this.uploadFilesInChunks(
					filesToUpload,
					relativePathsToUpload,
					allRelativePaths,
					filesToUpload.length,
				);

				this.currentAbortController = null;

				this.showUploadResults(
					uploadResults,
					uploadResults.saved_files_count,
					files.length,
					skippedFilesCount,
				);
			} catch (error) {
				if (this.cancelRequested) {
					if (!this.uploadInProgress) {
						// cancelled during duplicate checking; legacy flow already alerted
					} else {
						alert(
							"Upload cancelled. Any files uploaded before cancellation have been saved.",
						);
						setTimeout(() => window.location.reload(), 1000);
					}
				} else if (error?.name === "AbortError") {
					alert(
						"Upload was interrupted. Any files uploaded before the interruption have been saved.",
					);
					setTimeout(() => window.location.reload(), 1000);
				} else if (
					error?.name === "TypeError" &&
					String(error?.message || "").includes("fetch")
				) {
					let shouldSuppress = false;
					try {
						shouldSuppress =
							this.uploadInProgress || Boolean(sessionStorage.getItem("uploadInProgress"));
					} catch (_) {}
					if (!shouldSuppress) {
						alert(
							"Network error during upload. Please check your connection and try again.",
						);
					}
				} else {
					alert(`Upload failed: ${error?.message || "Unknown error"}`);
					setTimeout(() => window.location.reload(), 1000);
				}
			} finally {
				this.resetUIState();
			}
		});
	}

	partitionFilesForUpload(files) {
		const filesToUpload = [];
		const relativePathsToUpload = [];
		const allRelativePaths = [];
		let skippedFilesCount = 0;

		for (const file of files) {
			const directory = UploadUtils.getDirectoryPathFromFile(file);

			const fileKey = `${directory}/${file.name}`;
			const relativePath = file.webkitRelativePath || file.name;

			allRelativePaths.push(relativePath);

			if (!window.filesToSkip?.has?.(fileKey)) {
				filesToUpload.push(file);
				relativePathsToUpload.push(relativePath);
			} else {
				skippedFilesCount++;
			}
		}

		return { filesToUpload, relativePathsToUpload, allRelativePaths, skippedFilesCount };
	}

	/**
	 * @param {File[]} files
	 * @param {HTMLElement} cancelButton
	 * @param {HTMLElement} submitButton
	 * @returns {boolean} true if large files blocked flow
	 */
	checkForLargeFiles(files, cancelButton, submitButton) {
		const progressSection = document.getElementById("checkingProgressSection");
		const LARGE_FILE_THRESHOLD = 512 * 1024 * 1024; // 512MB
		const largeFiles = (files || []).filter(
			(file) => file && file.size > LARGE_FILE_THRESHOLD,
		);

		if (largeFiles.length === 0) return false;

		if (progressSection) progressSection.style.display = "none";
		if (cancelButton) {
			cancelButton.textContent = "Cancel";
			cancelButton.classList.remove("btn-warning");
			cancelButton.disabled = false;
		}
		if (submitButton) submitButton.disabled = false;

		const largeFileNames = largeFiles.map((file) => file.name).join(", ");
		const alertMessage = `Large files detected (over 512MB): ${largeFileNames}\n\nPlease:\n1. Skip these large files and upload the remaining files, or\n2. Use the SpectrumX SDK (https://pypi.org/project/spectrumx/) to upload large files and add them to your capture.\n\nLarge files may cause issues with the web interface.`;
		alert(alertMessage);
		return true;
	}

	getCSRFToken() {
		if (window.APIClient) {
			try {
				return new window.APIClient().getCSRFToken();
			} catch (_) {}
		}
		const token = document.querySelector("[name=csrfmiddlewaretoken]");
		return token ? token.value : "";
	}

	async checkFilesForDuplicates(files) {
		const progressSection = document.getElementById("checkingProgressSection");
		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");
		const progressMessage = document.getElementById("progressMessage");

		if (progressSection) progressSection.style.display = "block";
		if (progressMessage) progressMessage.textContent = "Processing files for upload...";

		if (this.cancelButton) this.cancelButton.textContent = "Cancel Processing";
		if (this.submitButton) this.submitButton.disabled = true;

		window.filesToSkip = new Set();
		window.fileCheckResults = new Map();

		const csrfToken = this.getCSRFToken();
		if (!csrfToken) {
			throw new Error("CSRF token not found");
		}

		const totalFiles = files.length;
		const checkFileUrl =
			document.querySelector("[data-check-file-url]")?.dataset?.checkFileUrl ||
			"/users/check-file-exists/";

		for (let i = 0; i < files.length; i++) {
			const file = files[i];

			const progress = Math.round(((i + 1) / totalFiles) * 100);
			if (progressBar) progressBar.style.width = `${progress}%`;
			if (progressText) progressText.textContent = `${progress}%`;

			const hashHex = await UploadUtils.calculateBlake3Hash(file);
			const directory = UploadUtils.getDirectoryPathFromFile(file);

			try {
				const data = await UploadUtils.checkFileExistsOnServer(
					file,
					hashHex,
					csrfToken,
					checkFileUrl,
				);

				const fileKey = `${directory}/${file.name}`;
				window.fileCheckResults.set(fileKey, {
					file,
					directory,
					filename: file.name,
					checksum: hashHex,
					data: data.data,
				});
				if (data?.data?.file_exists_in_tree === true) {
					window.filesToSkip.add(fileKey);
				}
			} catch (error) {
				console.error("Error checking file:", error);
			}

			if (this.cancelRequested) {
				break;
			}
		}

		if (progressSection) progressSection.style.display = "none";

		if (this.cancelRequested) {
			if (progressSection) progressSection.style.display = "none";
			await new Promise((resolve) => setTimeout(resolve, 100));
			alert("Processing cancelled. No files were uploaded.");
			throw new Error("Upload cancelled by user");
		}
	}

	async handleSkippedFilesUpload(allRelativePaths, abortController) {
		const skippedFormData = new FormData();
		for (const path of allRelativePaths) {
			skippedFormData.append("all_relative_paths", path);
		}

		UploadUtils.appendCaptureTypeToFormData(skippedFormData);

		const uploadUrl =
			document.querySelector("[data-upload-url]")?.dataset?.uploadUrl ||
			"/users/upload-capture/";
		const csrfToken = this.getCSRFToken();

		const response = await fetch(uploadUrl, {
			method: "POST",
			headers: { "X-CSRFToken": csrfToken },
			body: skippedFormData,
			signal: abortController.signal,
		});
		return await response.json();
	}

	calculateTotalChunks(filesToUpload, chunkSizeBytes) {
		return UploadUtils.calculateTotalChunks(filesToUpload, chunkSizeBytes);
	}

	async uploadChunk({
		chunk,
		chunkPaths,
		chunkNum,
		totalChunks,
		filesProcessed,
		isFinalChunk,
		allResults,
		allRelativePaths,
		totalFiles,
		chunkSizeBytes,
	}) {
		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");
		const progressMessage = document.getElementById("progressMessage");

		const progress = Math.round((filesProcessed / totalFiles) * 100);
		if (progressBar) progressBar.style.width = `${progress}%`;
		if (progressText) progressText.textContent = `${progress}%`;

		if (progressMessage) {
			if (chunk.length === 1 && chunk[0].size > chunkSizeBytes) {
				const file = chunk[0];
				progressMessage.textContent = `Uploading large file: ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB)...`;
			} else {
				progressMessage.textContent = `Uploading chunk ${chunkNum}/${totalChunks} (${filesProcessed} files processed)...`;
			}
		}

		const chunkFormData = new FormData();
		for (const file of chunk) chunkFormData.append("files", file);
		for (const path of chunkPaths) chunkFormData.append("relative_paths", path);
		for (const path of allRelativePaths)
			chunkFormData.append("all_relative_paths", path);

		UploadUtils.appendCaptureTypeToFormData(chunkFormData);

		chunkFormData.append("is_chunk", "true");
		chunkFormData.append("chunk_number", String(chunkNum));
		chunkFormData.append("total_chunks", String(totalChunks));

		if (this.cancelRequested) {
			throw new Error("Upload cancelled by user");
		}

		const controller = new AbortController();
		this.currentAbortController = controller;

		const MIN_AVG_UPLOAD_RATE = 100 * 1024; // 100KB/s
		const MIN_TIMEOUT_MS = 30000;
		const totalChunkBytes = chunk.reduce((t, f) => t + f.size, 0);
		const calculatedTimeout = (totalChunkBytes / MIN_AVG_UPLOAD_RATE) * 1000;
		const timeout = Math.max(calculatedTimeout, MIN_TIMEOUT_MS);
		const timeoutId = setTimeout(() => controller.abort(), timeout);

		const uploadUrl =
			document.querySelector("[data-upload-url]")?.dataset?.uploadUrl ||
			"/users/upload-capture/";
		const csrfToken = this.getCSRFToken();

		let response;
		let chunkResult;
		try {
			response = await fetch(uploadUrl, {
				method: "POST",
				headers: { "X-CSRFToken": csrfToken },
				body: chunkFormData,
				signal: controller.signal,
			});
			clearTimeout(timeoutId);
			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: ${response.statusText}`);
			}
			chunkResult = await response.json();
		} catch (error) {
			clearTimeout(timeoutId);
			if (error?.name === "AbortError") {
				throw new Error("Upload timeout - connection may be lost");
			}
			throw error;
		}

		if (chunkResult.saved_files_count !== undefined) {
			allResults.saved_files_count += chunkResult.saved_files_count;
		}
		if (chunkResult.captures && isFinalChunk) {
			allResults.captures = allResults.captures.concat(chunkResult.captures);
		}
		if (chunkResult.message && isFinalChunk) {
			allResults.message = chunkResult.message;
		}
		if (chunkResult.errors) {
			allResults.errors = allResults.errors.concat(chunkResult.errors);
		}

		if (chunkResult.file_upload_status === "error") {
			allResults.file_upload_status = "error";
			allResults.message = chunkResult.message || "Upload failed";
			if (progressMessage) {
				progressMessage.textContent =
					"Upload aborted due to errors. Please check the results.";
			}
			throw new Error(`Upload failed: ${chunkResult.message}`);
		}
		if (chunkResult.file_upload_status === "success" && isFinalChunk) {
			allResults.file_upload_status = "success";
		}
	}

	async uploadFilesInChunks(
		filesToUpload,
		relativePathsToUpload,
		allRelativePaths,
		totalFiles,
	) {
		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");
		const progressMessage = document.getElementById("progressMessage");
		const progressSection = document.getElementById("checkingProgressSection");

		if (filesToUpload.length > 0) {
			if (progressSection) progressSection.style.display = "block";
			if (progressMessage)
				progressMessage.textContent = "Uploading files and creating captures...";
			if (progressBar) progressBar.style.width = "0%";
			if (progressText) progressText.textContent = "0%";
		}

		const abortController = new AbortController();
		this.currentAbortController = abortController;

		const CHUNK_SIZE_BYTES = 50 * 1024 * 1024;

		let allResults = {
			file_upload_status: "success",
			saved_files_count: 0,
			captures: [],
			errors: [],
			message: "",
		};

		if (filesToUpload.length === 0) {
			allResults = await this.handleSkippedFilesUpload(
				allRelativePaths,
				abortController,
			);
		} else {
			let currentChunk = [];
			let currentChunkPaths = [];
			let currentChunkSize = 0;
			let chunkNumber = 1;
			let filesProcessed = 0;

			const totalChunks = this.calculateTotalChunks(
				filesToUpload,
				CHUNK_SIZE_BYTES,
			);

			for (let i = 0; i < filesToUpload.length; i++) {
				const file = filesToUpload[i];
				const filePath = relativePathsToUpload[i];

				if (
					currentChunkSize + file.size > CHUNK_SIZE_BYTES &&
					currentChunk.length > 0
				) {
					await this.uploadChunk({
						chunk: currentChunk,
						chunkPaths: currentChunkPaths,
						chunkNum: chunkNumber,
						totalChunks,
						filesProcessed,
						isFinalChunk: false,
						allResults,
						allRelativePaths,
						totalFiles,
						chunkSizeBytes: CHUNK_SIZE_BYTES,
					});
					currentChunk = [];
					currentChunkPaths = [];
					currentChunkSize = 0;
					chunkNumber++;
				}

				currentChunk.push(file);
				currentChunkPaths.push(filePath);
				currentChunkSize += file.size;
				filesProcessed++;

				if (i === filesToUpload.length - 1) {
					await this.uploadChunk({
						chunk: currentChunk,
						chunkPaths: currentChunkPaths,
						chunkNum: chunkNumber,
						totalChunks,
						filesProcessed,
						isFinalChunk: true,
						allResults,
						allRelativePaths,
						totalFiles,
						chunkSizeBytes: CHUNK_SIZE_BYTES,
					});
				}

				if (this.cancelRequested) break;
			}
		}

		if (this.cancelRequested) {
			await new Promise((resolve) => setTimeout(resolve, 100));
			throw new Error("Upload cancelled by user");
		}

		if (allResults.file_upload_status === "error") {
			this.currentAbortController = null;
			this.showUploadResults(allResults, allResults.saved_files_count, totalFiles);
			return allResults;
		}

		this.currentAbortController = null;
		return allResults;
	}

	resetUIState() {
		if (this.submitButton) this.submitButton.disabled = false;

		const progressSection = document.getElementById("checkingProgressSection");
		if (progressSection) progressSection.style.display = "none";

		if (this.cancelButton) {
			this.cancelButton.textContent = "Cancel";
			this.cancelButton.classList.remove("btn-warning");
			this.cancelButton.disabled = false;
		}

		if (this.closeButton) {
			this.closeButton.disabled = false;
			this.closeButton.style.opacity = "1";
		}

		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");
		const progressMessage = document.getElementById("progressMessage");
		if (progressBar) progressBar.style.width = "0%";
		if (progressText) progressText.textContent = "0%";
		if (progressMessage) progressMessage.textContent = "";

		this.isProcessing = false;
		this.uploadInProgress = false;
		this.cancelRequested = false;
		try {
			sessionStorage.removeItem("uploadInProgress");
		} catch (_) {}
		this.currentAbortController = null;
	}

	/**
	 * @param {string} buttonType
	 */
	handleCancellation(buttonType) {
		if (!this.isProcessing) return;
		this.cancelRequested = true;
		if (this.currentAbortController) {
			this.currentAbortController.abort();
		}

		if (buttonType === "cancel") {
			this.cancelButton.textContent = "Cancelling...";
			this.cancelButton.disabled = true;
		} else if (buttonType === "close") {
			this.closeButton.disabled = true;
			this.closeButton.style.opacity = "0.5";
		}

		const progressMessage = document.getElementById("progressMessage");
		if (progressMessage) {
			progressMessage.textContent = "Cancelling upload...";
		}

		setTimeout(() => {
			if (this.cancelRequested) {
				this.resetUIState();
			}
		}, 500);
	}

	showUploadResults(result, uploadedCount, totalCount, skippedCount = 0) {
		if (!this.uploadInProgress && result?.file_upload_status === "error") {
			this.resetUIState();
			return;
		}

		const resultModalId = "uploadResultModal";
		const modalBody = document.getElementById("uploadResultModalBody");
		const resultModalEl = document.getElementById(resultModalId);
		if (!modalBody || !resultModalEl) {
			return;
		}

		const uploadCaptureModalId = "uploadCaptureModal";
		const captureModalEl = document.getElementById(uploadCaptureModalId);
		if (captureModalEl) {
			this.closeModal(uploadCaptureModalId);
		}

		let msg = "";
		if (result.file_upload_status === "success") {
			if (uploadedCount === 0 && totalCount > 0) {
				msg = `<b>Upload complete!</b><br />All ${totalCount} files already existed on the server.`;
			} else if (skippedCount > 0) {
				msg = `<b>Upload complete!</b><br />Files uploaded: <strong>${uploadedCount}</strong> / ${totalCount}`;
				msg += `<br />Files already exist: <strong>${skippedCount}</strong>`;
			} else {
				msg = `<b>Upload complete!</b><br />Files uploaded: <strong>${uploadedCount}</strong> / ${totalCount}`;
			}

			if (result.captures && result.captures.length > 0) {
				const uuids = result.captures
					.map((uuid) => `<li>${uuid}</li>`)
					.join("");
				msg += `<br />Created capture UUID(s):<ul>${uuids}</ul>`;
			}

			if (result.errors && result.errors.length > 0) {
				const errs = result.errors.map((e) => `<li>${e}</li>`).join("");
				msg += `<br /><b>Errors:</b><ul>${errs}</ul>`;
				msg += "<br /><b>Please check details and upload again.</b>";
			}
		} else {
			msg = "<b>Upload Failed</b><br />";
			if (result.message) {
				msg += `${result.message}<br /><br />`;
			}
			msg += "<b>Please check file validity and try again.</b>";
			if (result.errors && result.errors.length > 0) {
				const errs = result.errors.map((e) => `<li>${e}</li>`).join("");
				msg += `<br /><br /><b>Error Details:</b><ul>${errs}</ul>`;
			}
		}

		modalBody.innerHTML = msg;
		this.openModal(resultModalId);

		if (result.file_upload_status === "success") {
			resultModalEl.addEventListener(
				"hidden.bs.modal",
				() => {
					window.location.reload();
				},
				{ once: true },
			);
		}
	}
}


if (typeof window !== "undefined") {
	window.UploadManager = UploadManager;
	window.CaptureTypeSelector = CaptureTypeSelector;
	window.FileUploadHandler = FileUploadHandler;
	window.UploadCaptureModalController = UploadCaptureModalController;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		UploadManager,
		CaptureTypeSelector,
		FileUploadHandler,
		UploadCaptureModalController,
	};
}

if (typeof window !== "undefined") {
	const isNodeTestEnv =
		typeof process !== "undefined" &&
		process.env &&
		process.env.NODE_ENV === "test";
	if (!isNodeTestEnv) {
		document.addEventListener("DOMContentLoaded", () => {
			new UploadManager();
		});
	}
}
