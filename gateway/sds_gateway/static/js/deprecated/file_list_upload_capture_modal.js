/* Upload Capture Modal JavaScript */

document.addEventListener("DOMContentLoaded", () => {
	// Upload Capture Modal JS
	let isProcessing = false; // Flag to track if processing is active
	// Reset cancellation state on page load
	// Add page refresh/close confirmation
	let uploadInProgress = false;

	// Clear any existing result modals on page load
	const existingResultModal = document.getElementById("uploadResultModal");
	if (existingResultModal) {
		const modalInstance = bootstrap.Modal.getInstance(existingResultModal);
		if (modalInstance) {
			modalInstance.hide();
		}
	}

	// Clear any upload-related session storage
	if (sessionStorage.getItem("uploadInProgress")) {
		sessionStorage.removeItem("uploadInProgress");
	}

	// Handle beforeunload event (page refresh/close)
	window.addEventListener("beforeunload", (e) => {
		if (
			isProcessing ||
			uploadInProgress ||
			sessionStorage.getItem("uploadInProgress")
		) {
			e.preventDefault();
			e.returnValue =
				"Upload in progress will be aborted. Are you sure you want to leave?";
			return e.returnValue;
		}
	});

	// Handle visibility change (tab close/minimize)
	document.addEventListener("visibilitychange", () => {
		if (document.visibilityState === "hidden" && uploadInProgress) {
			// Page hidden during upload
		}
	});

	// Get button references
	const uploadModal = document.getElementById("uploadCaptureModal");
	if (!uploadModal) {
		console.warn("uploadCaptureModal not found");
		return;
	}

	const cancelButton = uploadModal.querySelector(".btn-secondary");
	const closeButton = uploadModal.querySelector(".btn-close");
	const submitButton = document.getElementById("uploadSubmitBtn");

	if (!cancelButton || !closeButton || !submitButton) {
		console.warn("Required buttons not found in upload modal");
		return;
	}

	// Store abort controller reference for cancellation
	let currentAbortController = null;

	// Reset cancellation state when modal is opened
	uploadModal.addEventListener("show.bs.modal", () => {
		isProcessing = false;
		currentAbortController = null;
	});

	// Reset cancellation state when files are selected
	const fileInput = document.getElementById("captureFileInput");
	if (fileInput) {
		fileInput.addEventListener("change", () => {
			isProcessing = false;
			currentAbortController = null;
		});
	}

	// Reset cancellation state when modal is hidden
	uploadModal.addEventListener("hidden.bs.modal", () => {
		isProcessing = false;
		currentAbortController = null;
	});

	// Handle cancel button click
	let cancelRequested = false;

	// Helper function to handle cancellation logic
	function handleCancellation(buttonType) {
		if (isProcessing) {
			// Cancel processing
			cancelRequested = true;
			// Abort current upload if controller exists
			if (currentAbortController) {
				currentAbortController.abort();
			}
			// Update UI immediately based on button type
			if (buttonType === "cancel") {
				cancelButton.textContent = "Cancelling...";
				cancelButton.disabled = true;
			} else if (buttonType === "close") {
				closeButton.disabled = true;
				closeButton.style.opacity = "0.5";
			}
			// Update progress message
			const progressMessage = document.getElementById("progressMessage");
			if (progressMessage) {
				progressMessage.textContent = "Cancelling upload...";
			}
			// Force UI reset after a short delay to ensure it happens
			setTimeout(() => {
				if (cancelRequested) {
					resetUIState();
				}
			}, 500);
		}
		// If not processing, let the normal button behavior handle it
	}

	cancelButton.addEventListener("click", () => {
		handleCancellation("cancel");
	});

	// Handle close button (X) click - same logic as cancel button
	closeButton.addEventListener("click", () => {
		handleCancellation("close");
	});

	// Helper function to check for large files
	function checkForLargeFiles(files, cancelButton, submitButton) {
		const progressSection = document.getElementById("checkingProgressSection");
		const LARGE_FILE_THRESHOLD = 512 * 1024 * 1024; // 512MB in bytes
		const largeFiles = files.filter((file) => file.size > LARGE_FILE_THRESHOLD);

		if (largeFiles.length > 0) {
			// Reset UI state
			progressSection.style.display = "none";
			cancelButton.textContent = "Cancel";
			cancelButton.classList.remove("btn-warning");
			submitButton.disabled = false;

			// Create alert message
			const largeFileNames = largeFiles.map((file) => file.name).join(", ");
			const alertMessage = `Large files detected (over 512MB): ${largeFileNames}\n\nPlease:\n1. Skip these large files and upload the remaining files, or\n2. Use the SpectrumX SDK (https://pypi.org/project/spectrumx/) to upload large files and add them to your capture.\n\nLarge files may cause issues with the web interface.`;

			alert(alertMessage);
			return true; // Indicates large files were found
		}
		return false; // No large files found
	}

	// Helper function to check files for duplicates
	async function checkFilesForDuplicates(files, cancelButton, submitButton) {
		// Local progress bar variables
		const progressSection = document.getElementById("checkingProgressSection");
		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");
		const progressMessage = document.getElementById("progressMessage");

		// Show progress section
		progressSection.style.display = "block";
		progressMessage.textContent = "Processing files for upload...";

		// Update UI to show processing state
		cancelButton.textContent = "Cancel Processing";
		submitButton.disabled = true;

		// Initialize variables for file checking
		window.filesToSkip = new Set();
		window.fileCheckResults = new Map();

		const totalFiles = files.length;

		// Get CSRF token
		const getCSRFToken = () => {
			const metaToken = document.querySelector('meta[name="csrf-token"]');
			if (metaToken) return metaToken.getAttribute("content");
			const inputToken = document.querySelector('[name="csrfmiddlewaretoken"]');
			if (inputToken) return inputToken.value;
			const cookies = document.cookie.split(";");
			for (let i = 0; i < cookies.length; i++) {
				const cookie = cookies[i].trim();
				if (cookie.startsWith("csrftoken=")) {
					return cookie.substring("csrftoken=".length);
				}
			}
			return "";
		};

		const csrfToken = getCSRFToken();
		if (!csrfToken) {
			throw new Error("CSRF token not found");
		}

		// Check each file for duplicates with progress
		for (let i = 0; i < files.length; i++) {
			const file = files[i];

			// Update progress
			const progress = Math.round(((i + 1) / totalFiles) * 100);
			progressBar.style.width = `${progress}%`;
			progressText.textContent = `${progress}%`;

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
				const checkFileUrl =
					document.querySelector("[data-check-file-url]")?.dataset
						.checkFileUrl || "/users/check-file-exists/";
				const response = await fetch(checkFileUrl, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"X-CSRFToken": csrfToken,
					},
					body: JSON.stringify(checkData),
				});

				const data = await response.json();

				// Store the result
				const fileKey = `${directory}/${file.name}`;
				window.fileCheckResults.set(fileKey, {
					file: file,
					directory: directory,
					filename: file.name,
					checksum: hashHex,
					data: data.data,
				});

				// Mark for skipping if file exists in tree
				if (data.data && data.data.file_exists_in_tree === true) {
					window.filesToSkip.add(fileKey);
				}
			} catch (error) {
				// Error checking file
				console.error("Error checking file:", error);
			}

			// Check for cancellation after each file check
			if (cancelRequested) {
				break;
			}
		}

		progressSection.style.display = "none";

		// Check if cancellation was requested during file checking
		if (cancelRequested) {
			// Small delay to ensure UI updates are visible
			progressSection.style.display = "none";
			await new Promise((resolve) => setTimeout(resolve, 100));
			// Show alert for duplicate checking cancellation
			alert("Processing cancelled. No files were uploaded.");
			throw new Error("Upload cancelled by user");
		}
	}

	// Helper function to handle skipped files upload
	async function handleSkippedFilesUpload(allRelativePaths, abortController) {
		// Create form data for skipped files case
		const skippedFormData = new FormData();

		// Always add all relative paths for capture creation
		for (const path of allRelativePaths) {
			skippedFormData.append("all_relative_paths", path);
		}

		// Add other form fields
		const captureType = document.getElementById("captureTypeSelect").value;
		skippedFormData.append("capture_type", captureType);

		if (captureType === "drf") {
			const channels = document.getElementById("captureChannelsInput").value;
			skippedFormData.append("channels", channels);
		} else if (captureType === "rh") {
			const scanGroup = document.getElementById("captureScanGroupInput").value;
			skippedFormData.append("scan_group", scanGroup);
		}

		// Don't send chunk information for skipped files
		// This ensures capture creation happens

		const uploadUrl =
			document.querySelector("[data-upload-url]")?.dataset.uploadUrl ||
			"/users/upload-capture/";
		const getCSRFToken = () => {
			const metaToken = document.querySelector('meta[name="csrf-token"]');
			if (metaToken) return metaToken.getAttribute("content");
			const inputToken = document.querySelector('[name="csrfmiddlewaretoken"]');
			if (inputToken) return inputToken.value;
			const cookies = document.cookie.split(";");
			for (let i = 0; i < cookies.length; i++) {
				const cookie = cookies[i].trim();
				if (cookie.startsWith("csrftoken=")) {
					return cookie.substring("csrftoken=".length);
				}
			}
			return "";
		};

		const response = await fetch(uploadUrl, {
			method: "POST",
			headers: {
				"X-CSRFToken": getCSRFToken(),
			},
			body: skippedFormData,
			signal: abortController.signal,
		});

		const result = await response.json();
		return result;
	}

	// Helper function to calculate total chunks
	function calculateTotalChunks(filesToUpload, chunkSizeBytes) {
		let totalChunks = 0;
		let tempChunkSize = 0;
		let tempChunkFiles = 0; // Track number of files in current chunk (mirrors currentChunk.length)

		for (let i = 0; i < filesToUpload.length; i++) {
			const file = filesToUpload[i];

			// Check if this file would exceed the chunk limit (mirrors upload logic exactly)
			if (tempChunkSize + file.size > chunkSizeBytes && tempChunkFiles > 0) {
				// Current chunk would exceed size limit, start new chunk
				totalChunks++;
				tempChunkSize = 0;
				tempChunkFiles = 0;
			}

			// Now add the file to the current chunk
			if (file.size > chunkSizeBytes) {
				// Large file gets its own chunk
				totalChunks++;
				tempChunkSize = 0;
				tempChunkFiles = 0;
			} else {
				// Add to current chunk
				tempChunkSize += file.size;
				tempChunkFiles++;
			}
		}

		// Add final chunk if there are remaining files
		if (tempChunkSize > 0) {
			totalChunks++;
		}

		return totalChunks;
	}

	// Function to upload files in chunks
	async function uploadFilesInChunks(
		filesToUpload,
		relativePathsToUpload,
		allRelativePaths,
		totalFiles,
	) {
		// Get progress elements locally
		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");
		const progressMessage = document.getElementById("progressMessage");
		const progressSection = document.getElementById("checkingProgressSection");

		// Show upload progress if there are files to upload
		if (filesToUpload.length > 0) {
			progressSection.style.display = "block";
			progressMessage.textContent = "Uploading files and creating captures...";
			progressBar.style.width = "0%";
			progressText.textContent = "0%";
		}

		// Create AbortController for upload
		const abortController = new AbortController();
		currentAbortController = abortController;

		// Chunk size for file uploads (50 MB per chunk)
		const CHUNK_SIZE_BYTES = 50 * 1024 * 1024; // 50 MB in bytes

		let allResults = {
			file_upload_status: "success",
			saved_files_count: 0,
			captures: [],
			errors: [],
			message: "",
		};

		// Special case: if all files are skipped, send a single request without chunking
		if (filesToUpload.length === 0) {
			allResults = await handleSkippedFilesUpload(
				allRelativePaths,
				abortController,
			);
		} else {
			// Upload files in chunks based on size (50MB per chunk)
			let currentChunk = [];
			let currentChunkPaths = [];
			let currentChunkSize = 0;
			let chunkNumber = 1;
			let filesProcessed = 0;

			// Calculate total chunks first
			const totalChunks = calculateTotalChunks(filesToUpload, CHUNK_SIZE_BYTES);

			// Now upload files in chunks
			for (let i = 0; i < filesToUpload.length; i++) {
				const file = filesToUpload[i];
				const filePath = relativePathsToUpload[i];

				// Check if this file would exceed the 50MB limit
				if (
					currentChunkSize + file.size > CHUNK_SIZE_BYTES &&
					currentChunk.length > 0
				) {
					// Upload current chunk before adding this file
					await uploadChunk(
						currentChunk,
						currentChunkPaths,
						chunkNumber,
						totalChunks,
						filesProcessed,
						false,
						allResults,
						allRelativePaths,
						totalFiles,
						CHUNK_SIZE_BYTES,
					);
					// Reset for next chunk
					currentChunk = [];
					currentChunkPaths = [];
					currentChunkSize = 0;
					chunkNumber++;
				}

				// Add file to current chunk
				currentChunk.push(file);
				currentChunkPaths.push(filePath);
				currentChunkSize += file.size;
				filesProcessed++;

				// Check if this is the last file
				if (i === filesToUpload.length - 1) {
					// Upload final chunk
					await uploadChunk(
						currentChunk,
						currentChunkPaths,
						chunkNumber,
						totalChunks,
						filesProcessed,
						true,
						allResults,
						allRelativePaths,
						totalFiles,
						CHUNK_SIZE_BYTES,
					);
				}

				// Check if cancel was requested
				if (cancelRequested) {
					break;
				}
			}
		}

		// Check if cancellation was requested during chunk upload
		if (cancelRequested) {
			// Small delay to ensure UI updates are visible
			await new Promise((resolve) => setTimeout(resolve, 100));
			throw new Error("Upload cancelled by user");
		}

		// Check if upload was aborted due to errors
		if (allResults.file_upload_status === "error") {
			// Clear the reference since upload was aborted
			currentAbortController = null;
			// Show error results
			showUploadResults(allResults, allResults.saved_files_count, totalFiles);
			return allResults; // Exit early, don't continue with normal flow
		}

		// Clear the reference since upload completed
		currentAbortController = null;
		return allResults;
	}

	// Helper function to upload a chunk
	async function uploadChunk(
		chunk,
		chunkPaths,
		chunkNum,
		totalChunks,
		filesProcessed,
		isFinalChunk,
		allResults,
		allRelativePaths,
		totalFiles,
		CHUNK_SIZE_BYTES,
	) {
		// Get progress elements locally
		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");
		const progressMessage = document.getElementById("progressMessage");

		// Update progress
		const progress = Math.round((filesProcessed / totalFiles) * 100);
		progressBar.style.width = `${progress}%`;
		progressText.textContent = `${progress}%`;

		if (chunk.length === 1 && chunk[0].size > CHUNK_SIZE_BYTES) {
			// Large file upload
			const file = chunk[0];
			progressMessage.textContent = `Uploading large file: ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB)...`;
		} else {
			// Normal chunk upload
			progressMessage.textContent = `Uploading chunk ${chunkNum}/${totalChunks} (${filesProcessed} files processed)...`;
		}

		// Create form data for this chunk
		const chunkFormData = new FormData();

		// Add files for this chunk
		for (const file of chunk) {
			chunkFormData.append("files", file);
		}

		for (const path of chunkPaths) {
			chunkFormData.append("relative_paths", path);
		}

		// Always add all relative paths for capture creation
		for (const path of allRelativePaths) {
			chunkFormData.append("all_relative_paths", path);
		}

		// Add other form fields
		const captureType = document.getElementById("captureTypeSelect").value;
		chunkFormData.append("capture_type", captureType);

		if (captureType === "drf") {
			const channels = document.getElementById("captureChannelsInput").value;
			chunkFormData.append("channels", channels);
		} else if (captureType === "rh") {
			const scanGroup = document.getElementById("captureScanGroupInput").value;
			chunkFormData.append("scan_group", scanGroup);
		}

		// Add chunk information
		chunkFormData.append("is_chunk", "true");
		chunkFormData.append("chunk_number", chunkNum.toString());
		chunkFormData.append("total_chunks", totalChunks.toString());

		// Check for cancellation before starting this chunk
		if (cancelRequested) {
			throw new Error("Upload cancelled by user");
		}

		// Upload this chunk with timeout (longer timeout for large files)
		const controller = new AbortController();
		currentAbortController = controller;

		const MIN_AVG_UPLOAD_RATE = 100 * 1024; // 100 KB/s minimum upload rate
		const MIN_TIMEOUT_MS = 30000; // Minimum 30 seconds timeout
		const total_chunk_size_bytes = chunk.reduce(
			(total, file) => total + file.size,
			0,
		);
		const calculated_timeout =
			(total_chunk_size_bytes / MIN_AVG_UPLOAD_RATE) * 1000;
		const timeout = Math.max(calculated_timeout, MIN_TIMEOUT_MS); // Use at least 30 seconds

		const timeoutId = setTimeout(() => controller.abort(), timeout);

		let response;
		let chunkResult;

		const getCSRFToken = () => {
			const metaToken = document.querySelector('meta[name="csrf-token"]');
			if (metaToken) return metaToken.getAttribute("content");
			const inputToken = document.querySelector('[name="csrfmiddlewaretoken"]');
			if (inputToken) return inputToken.value;
			const cookies = document.cookie.split(";");
			for (let i = 0; i < cookies.length; i++) {
				const cookie = cookies[i].trim();
				if (cookie.startsWith("csrftoken=")) {
					return cookie.substring("csrftoken=".length);
				}
			}
			return "";
		};

		const uploadUrl =
			document.querySelector("[data-upload-url]")?.dataset.uploadUrl ||
			"/users/upload-capture/";

		try {
			response = await fetch(uploadUrl, {
				method: "POST",
				headers: {
					"X-CSRFToken": getCSRFToken(),
				},
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
			if (error.name === "AbortError") {
				throw new Error("Upload timeout - connection may be lost");
			}
			throw error;
		}

		// Merge results
		if (chunkResult.saved_files_count !== undefined) {
			allResults.saved_files_count += chunkResult.saved_files_count;
		}

		// Collect captures from the final chunk
		if (chunkResult.captures && isFinalChunk) {
			allResults.captures = allResults.captures.concat(chunkResult.captures);
		}

		// Also collect any message from the final chunk
		if (chunkResult.message && isFinalChunk) {
			allResults.message = chunkResult.message;
		}

		if (chunkResult.errors) {
			allResults.errors = allResults.errors.concat(chunkResult.errors);
		}

		// Check if any chunk failed
		if (chunkResult.file_upload_status === "error") {
			allResults.file_upload_status = "error";
			allResults.message = chunkResult.message || "Upload failed";
			const progressMessage = document.getElementById("progressMessage");
			if (progressMessage) {
				progressMessage.textContent =
					"Upload aborted due to errors. Please check the results.";
			}
			throw new Error(`Upload failed: ${chunkResult.message}`);
		}
		if (chunkResult.file_upload_status === "success") {
			// Only update to success if this is the final chunk
			if (isFinalChunk) {
				allResults.file_upload_status = "success";
			}
		}
	}

	const uploadForm = document.getElementById("uploadCaptureForm");
	if (uploadForm) {
		uploadForm.addEventListener("submit", async (e) => {
			e.preventDefault();

			// Set processing state
			isProcessing = true;
			uploadInProgress = true;
			cancelRequested = false; // Reset cancel flag for new upload
			sessionStorage.setItem("uploadInProgress", "true");

			// Check if files are selected
			if (!window.selectedFiles || window.selectedFiles.length === 0) {
				alert("Please select files to upload.");
				return;
			}

			const files = window.selectedFiles;

			// Check for large files before duplicate checking
			if (checkForLargeFiles(files, cancelButton, submitButton)) {
				return;
			}

			// Check files for duplicates
			await checkFilesForDuplicates(files, cancelButton, submitButton);

			// Prepare files for upload (only non-skipped files)
			const filesToUpload = [];
			const relativePathsToUpload = [];
			// Always collect all relative paths for capture creation, even for skipped files
			const allRelativePaths = [];
			let skippedFilesCount = 0;

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

				// Add to all paths for capture creation
				allRelativePaths.push(relativePath);

				// Only add to upload list if not skipped
				if (!window.filesToSkip.has(fileKey)) {
					filesToUpload.push(file);
					relativePathsToUpload.push(relativePath);
				} else {
					skippedFilesCount++;
				}
			}

			// Upload files in chunks
			try {
				const uploadResults = await uploadFilesInChunks(
					filesToUpload,
					relativePathsToUpload,
					allRelativePaths,
					filesToUpload.length,
				);

				// Clear the reference since upload completed
				currentAbortController = null;

				// Show results
				showUploadResults(
					uploadResults,
					uploadResults.saved_files_count,
					files.length,
					skippedFilesCount,
				);

				// Don't auto-reload for successful uploads - let user close modal first
			} catch (error) {
				if (cancelRequested) {
					// Check if this was cancelled during duplicate checking (no files uploaded yet)
					if (!uploadInProgress) {
						// Already showed alert in checkFilesForDuplicates function
						// No need to reload since no files were uploaded
					} else {
						alert(
							"Upload cancelled. Any files uploaded before cancellation have been saved.",
						);
						// Reload page after cancellation
						setTimeout(() => {
							window.location.reload();
						}, 1000);
					}
				} else if (error.name === "AbortError") {
					alert(
						"Upload was interrupted. Any files uploaded before the interruption have been saved.",
					);
					// Reload page after interruption
					setTimeout(() => {
						window.location.reload();
					}, 1000);
				} else if (
					error.name === "TypeError" &&
					error.message.includes("fetch")
				) {
					// Don't show alert for network errors after page refresh
					if (uploadInProgress || sessionStorage.getItem("uploadInProgress")) {
						// Suppressing network error alert during active upload
					} else {
						alert(
							"Network error during upload. Please check your connection and try again.",
						);
					}
				} else {
					alert(`Upload failed: ${error.message}`);
					// Reload page after other errors
					setTimeout(() => {
						window.location.reload();
					}, 1000);
				}
			} finally {
				// Clean up UI state - ensure this always runs
				resetUIState();
			}
		});
	}

	// Function to reset UI state
	function resetUIState() {
		// Reset submit button
		if (submitButton) {
			submitButton.disabled = false;
		}

		// Hide progress section
		const progressSection = document.getElementById("checkingProgressSection");
		if (progressSection) {
			progressSection.style.display = "none";
		}

		// Reset cancel button
		if (cancelButton) {
			cancelButton.textContent = "Cancel";
			cancelButton.classList.remove("btn-warning");
			cancelButton.disabled = false;
		}

		// Reset close button
		if (closeButton) {
			closeButton.disabled = false;
			closeButton.style.opacity = "1";
		}

		// Reset progress elements
		const progressBar = document.getElementById("checkingProgressBar");
		const progressText = document.getElementById("checkingProgressText");
		const progressMessage = document.getElementById("progressMessage");

		if (progressBar) progressBar.style.width = "0%";
		if (progressText) progressText.textContent = "0%";
		if (progressMessage) progressMessage.textContent = "";

		// Reset state flags
		isProcessing = false;
		uploadInProgress = false;
		cancelRequested = false;

		// Clear session storage
		sessionStorage.removeItem("uploadInProgress");

		// Clear abort controller
		currentAbortController = null;
	}

	// Function to show upload results
	function showUploadResults(
		result,
		uploadedCount,
		totalCount,
		skippedCount = 0,
	) {
		// Check if page was refreshed during upload
		if (!uploadInProgress && result.file_upload_status === "error") {
			resetUIState(); // Ensure UI is reset even if modal is not shown
			return;
		}

		const modalBody = document.getElementById("uploadResultModalBody");
		const resultModalEl = document.getElementById("uploadResultModal");
		const modal = new bootstrap.Modal(resultModalEl);

		// Close the upload modal before showing result modal
		const uploadModal = bootstrap.Modal.getInstance(
			document.getElementById("uploadCaptureModal"),
		);
		if (uploadModal) {
			uploadModal.hide();
		}

		let msg = "";

		if (result.file_upload_status === "success") {
			// Use frontend accumulated count for accuracy, but include backend message for additional info
			if (uploadedCount === 0 && totalCount > 0) {
				// All files were skipped
				msg = `<b>Upload complete!</b><br />All ${totalCount} files already existed on the server.`;
			} else if (skippedCount > 0) {
				// Some files were uploaded, some were skipped
				msg = `<b>Upload complete!</b><br />Files uploaded: <strong>${uploadedCount}</strong> / ${totalCount}`;
				msg += `<br />Files already exist: <strong>${skippedCount}</strong>`;
			} else {
				// All files were uploaded (no skipped files)
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
			// Upload failed - show error message and prompt to remove error files
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
		modal.show();

		// Add event listener to reload page when result modal is closed (only for successful uploads)
		if (result.file_upload_status === "success") {
			resultModalEl.addEventListener(
				"hidden.bs.modal",
				() => {
					window.location.reload();
				},
				{ once: true },
			); // Only trigger once per modal instance
		}
	}
});

// Capture Type Selection JavaScript
document.addEventListener("DOMContentLoaded", () => {
	const captureTypeSelect = document.getElementById("captureTypeSelect");
	const channelInputGroup = document.getElementById("channelInputGroup");
	const scanGroupInputGroup = document.getElementById("scanGroupInputGroup");
	const captureChannelsInput = document.getElementById("captureChannelsInput");
	const captureScanGroupInput = document.getElementById(
		"captureScanGroupInput",
	);

	if (captureTypeSelect) {
		captureTypeSelect.addEventListener("change", function () {
			const selectedType = this.value;

			// Hide both input groups initially
			if (channelInputGroup)
				channelInputGroup.classList.add("hidden-input-group");
			if (scanGroupInputGroup)
				scanGroupInputGroup.classList.add("hidden-input-group");

			// Clear required attributes
			if (captureChannelsInput)
				captureChannelsInput.removeAttribute("required");
			if (captureScanGroupInput)
				captureScanGroupInput.removeAttribute("required");

			// Show appropriate input group based on selection
			if (selectedType === "drf") {
				if (channelInputGroup)
					channelInputGroup.classList.remove("hidden-input-group");
				if (captureChannelsInput)
					captureChannelsInput.setAttribute("required", "required");
			} else if (selectedType === "rh") {
				if (scanGroupInputGroup)
					scanGroupInputGroup.classList.remove("hidden-input-group");
				// scan_group is optional for RadioHound captures
			}
		});
	}

	// Reset form when modal is hidden
	const uploadModal = document.getElementById("uploadCaptureModal");
	if (uploadModal) {
		uploadModal.addEventListener("hidden.bs.modal", () => {
			// Reset the form
			const form = document.getElementById("uploadCaptureForm");
			if (form) {
				form.reset();
			}

			// Hide input groups
			if (channelInputGroup)
				channelInputGroup.classList.add("hidden-input-group");
			if (scanGroupInputGroup)
				scanGroupInputGroup.classList.add("hidden-input-group");

			// Clear required attributes
			if (captureChannelsInput)
				captureChannelsInput.removeAttribute("required");
			if (captureScanGroupInput)
				captureScanGroupInput.removeAttribute("required");

			// Clear file check status
			const checkStatusDiv = document.getElementById("fileCheckStatus");
			if (checkStatusDiv) {
				checkStatusDiv.style.display = "none";
			}

			// Clear status alerts and file details button
			const uploadModalBody = document.querySelector(
				"#uploadCaptureModal .modal-body",
			);
			if (uploadModalBody) {
				const existingAlerts = uploadModalBody.querySelectorAll(
					".alert.alert-warning, .alert.alert-success",
				);
				for (const alert of existingAlerts) {
					if (
						alert.textContent.includes("will be skipped") ||
						alert.textContent.includes("will be uploaded")
					) {
						alert.remove();
					}
				}

				// Remove file details button
				const detailsLink = uploadModalBody.querySelector(
					"#viewFileDetailsLink",
				);
				if (detailsLink) {
					detailsLink.parentNode.remove();
				}
			}

			// Clear global variables
			if (window.filesToSkip) window.filesToSkip.clear();
			if (window.fileCheckResults) window.fileCheckResults.clear();
		});
	}
});

// BLAKE3 hash calculation for file deduplication
// Global variable to track files that should be skipped
window.filesToSkip = new Set();
window.fileCheckResults = new Map(); // Store detailed results for each file

document.addEventListener("DOMContentLoaded", () => {
	const modal = document.getElementById("uploadCaptureModal");
	if (!modal) {
		console.warn("uploadCaptureModal not found");
		return;
	}

	modal.addEventListener("shown.bs.modal", () => {
		const fileInput = document.getElementById("captureFileInput");
		if (!fileInput) {
			console.warn("captureFileInput not found");
			return;
		}

		// Remove any previous handler to avoid duplicates
		fileInput.removeEventListener("change", window._blake3CaptureHandler);

		// Simple file handler that just stores the selected files
		window._blake3CaptureHandler = async (event) => {
			const files = event.target.files;
			if (!files || files.length === 0) {
				return;
			}

			// Store the selected files for later processing
			window.selectedFiles = Array.from(files);
		};

		fileInput.addEventListener("change", window._blake3CaptureHandler);
	});
});
