/**
 * Common Error Handler for Visualizations
 * Provides shared error handling functionality for visualizations
 */

/**
 * Extract the last line from a traceback string
 */
export function extractErrorDetail(traceback) {
	if (!traceback) return "Check your capture data for issues.";

	const tracebackLines = traceback.split("\n").filter((line) => line.trim());
	return tracebackLines.length > 0
		? tracebackLines[tracebackLines.length - 1].trim()
		: "Check your capture data for issues.";
}

/**
 * Generate user-friendly error message based on error type
 * @returns {Object} Object with `message` (user-friendly message) and `errorDetail` (last error detail line, if any)
 */
export function generateErrorMessage(errorInfo, hasSourceDataError) {
	const message = hasSourceDataError
		? "An error occurred while processing; it may be due to an issue with the capture data."
		: "A server error occurred during processing. Please try again.";

	let errorDetail = null;
	if (hasSourceDataError && errorInfo.traceback) {
		errorDetail = extractErrorDetail(errorInfo.traceback);
	}

	return { message, errorDetail };
}

/**
 * Handle error display setup for a visualization
 * @param {Object} config - Configuration object
 * @param {HTMLElement} config.messageElement - Element to display the error message
 * @param {HTMLElement} config.errorDetailElement - Element to display the error detail line (optional)
 * @param {string} config.message - Error message to display
 * @param {string} config.errorDetail - Last error detail line to display (optional)
 */
export function setupErrorDisplay({
	messageElement,
	errorDetailElement,
	message,
	errorDetail,
}) {
	// Update the error message
	if (messageElement) {
		messageElement.textContent = message;
		if (messageElement.classList) {
			messageElement.classList.add("error-message-text");
		}
	}

	// Update the error detail line if provided
	if (errorDetailElement) {
		if (errorDetail) {
			errorDetailElement.textContent = errorDetail;
			errorDetailElement.classList.remove("d-none");
		} else {
			errorDetailElement.textContent = "";
			errorDetailElement.classList.add("d-none");
		}
	}
}
