/**
 * Files Upload Handler
 * Manages file upload functionality, BLAKE3 hashing, and progress tracking
 */

/**
 * BLAKE3 File Handler
 * Manages file selection and BLAKE3 hash calculation for deduplication
 */
class Blake3FileHandler {
	constructor() {
		// Initialize global variables for file tracking
		this.initializeGlobalVariables();
		this.setupEventListeners();
	}

	initializeGlobalVariables() {
		// Global variables to track files that should be skipped
		window.filesToSkip = new Set();
		window.fileCheckResults = new Map(); // Store detailed results for each file
	}

	setupEventListeners() {
		const modal = document.getElementById("uploadCaptureModal");
		if (!modal) {
			console.warn("uploadCaptureModal not found");
			return;
		}

		modal.addEventListener("shown.bs.modal", () => {
			this.setupFileInputHandler();
		});
	}

	setupFileInputHandler() {
		const fileInput = document.getElementById("captureFileInput");
		if (!fileInput) {
			console.warn("captureFileInput not found");
			return;
		}

		// Remove any previous handler to avoid duplicates
		if (window._blake3CaptureHandler) {
			fileInput.removeEventListener("change", window._blake3CaptureHandler);
		}

		// Create file handler that stores selected files
		window._blake3CaptureHandler = async (event) => {
			await this.handleFileSelection(event);
		};

		fileInput.addEventListener("change", window._blake3CaptureHandler);
	}

	async handleFileSelection(event) {
		const files = event.target.files;
		if (!files || files.length === 0) {
			return;
		}

		// Store the selected files for later processing
		window.selectedFiles = Array.from(files);

		console.log(`Selected ${files.length} files for upload`);
	}

	/**
	 * Calculate BLAKE3 hash for a file
	 * @param {File} file - The file to hash
	 * @returns {Promise<string>} - The BLAKE3 hash in hex format
	 */
	async calculateBlake3Hash(file) {
		try {
			const buffer = await file.arrayBuffer();
			const hasher = await hashwasm.createBLAKE3();
			hasher.init();
			hasher.update(new Uint8Array(buffer));
			return hasher.digest("hex");
		} catch (error) {
			console.error("Error calculating BLAKE3 hash:", error);
			throw error;
		}
	}

	/**
	 * Get directory path from webkitRelativePath
	 * @param {File} file - The file to get directory for
	 * @returns {string} - The directory path
	 */
	getDirectoryPath(file) {
		if (!file.webkitRelativePath) {
			return "/";
		}

		const pathParts = file.webkitRelativePath.split("/");
		if (pathParts.length > 1) {
			pathParts.pop(); // Remove filename
			return `/${pathParts.join("/")}`;
		}

		return "/";
	}

