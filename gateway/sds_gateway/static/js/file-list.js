/**
 * Capture list page entrypoint.
 * Controllers: captures/FileListPageController.js, captures/FileListCapturesTableManager.js.
 * Full legacy copy: static/js/deprecated/file-list.js
 */
window.initializeFrequencySlider = () => {
	if (window.fileListController) {
		window.fileListController.initializeFrequencyFromURL();
	}
};

document.addEventListener("DOMContentLoaded", () => {
	try {
		window.fileListController = new FileListPageController();
	} catch (error) {
		console.error("Error initializing file list controller:", error);
	}
});

if (typeof module !== "undefined" && module.exports) {
	const { FileListPageController } = require("./captures/FileListPageController.js");
	const {
		FileListCapturesTableManager,
	} = require("./captures/FileListCapturesTableManager.js");
	module.exports = { FileListController: FileListPageController, FileListCapturesTableManager };
}
