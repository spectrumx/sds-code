/**
 * Date and display formatting helpers.
 * Migrated from deprecated/components.js (ComponentUtils).
 */
const FormatUtils = {
	formatDate(dateString) {
		if (!dateString) return "<div>-</div>";

		let date;

		// Try to parse the date string
		if (typeof dateString === "string") {
			// Handle different date formats
			if (dateString.includes("T")) {
				// ISO format: 2023-12-25T14:30:45.123Z
				date = new Date(dateString);
			} else if (dateString.includes("/") && dateString.includes(":")) {
				// Already formatted: 12/25/2023 2:30:45 PM
				date = new Date(dateString);
			} else {
				// Try to parse as-is
				date = new Date(dateString);
			}
		} else {
			date = new Date(dateString);
		}

		if (!date || Number.isNaN(date.getTime())) {
			return "<div>-</div>";
		}

		const month = String(date.getMonth() + 1).padStart(2, "0");
		const day = String(date.getDate()).padStart(2, "0");
		const year = date.getFullYear();
		const hours = date.getHours();
		const minutes = String(date.getMinutes()).padStart(2, "0");
		const seconds = String(date.getSeconds()).padStart(2, "0");
		const ampm = hours >= 12 ? "PM" : "AM";
		const displayHours = hours % 12 || 12;

		return `<div>${month}/${day}/${year}</div><small class="text-muted">${displayHours}:${minutes}:${seconds} ${ampm}</small>`;
	},

	/**
	 * Format date for modal display in the same style as dataset table
	 * @param {string} dateString - ISO date string
	 * @returns {string} Formatted date HTML
	 */
	formatDateForModal(dateString) {
		if (!dateString || dateString === "None") {
			return "N/A";
		}

		try {
			const date = new Date(dateString);
			if (Number.isNaN(date.getTime())) {
				return "N/A";
			}

			// Format date as YYYY-MM-DD
			const year = date.getFullYear();
			const month = String(date.getMonth() + 1).padStart(2, "0");
			const day = String(date.getDate()).padStart(2, "0");
			const dateFormatted = `${year}-${month}-${day}`;

			// Format time as HH:MM:SS T
			const hours = String(date.getHours()).padStart(2, "0");
			const minutes = String(date.getMinutes()).padStart(2, "0");
			const seconds = String(date.getSeconds()).padStart(2, "0");
			const timezone = date
				.toLocaleTimeString("en-US", { timeZoneName: "short" })
				.split(" ")[1];
			const timeFormatted = `${hours}:${minutes}:${seconds} ${timezone}`;

			return `<span class="bg-transparent pe-2">${dateFormatted}</span><span class="text-muted bg-transparent">${timeFormatted}</span>`;
		} catch (error) {
			console.error("Error formatting capture date:", error);
			return "N/A";
		}
	},

	/**
	 * Formats date for display (simple version)
	 * @param {string} dateString - ISO date string
	 * @returns {string} Formatted date
	 */
	formatDateSimple(dateString) {
		try {
			const date = new Date(dateString);
			return date.toString() !== "Invalid Date"
				? date.toLocaleDateString("en-US", {
						month: "2-digit",
						day: "2-digit",
						year: "numeric",
					})
				: "";
		} catch (e) {
			return "";
		}
	},
};

if (typeof window !== "undefined") {
	window.FormatUtils = FormatUtils;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { FormatUtils };
}

