/**
 * Browser feature checks for gateway UI.
 * Merged from deprecated/files-ui.js (BrowserCompatibility) and
 * deprecated/file-manager.js (checkBrowserSupport).
 */
const BrowserSupport = {
	checkRequiredFeatures() {
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
			.filter(([name, supported]) => !supported)
			.map(([name]) => name);

		if (missingFeatures.length > 0) {
			console.warn("Missing browser features:", missingFeatures);
			return false;
		}

		return true;
	},

	checkBootstrapSupport() {
		return (
			"bootstrap" in window ||
			typeof bootstrap !== "undefined" ||
			document.querySelector("[data-bs-toggle]") !== null
		);
	},

	/**
	 * File manager / upload oriented checks.
	 * @returns {boolean}
	 */
	checkBrowserSupport() {
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
			.filter(([name, supported]) => !supported)
			.map(([name]) => name);

		if (missingFeatures.length > 0) {
			console.warn("Missing browser features:", missingFeatures);
			return false;
		}

		return true;
	},
};

if (typeof window !== "undefined") {
	window.BrowserSupport = BrowserSupport;
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { BrowserSupport };
}
