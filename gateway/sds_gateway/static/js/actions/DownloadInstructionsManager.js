/**
 * Download Instructions Manager
 * Handles all download instructions-related actions
 */
class DownloadInstructionsManager {
	/**
	 * Initialize download instructions manager
	 */
	constructor() {
		this.initializeEventListeners();
	}

	initializeEventListeners() {
		// Initialize event listeners for download instructions
		this.initializeCopyButtons();
	}

	initializeCopyButtons() {
		const manager = this;

		// Initialize copy buttons for download instructions
		const copyButtons = document.querySelectorAll(".copy-btn");

		for (const button of copyButtons) {
			button.addEventListener("click", function () {
				const targetId = this.getAttribute("data-clipboard-target");
				const codeElement = document.querySelector(targetId);

				if (codeElement) {
					const textToCopy = codeElement.textContent;

					// Use modern clipboard API if available
					if (navigator.clipboard && window.isSecureContext) {
						navigator.clipboard
							.writeText(textToCopy)
							.then(() => {
								manager.showCopySuccess(this);
							})
							.catch(() => {
								manager.fallbackCopyTextToClipboard(textToCopy, this);
							});
					} else {
						manager.fallbackCopyTextToClipboard(textToCopy, this);
					}
				}
			});
		}
	}

	showCopySuccess(button) {
		const originalText = button.innerHTML;
		button.innerHTML = '<i class="bi bi-check"></i> Copied!';
		button.classList.add("copied");

		setTimeout(() => {
			button.innerHTML = originalText;
			button.classList.remove("copied");
		}, 2000);
	}

	fallbackCopyTextToClipboard(text, button) {
		const textArea = document.createElement("textarea");
		textArea.value = text;
		textArea.style.position = "fixed";
		textArea.style.left = "-999999px";
		textArea.style.top = "-999999px";
		document.body.appendChild(textArea);
		textArea.focus();
		textArea.select();

		try {
			document.execCommand("copy");
			this.showCopySuccess(button);
		} catch (err) {
			console.error("Fallback: Oops, unable to copy", err);
		}

		document.body.removeChild(textArea);
	}
}

// Make class available globally
window.DownloadInstructionsManager = DownloadInstructionsManager;

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
	module.exports = { DownloadInstructionsManager };
}
