/**
 * Global drag/drop and DataTransfer directory traversal for capture uploads.
 * Migrated from deprecated/file-manager.js.
 */
class FileDropManager {
	/** @param {{ handleFileSelection: (files: File[]) => void }} host */
	constructor(host) {
		this.host = host;
	}

	addGlobalDropGuards() {
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

		window.selectedFiles = files;

		const uploadModalEl = document.getElementById("uploadCaptureModal");
		if (!uploadModalEl) {
			console.error("Upload modal element not found");
			return;
		}

		const uploadModal = new bootstrap.Modal(uploadModalEl);
		uploadModal.show();

		setTimeout(() => {
			this.handleGlobalFilesInModal(files);
		}, 200);
	}

	handleGlobalFilesInModal(files) {
		const fileInput = document.getElementById("captureFileInput");
		if (fileInput) {
			const dataTransfer = new DataTransfer();
			for (const file of files) {
				dataTransfer.items.add(file);
			}
			fileInput.files = dataTransfer.files;
		}

		this.host.handleFileSelection(files);

		const selectedFilesSection = document.getElementById("selectedFiles");
		if (selectedFilesSection) {
			selectedFilesSection.classList.add("has-files");
		}

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
		const first = itemsOrFiles[0];
		if (first && typeof first.getAsFile === "function") {
			return Array.from(itemsOrFiles)
				.map((item) => item.getAsFile())
				.filter((f) => !!f);
		}
		return Array.from(itemsOrFiles);
	}

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
}

if (typeof window !== "undefined") {
	window.FileDropManager = FileDropManager;
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { FileDropManager };
}
