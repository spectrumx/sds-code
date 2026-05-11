/**
 * Global styles and visualization triggers.
 * Migrated from deprecated/components.js (tail section).
 */
const style = document.createElement("style");
style.textContent = `
  .edit-name-btn:hover i,
  .save-name-btn:hover i {
    color: white !important;
  }

  /* Hide native clear button in Chrome */
  input[type="search"]::-webkit-search-cancel-button {
    -webkit-appearance: none;
    display: none;
  }
`;
document.head.appendChild(style);

document.addEventListener("DOMContentLoaded", () => {
	if (!window.components) {
		// DOMUtils.js exposes a singleton on window.DOMUtils (not the class constructor).
		const domUtils =
			typeof window.DOMUtils?.showAlert === "function" ? window.DOMUtils : null;
		window.components = {
			showError(message) {
				if (domUtils) {
					domUtils.showAlert(message, "error");
				} else {
					console.error(message);
				}
			},
			showSuccess(message) {
				if (domUtils) {
					domUtils.showAlert(message, "success");
				} else {
					console.log(message);
				}
			},
		};
	}

	if (window.VisualizationModal) {
		window.visualizationModalInstance = new window.VisualizationModal();
	}

	document.addEventListener("click", (e) => {
		if (e.target.closest(".visualization-trigger-btn")) {
			const button = e.target.closest(".visualization-trigger-btn");
			const captureUuid = button.getAttribute("data-capture-uuid");
			const captureType = button.getAttribute("data-capture-type");

			if (captureUuid && captureType && window.visualizationModalInstance) {
				window.visualizationModalInstance.openWithCaptureData(
					captureUuid,
					captureType,
				);
			}
		}
	});
});
