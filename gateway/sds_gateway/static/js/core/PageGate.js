/**
 * Single entry for environment checks, shared chrome styles, and visualization wiring.
 */
(function pageGateModule() {
	if (typeof window === "undefined") return;

	function checkRequiredFeatures() {
		const requiredFeatures = {
			"DOM API": "document" in window && "addEventListener" in document,
			"Console API": "console" in window && "log" in console,
			Map: "Map" in window,
			Set: "Set" in window,
			"Template Literals": (() => {
				try {
					const test = `test${1}`;
					return test === "test1";
				} catch {
					return false;
				}
			})(),
		};

		const missingFeatures = Object.entries(requiredFeatures)
			.filter(([, supported]) => !supported)
			.map(([name]) => name);

		if (missingFeatures.length > 0) {
			console.warn("Missing browser features:", missingFeatures);
			return false;
		}
		return true;
	}

	function checkBootstrapPresent() {
		return (
			"bootstrap" in window ||
			typeof bootstrap !== "undefined" ||
			document.querySelector("[data-bs-toggle]") !== null
		);
	}

	function checkUploadFeatures() {
		const requiredFeatures = {
			"File API": "File" in window,
			FileReader: "FileReader" in window,
			FormData: "FormData" in window,
			"Fetch API": "fetch" in window,
			Promise: "Promise" in window,
			Map: "Map" in window,
			Set: "Set" in window,
		};

		const missingFeatures = Object.entries(requiredFeatures)
			.filter(([, supported]) => !supported)
			.map(([name]) => name);

		if (missingFeatures.length > 0) {
			console.warn("Missing browser features:", missingFeatures);
			return false;
		}
		return true;
	}

	function injectGatewayChromeStyles() {
		if (document.getElementById("gateway-chrome-styles")) return;
		const style = document.createElement("style");
		style.id = "gateway-chrome-styles";
		style.textContent = `
  .edit-name-btn:hover i,
  .save-name-btn:hover i {
    color: white !important;
  }

  input[type="search"]::-webkit-search-cancel-button {
    -webkit-appearance: none;
    display: none;
  }
`;
		document.head.appendChild(style);
	}

	function wireVisualizationTriggers() {
		if (window.VisualizationModal && !window.visualizationModalInstance) {
			window.visualizationModalInstance = new window.VisualizationModal();
		}

		if (window.__visualizationTriggerBound) return;
		window.__visualizationTriggerBound = true;

		document.addEventListener("click", (e) => {
			const button = e.target.closest?.(".visualization-trigger-btn");
			if (!button) return;
			const captureUuid = button.getAttribute("data-capture-uuid");
			const captureType = button.getAttribute("data-capture-type");

			if (
				captureUuid &&
				captureType &&
				window.visualizationModalInstance &&
				typeof window.visualizationModalInstance.openWithCaptureData ===
					"function"
			) {
				window.visualizationModalInstance.openWithCaptureData(
					captureUuid,
					captureType,
				);
			}
		});
	}

	function onReady(fn) {
		if (document.readyState === "loading") {
			document.addEventListener("DOMContentLoaded", fn, { once: true });
		} else {
			fn();
		}
	}

	function runOnce() {
		if (window.__pageGateRan) return;
		window.__pageGateRan = true;

		if (!checkRequiredFeatures()) {
			void window.DOMUtils?.showError?.(
				"Your browser doesn't support required features. Please use a modern browser.",
				"browser-compatibility",
			);
			return;
		}

		injectGatewayChromeStyles();

		onReady(() => {
			if (!checkBootstrapPresent()) {
				console.warn(
					"Bootstrap not detected. Some UI features may not work properly.",
				);
			}
			wireVisualizationTriggers();
		});
	}

	window.PageGate = {
		runOnce,
		checkRequiredFeatures,
		checkBootstrapPresent,
		checkUploadFeatures,
		injectGatewayChromeStyles,
		wireVisualizationTriggers,
	};

	runOnce();
})();

if (typeof module !== "undefined" && module.exports) {
	module.exports = {};
}
