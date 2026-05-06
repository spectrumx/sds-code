/**
 * User notifications with de-duplication (files UI, uploads, etc.).
 * Migrated from deprecated/files-ui.js (ErrorHandler).
 */
const NotificationUtils = {
	shownMessages: new Set(),

	showError(message, context = "", error = null) {
		const messageKey = `${context}:${message}`;

		if (this.shownMessages.has(messageKey)) {
			if (error) {
				console.error(`FilesUI Error [${context}]:`, {
					message: error.message,
					stack: error.stack,
					userMessage: message,
					timestamp: new Date().toISOString(),
					userAgent: navigator.userAgent,
				});
			} else {
				console.warn(`FilesUI Warning [${context}]:`, message);
			}
			return;
		}

		this.shownMessages.add(messageKey);

		if (error) {
			console.error(`FilesUI Error [${context}]:`, {
				message: error.message,
				stack: error.stack,
				userMessage: message,
				timestamp: new Date().toISOString(),
				userAgent: navigator.userAgent,
			});
		} else {
			console.warn(`FilesUI Warning [${context}]:`, message);
		}

		if (window.components?.showError) {
			window.components.showError(message);
		} else {
			this.showFallbackError(message);
		}
	},

	showFallbackError(message) {
		const errorContainer = document.querySelector(
			".error-container, .alert-container, .files-container",
		);
		if (errorContainer) {
			const errorDiv = document.createElement("div");
			errorDiv.className = "alert alert-danger alert-dismissible fade show";
			errorDiv.innerHTML = `
				${message}
				<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
			`;
			errorContainer.insertBefore(errorDiv, errorContainer.firstChild);
		}
	},

	getUserFriendlyErrorMessage(error, context = "") {
		void context;
		if (!error) return "An unexpected error occurred";

		if (error.name === "TypeError" && error.message.includes("Cannot read")) {
			return "Configuration error: Some components are not properly loaded";
		}
		if (error.name === "ReferenceError") {
			return "Component error: Required functionality is not available";
		}

		return error.message || "An unexpected error occurred";
	},
};

/** @deprecated Use NotificationUtils */
const ErrorHandler = NotificationUtils;

if (typeof window !== "undefined") {
	window.NotificationUtils = NotificationUtils;
	window.ErrorHandler = ErrorHandler;
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { NotificationUtils, ErrorHandler };
}
