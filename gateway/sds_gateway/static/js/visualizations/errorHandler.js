/**
 * Common Error Handler for Visualizations
 * Provides shared error handling functionality for waterfall and spectrogram visualizations
 */

/**
 * Extract the last line from a traceback string
 */
export function extractLastTracebackLine(traceback) {
	if (!traceback) return "Check your capture data for issues.";

	const tracebackLines = traceback.split("\n").filter((line) => line.trim());
	return tracebackLines.length > 0
		? tracebackLines[tracebackLines.length - 1].trim()
		: "Check your capture data for issues.";
}

/**
 * Generate user-friendly error message based on error type
 */
export function generateErrorMessage(errorInfo, hasSourceDataError) {
	if (hasSourceDataError) {
		const traceback = errorInfo.traceback || "";
		const lastLine = extractLastTracebackLine(traceback);
		return `There may be an issue with your capture data.\n\n${lastLine}`;
	}
	return "A server error occurred during processing. Please try again.";
}

/**
 * Format error details text for display
 */
export function formatErrorDetails(errorInfo) {
	let detailsText = "";
	if (errorInfo.error_type) {
		detailsText += `Error Type: ${errorInfo.error_type}\n\n`;
	}
	if (errorInfo.traceback) {
		detailsText += `Traceback:\n${errorInfo.traceback}`;
	} else if (errorInfo.message) {
		detailsText += `Error Message: ${errorInfo.message}`;
	} else {
		detailsText += JSON.stringify(errorInfo, null, 2);
	}
	return detailsText;
}

/**
 * Setup error details toggle button and content
 */
export function setupErrorDetailsToggle(toggleButton, detailsContent) {
	// Remove existing event listeners by cloning the button
	const newToggleButton = toggleButton.cloneNode(true);
	toggleButton.parentNode.replaceChild(newToggleButton, toggleButton);

	// Add toggle functionality
	newToggleButton.addEventListener("click", () => {
		const isVisible = detailsContent.classList.contains("visible");
		if (isVisible) {
			detailsContent.classList.remove("visible");
			newToggleButton.innerHTML =
				'<i class="bi bi-chevron-down"></i> Show Error Details';
		} else {
			detailsContent.classList.add("visible");
			newToggleButton.innerHTML =
				'<i class="bi bi-chevron-up"></i> Hide Error Details';
		}
	});
}

/**
 * Handle error display setup for a visualization
 * @param {Object} config - Configuration object
 * @param {HTMLElement} config.messageElement - Element to display the error message
 * @param {HTMLElement} config.detailsContainer - Container for error details
 * @param {HTMLElement} config.detailsContent - Content element for error details
 * @param {HTMLElement} config.toggleButton - Button to toggle error details
 * @param {string} config.message - Error message to display
 * @param {Object} config.errorInfo - Error information object
 */
export function setupErrorDisplay({
	messageElement,
	detailsContainer,
	detailsContent,
	toggleButton,
	message,
	errorInfo,
}) {
	// Update the error message
	if (messageElement) {
		messageElement.textContent = message;
		if (messageElement.classList) {
			messageElement.classList.add("error-message-text");
		}
	}

	// Setup error details if we have error info
	if (
		errorInfo &&
		Object.keys(errorInfo).length > 0 &&
		detailsContainer &&
		detailsContent &&
		toggleButton
	) {
		// Format error details
		const detailsText = formatErrorDetails(errorInfo);
		detailsContent.textContent = detailsText;

		// Setup toggle functionality
		setupErrorDetailsToggle(toggleButton, detailsContent);

		// Show details container
		detailsContainer.classList.remove("d-none");
	} else if (detailsContainer) {
		// Hide details container if no error info
		detailsContainer.classList.add("d-none");
	}
}
