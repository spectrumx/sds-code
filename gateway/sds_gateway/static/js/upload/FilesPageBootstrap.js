/**
 * Files page: wires CaptureTypeSelector, FilesPageInitializer, FileUploadHandler on DOM ready.
 * Replaces the DOMContentLoaded block from deprecated/files-ui.js (duplicated classes removed).
 */
document.addEventListener("DOMContentLoaded", () => {
	if (!window.BrowserSupport?.checkRequiredFeatures?.()) {
		window.NotificationUtils?.showError(
			"Your browser doesn't support required features. Please use a modern browser.",
			"browser-compatibility",
		);
		return;
	}

	if (!window.BrowserSupport?.checkBootstrapSupport?.()) {
		console.warn(
			"Bootstrap not detected. Some UI features may not work properly.",
		);
	}

	try {
		const needsCaptureSelector =
			document.getElementById("captureTypeSelect") ||
			document.getElementById("uploadCaptureModal");
		const needsPageInitializer =
			document.querySelector(".modal[data-item-uuid]") ||
			document.getElementById("capture-modal");
		const needsFileUploadHandler =
			document.getElementById("uploadFileModal") ||
			document.getElementById("uploadFileForm");

		let captureSelector = null;
		if (needsCaptureSelector && window.CaptureTypeSelector) {
			captureSelector = new window.CaptureTypeSelector();
		}

		let filesPageInitializer = null;
		if (needsPageInitializer && window.FilesPageInitializer) {
			filesPageInitializer = new window.FilesPageInitializer();
			window.filesPageInitializer = filesPageInitializer;
		}

		let fileUploadHandler = null;
		if (needsFileUploadHandler && window.FileUploadHandler) {
			fileUploadHandler = new window.FileUploadHandler();
			window.fileUploadHandler = fileUploadHandler;
		}

		window.filesUICleanup = () => {
			if (captureSelector && typeof captureSelector.cleanup === "function") {
				captureSelector.cleanup();
			}
			if (
				filesPageInitializer &&
				typeof filesPageInitializer.cleanup === "function"
			) {
				filesPageInitializer.cleanup();
			}
			if (
				fileUploadHandler &&
				typeof fileUploadHandler.cleanup === "function"
			) {
				fileUploadHandler.cleanup();
			}
		};
	} catch (error) {
		window.NotificationUtils?.showError(
			"Failed to initialize Files UI components",
			"initialization",
			error,
		);
	}
});

if (typeof module !== "undefined" && module.exports) {
	module.exports = {};
}
