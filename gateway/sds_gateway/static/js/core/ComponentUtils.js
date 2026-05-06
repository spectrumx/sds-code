/**
 * Legacy HTML escaping and format delegates (prefer Django fragments long-term).
 * Migrated from deprecated/components.js.
 * Depends on window.FormatUtils (load FormatUtils.js first).
 */
const ComponentUtils = {
	escapeHtml(text) {
		if (!text) return "";
		const div = document.createElement("div");
		div.textContent = text;
		return div.innerHTML;
	},

	formatDate(dateString) {
		return window.FormatUtils.formatDate(dateString);
	},

	formatDateForModal(dateString) {
		return window.FormatUtils.formatDateForModal(dateString);
	},

	formatDateSimple(dateString) {
		return window.FormatUtils.formatDateSimple(dateString);
	},
};

if (typeof window !== "undefined") {
	window.ComponentUtils = ComponentUtils;
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { ComponentUtils };
}
