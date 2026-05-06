/**
 * Upload capture modal: submit, cancel/abort, progress, beforeunload guards.
 * Placeholder: migrate from file_list_upload_capture_modal.js in a later step.
 */
class UploadCaptureModalController {
	constructor() {}

	init() {}

	/**
	 * @param {File[]} files
	 * @param {HTMLElement} cancelButton
	 * @param {HTMLElement} submitButton
	 * @returns {boolean} true if large files blocked flow
	 */
	checkForLargeFiles(files, cancelButton, submitButton) {
		void files;
		void cancelButton;
		void submitButton;
		return false;
	}

	resetUIState() {}

	/**
	 * @param {string} buttonType
	 */
	handleCancellation(buttonType) {
		void buttonType;
	}
}

if (typeof window !== "undefined") {
	window.UploadCaptureModalController = UploadCaptureModalController;
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { UploadCaptureModalController };
}