	/**
	 * Check if a file exists on the server
	 * @param {File} file - The file to check
	 * @param {string} hash - The BLAKE3 hash of the file
	 * @returns {Promise<Object>} - The server response
	 */
	async checkFileExists(file, hash) {
		const directory = this.getDirectoryPath(file);

		const checkData = {
			directory: directory,
			filename: file.name,
			checksum: hash,
		};

		try {
			const response = await fetch(window.checkFileExistsUrl, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": window.csrfToken,
				},
				body: JSON.stringify(checkData),
			});

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: ${response.statusText}`);
			}

			return await response.json();
		} catch (error) {
			console.error("Error checking file existence:", error);
			throw error;
		}
	}

	/**
	 * Process a single file for duplicate checking
	 * @param {File} file - The file to process
	 * @returns {Promise<Object>} - Processing result
	 */
	async processFileForDuplicateCheck(file) {
		try {
			// Calculate hash
			const hash = await this.calculateBlake3Hash(file);

			// Check if file exists
			const checkResult = await this.checkFileExists(file, hash);

			// Store results
			const directory = this.getDirectoryPath(file);
			const fileKey = `${directory}/${file.name}`;

			const result = {
				file: file,
				directory: directory,
				filename: file.name,
				checksum: hash,
				data: checkResult.data,
			};

			window.fileCheckResults.set(fileKey, result);

			// Mark for skipping if file exists
			if (checkResult.data && checkResult.data.file_exists_in_tree === true) {
				window.filesToSkip.add(fileKey);
			}

			return result;
		} catch (error) {
			console.error("Error processing file for duplicate check:", error);
			return null;
		}
	}
}

/**
 * Files Upload Modal Handler
 * Manages file upload functionality, progress tracking, and chunked uploads
 */
class FilesUploadModal {
	constructor() {
		this.isProcessing = false;
		this.uploadInProgress = false;
		this.cancelRequested = false;
		this.currentAbortController = null;

		this.initializeElements();
		this.setupEventListeners();
		this.clearExistingModals();
	}

	initializeElements() {
		this.cancelButton = document.querySelector(
			"#uploadCaptureModal .btn-secondary",
		);
		this.submitButton = document.getElementById("uploadSubmitBtn");
		this.uploadModal = document.getElementById("uploadCaptureModal");
		this.fileInput = document.getElementById("captureFileInput");
		this.uploadForm = document.getElementById("uploadCaptureForm");
	}

	setupEventListeners() {
		// Modal event listeners
		if (this.uploadModal) {
			this.uploadModal.addEventListener("show.bs.modal", () =>
				this.resetState(),
			);
			this.uploadModal.addEventListener("hidden.bs.modal", () =>
				this.resetState(),
			);
		}

		// File input change listener
		if (this.fileInput) {
			this.fileInput.addEventListener("change", () => this.resetState());
		}

		// Cancel button listener
		if (this.cancelButton) {
			this.cancelButton.addEventListener("click", () => this.handleCancel());
		}

		// Form submit listener
		if (this.uploadForm) {
			this.uploadForm.addEventListener("submit", (e) => this.handleSubmit(e));
		}
	}

	clearExistingModals() {
		const existingResultModal = document.getElementById("uploadResultModal");
		if (existingResultModal) {
			const modalInstance = bootstrap.Modal.getInstance(existingResultModal);
			if (modalInstance) {
				modalInstance.hide();
			}
		}
	}

	resetState() {
		this.isProcessing = false;
		this.currentAbortController = null;
		this.cancelRequested = false;
	}

	handleCancel() {
		if (this.isProcessing) {
			this.cancelRequested = true;

			if (this.currentAbortController) {
				this.currentAbortController.abort();
			}

			this.cancelButton.textContent = "Cancelling...";
			this.cancelButton.disabled = true;

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
	}

	async handleSubmit(e) {
		e.preventDefault();

		this.isProcessing = true;
		this.uploadInProgress = true;
		this.cancelRequested = false;

		// Check if files are selected
		if (!window.selectedFiles || window.selectedFiles.length === 0) {
			alert("Please select files to upload.");
			return;
		}

		try {
			this.showProgressSection();
			await this.checkFilesForDuplicates();

			if (this.cancelRequested) {
				throw new Error("Upload cancelled by user");
			}

			await this.uploadFiles();
		} catch (error) {
			this.handleError(error);
		} finally {
			this.resetUIState();
		}
	}

	showProgressSection() {
		const progressSection = document.getElementById("checkingProgressSection");
		const progressMessage = document.getElementById("progressMessage");

		if (progressSection) {
			progressSection.style.display = "block";
		}
		if (progressMessage) {
			progressMessage.textContent = "Checking files for duplicates...";
		}

		this.cancelButton.textContent = "Cancel Processing";
		this.cancelButton.classList.add("btn-warning");
		this.submitButton.disabled = true;
	}

	async checkFilesForDuplicates() {
		window.filesToSkip = new Set();
		window.fileCheckResults = new Map();
		const files = window.selectedFiles;
		const totalFiles = files.length;

		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");

		for (let i = 0; i < files.length; i++) {
			if (this.cancelRequested) break;

			const file = files[i];
			const progress = Math.round(((i + 1) / totalFiles) * 100);

			if (progressBar) progressBar.style.width = `${progress}%`;
			if (progressText) progressText.textContent = `${progress}%`;

			await this.processFile(file);
		}

		if (this.cancelRequested) {
			throw new Error("Upload cancelled by user");
		}
	}

	async processFile(file) {
		// Calculate BLAKE3 hash
		const buffer = await file.arrayBuffer();
		const hasher = await hashwasm.createBLAKE3();
		hasher.init();
		hasher.update(new Uint8Array(buffer));
		const hashHex = hasher.digest("hex");

		// Calculate directory path
		let directory = "/";
		if (file.webkitRelativePath) {
			const pathParts = file.webkitRelativePath.split("/");
			if (pathParts.length > 1) {
				pathParts.pop();
				directory = `/${pathParts.join("/")}`;
			}
		}

		// Check if file exists
		const checkData = {
			directory: directory,
			filename: file.name,
			checksum: hashHex,
		};

		try {
			const response = await fetch(window.checkFileExistsUrl, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": window.csrfToken,
				},
				body: JSON.stringify(checkData),
			});
			const data = await response.json();

			const fileKey = `${directory}/${file.name}`;
			window.fileCheckResults.set(fileKey, {
				file: file,
				directory: directory,
				filename: file.name,
				checksum: hashHex,
				data: data.data,
			});

			if (data.data && data.data.file_exists_in_tree === true) {
				window.filesToSkip.add(fileKey);
			}
		} catch (error) {
			console.error("Error checking file:", error);
		}
	}

	async uploadFiles() {
		const progressMessage = document.getElementById("progressMessage");
		const progressSection = document.getElementById("checkingProgressSection");
		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");

		if (progressMessage) {
			progressMessage.textContent = "Uploading files and creating captures...";
		}
		if (progressBar) progressBar.style.width = "0%";
		if (progressText) progressText.textContent = "0%";

		const files = window.selectedFiles;
		const filesToUpload = [];
		const relativePathsToUpload = [];
		const allRelativePaths = [];

		// Process files for upload
		for (const file of files) {
			let directory = "/";
			if (file.webkitRelativePath) {
				const pathParts = file.webkitRelativePath.split("/");
				if (pathParts.length > 1) {
					pathParts.pop();
					directory = `/${pathParts.join("/")}`;
				}
			}
			const fileKey = `${directory}/${file.name}`;
			const relativePath = file.webkitRelativePath || file.name;

			console.debug(
				`Processing file: ${file.name}, webkitRelativePath: '${file.webkitRelativePath}', relativePath: '${relativePath}', directory: '${directory}'`,
			);
			allRelativePaths.push(relativePath);

			if (!window.filesToSkip.has(fileKey)) {
				filesToUpload.push(file);
				relativePathsToUpload.push(relativePath);
			}
		}

		console.debug(
			"All relative paths being sent:",
			allRelativePaths.slice(0, 5),
		);
		console.debug(
			"Relative paths to upload:",
			relativePathsToUpload.slice(0, 5),
		);

		if (filesToUpload.length > 0 && progressSection) {
			progressSection.style.display = "block";
		}

		this.currentAbortController = new AbortController();

		let result;
		if (filesToUpload.length === 0) {
			result = await this.uploadSkippedFiles(allRelativePaths);
		} else {
			result = await this.uploadFilesInChunks(
				filesToUpload,
				relativePathsToUpload,
				allRelativePaths,
			);
		}

		this.currentAbortController = null;
		this.showUploadResults(result, result.saved_files_count, files.length);
	}

	async uploadSkippedFiles(allRelativePaths) {
		const formData = new FormData();

		console.debug(
			"uploadSkippedFiles - allRelativePaths:",
			allRelativePaths.slice(0, 5),
		);
		for (const path of allRelativePaths) {
			formData.append("all_relative_paths", path);
		}

		this.addCaptureTypeData(formData);

		const response = await fetch(window.uploadFilesUrl, {
			method: "POST",
			body: formData,
			signal: this.currentAbortController.signal,
		});

		return await response.json();
	}

	async uploadFilesInChunks(
		filesToUpload,
		relativePathsToUpload,
		allRelativePaths,
	) {
		const CHUNK_SIZE = 5;
		const totalFiles = filesToUpload.length;
		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");
		const progressMessage = document.getElementById("progressMessage");

		const allResults = {
			file_upload_status: "success",
			saved_files_count: 0,
			captures: [],
			errors: [],
			message: "",
		};

		for (let i = 0; i < filesToUpload.length; i += CHUNK_SIZE) {
			if (this.cancelRequested) break;

			const chunk = filesToUpload.slice(i, i + CHUNK_SIZE);
			const chunkPaths = relativePathsToUpload.slice(i, i + CHUNK_SIZE);

			const totalChunks = Math.ceil(filesToUpload.length / CHUNK_SIZE);
			const currentChunk = Math.floor(i / CHUNK_SIZE) + 1;
			const isFinalChunk = currentChunk === totalChunks;

			// Update progress
			const progress = Math.round(((i + chunk.length) / totalFiles) * 100);
			if (progressBar) progressBar.style.width = `${progress}%`;
			if (progressText) progressText.textContent = `${progress}%`;
			if (progressMessage) {
				progressMessage.textContent = `Uploading files ${i + 1}-${Math.min(i + CHUNK_SIZE, totalFiles)} of ${totalFiles} (chunk ${currentChunk}/${totalChunks})...`;
			}

			const chunkResult = await this.uploadChunk(
				chunk,
				chunkPaths,
				allRelativePaths,
				currentChunk,
				totalChunks,
			);

			// Merge results
			if (chunkResult.saved_files_count !== undefined) {
				allResults.saved_files_count += chunkResult.saved_files_count;
			}
			if (chunkResult.captures && isFinalChunk) {
				allResults.captures = allResults.captures.concat(chunkResult.captures);
			}
			if (chunkResult.errors) {
				allResults.errors = allResults.errors.concat(chunkResult.errors);
			}

			if (chunkResult.file_upload_status === "error") {
				allResults.file_upload_status = "error";
				allResults.message = chunkResult.message || "Upload failed";
				break;
			}

			if (chunkResult.file_upload_status === "success" && isFinalChunk) {
				allResults.file_upload_status = "success";
			}
		}

		if (this.cancelRequested) {
			throw new Error("Upload cancelled by user");
		}

		return allResults;
	}

	async uploadChunk(
		chunk,
		chunkPaths,
		allRelativePaths,
		currentChunk,
		totalChunks,
	) {
		const formData = new FormData();

		console.debug(
			`uploadChunk ${currentChunk}/${totalChunks} - chunkPaths:`,
			chunkPaths,
		);
		console.debug(
			`uploadChunk ${currentChunk}/${totalChunks} - allRelativePaths (first 5):`,
			allRelativePaths.slice(0, 5),
		);

		for (const file of chunk) {
			formData.append("files", file);
		}
		for (const path of chunkPaths) {
			formData.append("relative_paths", path);
		}
		for (const path of allRelativePaths) {
			formData.append("all_relative_paths", path);
		}

		this.addCaptureTypeData(formData);

		formData.append("is_chunk", "true");
		formData.append("chunk_number", currentChunk.toString());
		formData.append("total_chunks", totalChunks.toString());

		const controller = new AbortController();
		this.currentAbortController = controller;
		const timeoutId = setTimeout(() => controller.abort(), 300000);

		try {
			const response = await fetch(window.uploadFilesUrl, {
				method: "POST",
				body: formData,
				signal: controller.signal,
			});

			clearTimeout(timeoutId);

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: ${response.statusText}`);
			}

			return await response.json();
		} catch (error) {
			clearTimeout(timeoutId);
			if (error.name === "AbortError") {
				throw new Error("Upload timeout - connection may be lost");
			}
			throw error;
		}
	}

	addCaptureTypeData(formData) {
		const captureType = document.getElementById("captureTypeSelect").value;
		formData.append("capture_type", captureType);

		if (captureType === "drf") {
			const channels = document.getElementById("captureChannelsInput").value;
			formData.append("channels", channels);
		} else if (captureType === "rh") {
			const scanGroup = document.getElementById("captureScanGroupInput").value;
			formData.append("scan_group", scanGroup);
		}
	}

	handleError(error) {
		if (this.cancelRequested) {
			alert(
				"Upload cancelled. Any files uploaded before cancellation have been saved.",
			);
			setTimeout(() => window.location.reload(), 1000);
		} else if (error.name === "AbortError") {
			alert(
				"Upload was interrupted. Any files uploaded before the interruption have been saved.",
			);
			setTimeout(() => window.location.reload(), 1000);
		} else if (error.name === "TypeError" && error.message.includes("fetch")) {
			alert(
				"Network error during upload. Please check your connection and try again.",
			);
		} else {
			alert(`Upload failed: ${error.message}`);
			setTimeout(() => window.location.reload(), 1000);
		}
	}

	resetUIState() {
		this.submitButton.disabled = false;

		const progressSection = document.getElementById("checkingProgressSection");
		if (progressSection) {
			progressSection.style.display = "none";
		}

		this.cancelButton.textContent = "Cancel";
		this.cancelButton.classList.remove("btn-warning");
		this.cancelButton.disabled = false;

		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");
		const progressMessage = document.getElementById("progressMessage");

		if (progressBar) progressBar.style.width = "0%";
		if (progressText) progressText.textContent = "0%";
		if (progressMessage) progressMessage.textContent = "";

		this.isProcessing = false;
		this.uploadInProgress = false;
		this.cancelRequested = false;
		this.currentAbortController = null;
	}

	showUploadResults(result, uploadedCount, totalCount) {
		const uploadModal = bootstrap.Modal.getInstance(this.uploadModal);
		if (uploadModal) {
			uploadModal.hide();
		}

		if (result.file_upload_status === "success") {
			setTimeout(() => window.location.reload(), 500);
		} else {
			this.showErrorModal(result);
		}
	}

	showErrorModal(result) {
		const modalBody = document.getElementById("uploadResultModalBody");
		const resultModalEl = document.getElementById("uploadResultModal");
		const modal = new bootstrap.Modal(resultModalEl);

		let msg = "<b>Upload Failed</b><br />";
		if (result.message) {
			msg += `${result.message}<br /><br />`;
		}
		msg += "<b>Please remove the problematic files and try again.</b>";

		if (result.errors && result.errors.length > 0) {
			const errs = result.errors.map((e) => `<li>${e}</li>`).join("");
			msg += `<br /><br /><b>Error Details:</b><ul>${errs}</ul>`;
		}

		modalBody.innerHTML = msg;
		modal.show();
	}
}

// Initialize when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
	// Set up session storage alert handling
	const key = "filesAlert";
	const stored = sessionStorage.getItem(key);
	if (stored) {
		try {
			const data = JSON.parse(stored);
			if (
				window.components &&
				typeof window.components.showError === "function" &&
				data?.type === "error"
			) {
				window.components.showError(data.message || "An error occurred.");
			} else if (
				window.components &&
				typeof window.components.showSuccess === "function" &&
				data?.type === "success"
			) {
				window.components.showSuccess(data.message || "Success");
			}
		} catch (e) {}
		sessionStorage.removeItem(key);
	}

	// Initialize BLAKE3 handler first, then upload modal
	new Blake3FileHandler();
	new FilesUploadModal();
});
