/**
 * Single-file upload modal (files page, not capture batch).
 */
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
			const csrfToken = window.APIClient.getCSRFToken();
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
if (typeof window !== "undefined") {
	window.FileUploadHandler = FileUploadHandler;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { FileUploadHandler };
}
