/**
 * Files page: sessionStorage flash + capture upload modal (Blake3 + chunked modal).
 * Replaces the DOMContentLoaded block from deprecated/files-upload.js.
 */
document.addEventListener("DOMContentLoaded", () => {
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
		} catch (_) {}
		sessionStorage.removeItem(key);
	}

	if (window.Blake3FileHandler) {
		new window.Blake3FileHandler();
	}
	if (window.FilesUploadModal) {
		new window.FilesUploadModal();
	}
});

if (typeof module !== "undefined" && module.exports) {
	module.exports = {};
}
