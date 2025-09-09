/**
 * WaterfallBase Class
 * Common functionality shared between waterfall components
 */

export const WaterfallBase = {
	/**
	 * Parse base64 waterfall data
	 */
	parseWaterfallData(base64Data) {
		try {
			const binaryString = atob(base64Data);
			const bytes = new Uint8Array(binaryString.length);
			for (let i = 0; i < binaryString.length; i++) {
				bytes[i] = binaryString.charCodeAt(i);
			}

			const floatArray = new Float32Array(bytes.buffer);
			return Array.from(floatArray);
		} catch (error) {
			console.error("Failed to parse waterfall data:", error);
			return null;
		}
	},

	/**
	 * Calculate power bounds from data array
	 */
	calculatePowerBounds(dataArray) {
		if (!dataArray || dataArray.length === 0) {
			return { min: -130, max: 0 };
		}

		let globalMin = Number.POSITIVE_INFINITY;
		let globalMax = Number.NEGATIVE_INFINITY;

		for (const data of dataArray) {
			if (data && data.length > 0) {
				const dataMin = Math.min(...data);
				const dataMax = Math.max(...data);

				globalMin = Math.min(globalMin, dataMin);
				globalMax = Math.max(globalMax, dataMax);
			}
		}

		// If we found valid data, use it; otherwise fall back to defaults
		if (globalMin !== Number.POSITIVE_INFINITY && globalMax !== Number.NEGATIVE_INFINITY) {
			// Add a small margin (5%) to the bounds for better visualization
			const margin = (globalMax - globalMin) * 0.05;
			return {
				min: globalMin - margin,
				max: globalMax + margin
			};
		}
		return { min: -130, max: 0 };
	},

	/**
	 * Get color for a normalized value (0-1) using viridis-like mapping
	 */
	getColorForValue(normalizedValue) {
		// Simple color mapping - can be enhanced with different color maps
		const r = Math.floor(normalizedValue * 255);
		const g = Math.floor((1 - normalizedValue) * 255);
		const b = 128;
		return `rgb(${r}, ${g}, ${b})`;
	},

	/**
	 * Format timestamp for display
	 */
	formatTimestamp(timestamp) {
		try {
			const date = new Date(timestamp);
			return date.toLocaleString();
		} catch {
			return timestamp;
		}
	},

	/**
	 * Normalize value to 0-1 range based on min/max bounds
	 */
	normalizeValue(value, min, max) {
		return Math.max(0, Math.min(1, (value - min) / (max - min)));
	}
}
