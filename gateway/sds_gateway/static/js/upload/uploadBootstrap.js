/**
 * Initializes upload UI based on DOM (capture modal, files browser, plain file form).
 */
function initUploadPage() {
	const hasFilesBrowser = Boolean(document.querySelector(".files-container"));

	if (document.getElementById("uploadCaptureModal")) {
		const ctrl = new CaptureUploadController({});
		ctrl.init();
		window.captureUploadController = ctrl;
	}

	if (document.getElementById("captureTypeSelect")) {
		window.captureTypeSelectorInstance = new CaptureTypeSelector();
	}

	if (hasFilesBrowser) {
		new FilesBrowserManager();
	}

	if (hasFilesBrowser && document.getElementById("uploadFileForm")) {
		window.fileUploadHandlerInstance = new FileUploadHandler();
		window.fileUploadHandler = window.fileUploadHandlerInstance;
	}
}

if (typeof window !== "undefined") {
	const isNodeTestEnv =
		typeof process !== "undefined" &&
		process.env &&
		process.env.NODE_ENV === "test";
	if (!isNodeTestEnv) {
		document.addEventListener("DOMContentLoaded", initUploadPage);
	}
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { initUploadPage };
}
