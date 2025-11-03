/**
 * Waterfall Cache Manager
 * Manages loading and caching of waterfall slice data
 */

export class WaterfallCacheManager {
	constructor(totalSlices) {
		this.totalSlices = totalSlices;
		this.loadedSlices = new Set(); // Track which slice indices are loaded
		this.loadingRanges = new Set(); // Track which ranges are currently loading
		this.sliceData = new Map(); // Map of slice index -> parsed slice data
		this.maxConcurrentLoads = 3;
	}

	/**
	 * Check if a specific slice is loaded
	 */
	isSliceLoaded(index) {
		return this.loadedSlices.has(index);
	}

	/**
	 * Check if a range of slices is fully loaded
	 */
	isRangeLoaded(startIndex, endIndex) {
		for (let i = startIndex; i < endIndex; i++) {
			if (i >= this.totalSlices) break;
			if (!this.loadedSlices.has(i)) {
				return false;
			}
		}
		return true;
	}

	/**
	 * Get loaded slices for a range (may include nulls for unloaded slices)
	 */
	getRangeSlices(startIndex, endIndex) {
		const slices = [];
		for (let i = startIndex; i < endIndex; i++) {
			if (i >= this.totalSlices) break;
			slices.push(this.sliceData.get(i) || null);
		}
		return slices;
	}

	/**
	 * Add loaded slices to the cache
	 *
	 * @param {number} startIndex
	 * @param {Array} parsedSlices - Array of parsed slice data
	 */
	addLoadedSlices(startIndex, slices) {
		for (let i = 0; i < slices.length; i++) {
			const sliceIndex = startIndex + i;
			if (sliceIndex >= this.totalSlices) break;

			this.sliceData.set(sliceIndex, slices[i]);
			this.loadedSlices.add(sliceIndex);
		}
	}

	/**
	 * Get missing ranges that need to be loaded
	 */
	getMissingRanges(startIndex, endIndex) {
		const missingRanges = [];
		let rangeStart = null;

		for (let i = startIndex; i < endIndex; i++) {
			if (i >= this.totalSlices) break;

			if (!this.loadedSlices.has(i)) {
				if (rangeStart === null) {
					rangeStart = i;
				}
			} else {
				if (rangeStart !== null) {
					// End of missing range
					missingRanges.push([rangeStart, i]);
					rangeStart = null;
				}
			}
		}

		if (rangeStart !== null) {
			missingRanges.push([rangeStart, endIndex]);
		}

		return missingRanges;
	}

	/**
	 * Check if a range is currently being loaded
	 */
	isRangeLoading(startIndex, endIndex) {
		const rangeKey = `${startIndex}-${endIndex}`;
		return this.loadingRanges.has(rangeKey);
	}

	/**
	 * Mark a range as loading
	 */
	markRangeLoading(startIndex, endIndex) {
		const rangeKey = `${startIndex}-${endIndex}`;
		this.loadingRanges.add(rangeKey);
	}

	/**
	 * Mark a range as finished loading
	 */
	markRangeLoaded(startIndex, endIndex) {
		const rangeKey = `${startIndex}-${endIndex}`;
		this.loadingRanges.delete(rangeKey);
	}

	/**
	 * Get the number of loaded slices
	 */
	getLoadedCount() {
		return this.loadedSlices.size;
	}

	/**
	 * Clear all cached data
	 */
	clear() {
		this.loadedSlices.clear();
		this.loadingRanges.clear();
		this.sliceData.clear();
	}

	/**
	 * Update total slices (e.g., when metadata is loaded)
	 */
	setTotalSlices(totalSlices) {
		this.totalSlices = totalSlices;
	}
}
