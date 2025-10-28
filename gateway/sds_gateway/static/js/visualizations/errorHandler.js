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
		return `An error occurred while processing. It may be due to an issue with the capture data.\n\n${lastLine}`;
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
 * Setup error details toggle button and content using Bootstrap Collapse
 */
export function setupErrorDetailsToggle(toggleButton, detailsContent) {
	// Initialize Bootstrap Collapse (initialized but controlled via data attributes on button)
	const _collapse = new bootstrap.Collapse(detailsContent, {
		toggle: false,
	});

	// Update button icon based on collapse state
	const updateButtonIcon = (isExpanded) => {
		toggleButton.innerHTML = isExpanded
			? '<i class="bi bi-chevron-up"></i> Hide Error Details'
			: '<i class="bi bi-chevron-down"></i> Show Error Details';
	};

	// Listen to collapse events to update button state
	detailsContent.addEventListener("shown.bs.collapse", () => {
		updateButtonIcon(true);
	});

	detailsContent.addEventListener("hidden.bs.collapse", () => {
		updateButtonIcon(false);
	});

	// Initial state
	updateButtonIcon(false);
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
