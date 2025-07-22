document.addEventListener("DOMContentLoaded", () => {
	// Initialize Bootstrap modal
	const uploadModal = document.getElementById("uploadModal");
	const uploadButton = document.getElementById("uploadButton");
	const modal = new bootstrap.Modal(uploadModal);

	// Show modal when upload button is clicked
	uploadButton.addEventListener("click", () => {
		modal.show();
	});

	const uploadForm = document.getElementById("uploadForm");
	const regularDropZone = document.getElementById("regularDropZone");
	const captureDropZone = document.getElementById("dropZone");
	const regularFileInput = document.getElementById("regularFileInput");
	const directoryInput = document.getElementById("directoryInput");
	const fileList = document.getElementById("fileList");
	const regularUploadRadio = document.getElementById("regularUpload");
	const captureUploadRadio = document.getElementById("captureUpload");
	const captureOptions = document.getElementById("captureOptions");
	const regularOptions = document.getElementById("regularOptions");
	const totalSizeDiv = document.querySelector(".total-size");

	// Show/hide appropriate options based on upload type
	regularUploadRadio.addEventListener("change", () => {
		captureOptions.style.display = "none";
		regularOptions.style.display = "block";
	});

	captureUploadRadio.addEventListener("change", () => {
		captureOptions.style.display = "block";
		regularOptions.style.display = "none";
	});

	// Prevent default drag behaviors
	for (const eventName of ["dragenter", "dragover", "dragleave", "drop"]) {
		regularDropZone.addEventListener(eventName, preventDefaults, false);
		captureDropZone.addEventListener(eventName, preventDefaults, false);
		document.body.addEventListener(eventName, preventDefaults, false);
	}

	// Highlight drop zone when item is dragged over it
	for (const eventName of ["dragenter", "dragover"]) {
		regularDropZone.addEventListener(eventName, highlight, false);
		captureDropZone.addEventListener(eventName, highlight, false);
	}

	for (const eventName of ["dragleave", "drop"]) {
		regularDropZone.addEventListener(eventName, unhighlight, false);
		captureDropZone.addEventListener(eventName, unhighlight, false);
	}

	function preventDefaults(e) {
		e.preventDefault();
		e.stopPropagation();
	}

	function highlight(e) {
		this.classList.add("highlight");
	}

	function unhighlight(e) {
		this.classList.remove("highlight");
	}

	// Handle regular file selection
	regularDropZone.addEventListener("click", () => regularFileInput.click());
	regularFileInput.addEventListener("change", handleRegularFileSelect);

	// Handle directory selection
	captureDropZone.addEventListener("click", () => directoryInput.click());
	directoryInput.addEventListener("change", handleDirectorySelect);

	// Handle drops
	regularDropZone.addEventListener("drop", handleRegularDrop);
	captureDropZone.addEventListener("drop", handleCaptureDrop);

	async function processEntry(entry, basePath = "") {
		const files = [];
		console.log("DEBUG - Entry details:", {
			name: entry.name,
			basePath: basePath,
			fullPath: entry.fullPath,
			isFile: entry.isFile,
			isDirectory: entry.isDirectory,
		});

		if (entry.isFile) {
			const file = await new Promise((resolve) => entry.file(resolve));

			// For RadioHound files, preserve the original directory structure
			if (file.name.endsWith(".rh.json")) {
				// Extract the directory path from the full path
				const dirPath = entry.fullPath
					? entry.fullPath.split("/").slice(1, -1).join("/")
					: "";

				file.originalDirectory = dirPath;
				file.relativePath = dirPath ? `${dirPath}/${file.name}` : file.name;

				console.log("DEBUG - RadioHound file processing:", {
					dirPath: dirPath,
					originalDirectory: file.originalDirectory,
					relativePath: file.relativePath,
					fullPath: entry.fullPath,
				});
			} else if (
				file.name.includes("drf_") ||
				file.name.startsWith("rf@") ||
				basePath.includes("cap-")
			) {
				// For Digital RF files, preserve the original directory structure
				const dirPath =
					basePath.split("/")[0] || entry.fullPath?.split("/")[1] || "";
				file.originalDirectory = basePath;
				file.relativePath = `${dirPath}/${file.name}`;

				console.log("DEBUG - Digital RF file processing:", {
					dirPath: dirPath,
					originalDirectory: file.originalDirectory,
					relativePath: file.relativePath,
					fullPath: entry.fullPath,
					basePath: basePath,
				});
			} else {
				// For other files, preserve the complete directory structure
				const dirPath = entry.fullPath
					? entry.fullPath.split("/").slice(1, -1).join("/")
					: basePath;
				file.originalDirectory = dirPath;
				file.relativePath = dirPath ? `${dirPath}/${file.name}` : file.name;
			}

			console.log("DEBUG - File after processing:", {
				originalDirectory: file.originalDirectory,
				relativePath: file.relativePath,
			});
			files.push(file);
		} else if (entry.isDirectory) {
			const reader = entry.createReader();
			const entries = await new Promise((resolve) =>
				reader.readEntries(resolve),
			);
			// Update the base path to include this directory
			const newBasePath = basePath ? `${basePath}/${entry.name}` : entry.name;

			for (const childEntry of entries) {
				const childFiles = await processEntry(childEntry, newBasePath);
				files.push(...childFiles);
			}
		}
		return files;
	}

	async function handleRegularDrop(e) {
		const dt = e.dataTransfer;
		let files = [];

		if (dt.items) {
			const items = Array.from(dt.items);
			const entries = items
				.filter((item) => item.webkitGetAsEntry || item.getAsEntry)
				.map((item) => item.webkitGetAsEntry() || item.getAsEntry());

			for (const entry of entries) {
				if (entry) {
					const entryFiles = await processEntry(entry);
					files.push(...entryFiles);
				}
			}
		} else {
			files = Array.from(dt.files);
		}

		handleFiles(files, false);
	}

	async function handleCaptureDrop(e) {
		e.preventDefault();
		const dt = e.dataTransfer;
		const files = [];
		console.log("Handling capture drop");

		if (dt.items) {
			const items = Array.from(dt.items);
			const entries = items
				.filter((item) => item.webkitGetAsEntry || item.getAsEntry)
				.map((item) => item.webkitGetAsEntry() || item.getAsEntry());

			// Process all entries
			for (const entry of entries) {
				if (entry) {
					console.log("Processing entry:", entry.name);
					const entryFiles = await processEntry(entry, entry.name);
					files.push(...entryFiles);
				}
			}
		} else {
			console.log("No items in drop data transfer");
		}

		if (files.length === 0) {
			showError("Please drop a directory containing capture files");
			return;
		}

		// For RadioHound captures, preserve the original directory name
		const rhFiles = files.filter((f) => f.name.endsWith(".rh.json"));
		const drfFiles = files.filter(
			(f) =>
				f.name.includes("drf_") ||
				f.name.startsWith("rf@") ||
				f.webkitRelativePath?.includes("cap-"),
		);

		if (rhFiles.length > 0) {
			const originalDir = rhFiles[0].originalDirectory;
			if (originalDir) {
				// Update all file paths to use the original directory
				for (const file of files) {
					file.relativePath = file.relativePath.replace(/^[^/]+/, originalDir);
				}
			}
		} else if (drfFiles.length > 0) {
			// For Digital RF, use the original directory name just like RadioHound
			const originalDir = drfFiles[0].webkitRelativePath?.split("/")[0] || "";
			if (originalDir) {
				for (const file of files) {
					file.relativePath = file.relativePath.replace(/^[^/]+/, originalDir);
				}
			}
		}

		handleFiles(files, true);
	}

	function handleRegularFileSelect(e) {
		const files = Array.from(e.target.files);
		handleFiles(files, false);
	}

	function handleDirectorySelect(e) {
		const files = Array.from(e.target.files);
		console.log(
			"Directory selected, files:",
			files.map((f) => f.name),
		);
		if (files.length === 0) {
			showError("Please select a directory containing .rh.json files");
			return;
		}
		handleFiles(files, true);
	}

	function updateTotalSize() {
		const files = Array.from(
			regularUploadRadio.checked
				? regularFileInput.files
				: directoryInput.files,
		);
		const totalSize = files.reduce((sum, file) => sum + file.size, 0);
		totalSizeDiv.textContent = `Total size: ${formatBytes(totalSize)}`;
	}

	function formatBytes(bytes) {
		if (bytes === 0) return "0 Bytes";
		const k = 1024;
		const sizes = ["Bytes", "KB", "MB", "GB"];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
	}

	function truncateFileName(name, maxLength) {
		if (name.length <= maxLength) return name;
		const ext = name.split(".").pop();
		const nameWithoutExt = name.slice(0, -(ext.length + 1));
		const truncated = `${nameWithoutExt.slice(0, maxLength - ext.length - 4)}...`;
		return `${truncated}.${ext}`;
	}

	function showError(message) {
		const errorDiv = document.createElement("div");
		errorDiv.className = "alert alert-danger";
		errorDiv.innerHTML = message;
		fileList.insertBefore(errorDiv, fileList.firstChild);
	}

	function handleFormSubmission(form) {
		form.addEventListener("submit", async (e) => {
			e.preventDefault();

			const submitButton = form.querySelector(".upload-submit");
			if (submitButton) {
				submitButton.disabled = true;
				submitButton.textContent = "Uploading...";
			}

			try {
				const formData = new FormData(form);
				const fileInput = form.querySelector('input[type="file"]');
				const captureType = form.querySelector('[name="capture_type"]')?.value;

				// Clear any existing files from formData
				formData.delete("files[]");
				formData.delete("files");

				const files = Array.from(fileInput.files);
				const rhFiles = files.filter((f) => f.name.endsWith(".rh.json"));
				const drfFiles = files.filter(
					(f) =>
						f.name.includes("drf_") ||
						f.name.startsWith("rf@") ||
						f.webkitRelativePath?.includes("cap-"),
				);

				// Get the original directory name
				let directory = "";
				if (rhFiles.length > 0) {
					directory =
						rhFiles[0].webkitRelativePath?.split("/")[0] ||
						"radiohound-update-v0";
				} else if (drfFiles.length > 0) {
					directory = drfFiles[0].webkitRelativePath?.split("/")[0] || "";
				}

				// Add each file to formData with its complete path
				for (const file of files) {
					const relativePath = file.webkitRelativePath || file.name;
					formData.append("files[]", file, relativePath);
				}

				// Set the directory to the original directory name
				if (directory) {
					formData.set("directory", directory);
				}

				const response = await fetch(form.action, {
					method: "POST",
					body: formData,
				});

				if (!response.ok) {
					throw new Error(`HTTP error! status: ${response.status}`);
				}

				// Close modal and reload page on success
				const modal = bootstrap.Modal.getInstance(form.closest(".modal"));
				if (modal) {
					modal.hide();
				}
				window.location.reload();
			} catch (error) {
				console.error("Upload error:", error);
				showError("Failed to upload files. Please try again.");

				if (submitButton) {
					submitButton.disabled = false;
					submitButton.textContent = "Upload";
				}
			}
		});
	}

	function createFileList(files) {
		const dt = new DataTransfer();
		for (const file of files) {
			dt.items.add(file);
		}
		return dt.files;
	}

	function handleFiles(files, isCapture) {
		const fileList = document.getElementById("fileList");
		fileList.innerHTML = "";

		// Group files by directory
		const directories = new Map();
		for (const file of files) {
			let dirPath;

			if (file.name.endsWith(".rh.json")) {
				// For RadioHound files, use radiohound-update-v0
				dirPath = "radiohound-update-v0";
			} else if (
				isCapture &&
				(file.name.includes("drf_") ||
					file.name.startsWith("rf@") ||
					file.webkitRelativePath?.includes("cap-"))
			) {
				// For Digital RF captures, use the parent directory name
				dirPath =
					file.webkitRelativePath?.split("/")[0] ||
					file.originalDirectory?.split("/")[0] ||
					file.relativePath?.split("/")[0] ||
					"Root";
			} else {
				// For regular files
				dirPath =
					file.originalDirectory ||
					(file.webkitRelativePath
						? file.webkitRelativePath.split("/")[0]
						: "Root");
			}

			if (!directories.has(dirPath)) {
				directories.set(dirPath, {
					name: dirPath,
					files: [],
					fileCount: 0,
					totalSize: 0,
				});
			}
			const dirInfo = directories.get(dirPath);
			dirInfo.files.push(file);
			dirInfo.fileCount++;
			dirInfo.totalSize += file.size;
		}

		// Create a container for all directories
		const directoriesContainer = document.createElement("div");
		directoriesContainer.className = "directories-container";

		// Display directory information
		for (const [dirPath, dirInfo] of directories) {
			const dirDiv = document.createElement("div");
			dirDiv.className = "directory-info p-3 border rounded mb-3";

			// Create the header with folder icon and directory info
			const headerDiv = document.createElement("div");
			headerDiv.className = "d-flex align-items-center justify-content-between";
			headerDiv.innerHTML = `
                <div class="d-flex align-items-center">
                    <i class="bi bi-folder-fill me-2" style="color: #00857c;"></i>
                    <div>
                        <div class="fw-bold">${dirInfo.name}</div>
                        <div class="text-muted small">
                            ${dirInfo.fileCount} file${dirInfo.fileCount !== 1 ? "s" : ""} •
                            ${formatBytes(dirInfo.totalSize)}
                        </div>
                    </div>
                </div>
                <button class="btn btn-sm btn-outline-secondary toggle-files" type="button">
                    <i class="bi bi-chevron-down"></i>
                </button>
            `;

			// Create collapsible files list
			const filesListDiv = document.createElement("div");
			filesListDiv.className = "files-list mt-2 ps-4 border-start ms-3 d-none";
			for (const file of dirInfo.files) {
				const fileDiv = document.createElement("div");
				fileDiv.className = "file-item py-1";
				fileDiv.innerHTML = `
                    <div class="d-flex align-items-center">
                        <i class="bi bi-file-earmark me-2 text-secondary"></i>
                        <div class="text-truncate">${file.name}</div>
                        <div class="text-muted small ms-2">${formatBytes(file.size)}</div>
                    </div>
                `;
				filesListDiv.appendChild(fileDiv);
			}

			// Add click handler for toggle button
			headerDiv
				.querySelector(".toggle-files")
				.addEventListener("click", (e) => {
					const icon = headerDiv.querySelector(
						".bi-chevron-down, .bi-chevron-up",
					);
					filesListDiv.classList.toggle("d-none");
					icon.classList.toggle("bi-chevron-down");
					icon.classList.toggle("bi-chevron-up");
				});

			dirDiv.appendChild(headerDiv);
			dirDiv.appendChild(filesListDiv);
			directoriesContainer.appendChild(dirDiv);
		}

		fileList.appendChild(directoriesContainer);

		// Add some basic styles
		const style = document.createElement("style");
		style.textContent = `
            .directory-info {
                background: #fff;
                transition: all 0.2s ease;
                border-color: #e5e5e5 !important;
            }
            .directory-info:hover {
                background: #f8f9fa;
                border-color: #00857c !important;
            }
            .files-list {
                font-size: 0.9em;
                border-color: #e5e5e5 !important;
            }
            .file-item {
                color: #666;
            }
            .toggle-files {
                padding: 0.25rem 0.5rem;
                border-color: #e5e5e5;
                color: #666;
            }
            .toggle-files:hover {
                border-color: #00857c;
                color: #00857c;
            }
            .toggle-files i {
                transition: transform 0.2s ease;
            }
            .toggle-files .bi-chevron-up {
                transform: rotate(180deg);
            }
            .file-item i {
                color: #666;
            }
            .file-item:hover i {
                color: #00857c;
            }
        `;
		document.head.appendChild(style);

		// Store files in the appropriate input
		if (isCapture) {
			directoryInput.files = createFileList(files);
			showCaptureFields();
		} else {
			regularFileInput.files = createFileList(files);
			hideCaptureFields();
		}

		// Update total size
		const totalSize = Array.from(files).reduce(
			(sum, file) => sum + file.size,
			0,
		);
		totalSizeDiv.textContent = `Total size: ${formatBytes(totalSize)}`;
	}

	function showCaptureFields() {
		captureOptions.style.display = "block";
		regularOptions.style.display = "none";
	}

	function hideCaptureFields() {
		captureOptions.style.display = "none";
		regularOptions.style.display = "block";
	}

	// Add name attribute to file inputs
	directoryInput.setAttribute("name", "files[]");
	regularFileInput.setAttribute("name", "files[]");

	// Handle form submission for both regular and capture uploads
	handleFormSubmission(uploadForm);
});
