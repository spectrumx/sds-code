/**
 * Waterfall Slice Cache
 * Manages in-memory cache of waterfall slices with LRU eviction policy
 */

import { CACHE_SIZE } from "./constants.js";

class WaterfallSliceCache {
	constructor(maxSize = CACHE_SIZE) {
		this.maxSize = maxSize;
		// Map of sliceIndex -> slice data
		this.cache = new Map();
		// Track access order for LRU eviction (most recently used at end)
		this.accessOrder = [];
	}

	/**
	 * Get a single slice by index
	 * @param {number} sliceIndex - The slice index to retrieve
	 * @returns {Object|null} The slice data or null if not cached
	 */
	getSlice(sliceIndex) {
		if (this.cache.has(sliceIndex)) {
			// Update access order (move to end = most recently used)
			this._updateAccessOrder(sliceIndex);
			return this.cache.get(sliceIndex);
		}
		return null;
	}

	/**
	 * Get a range of slices
	 * @param {number} startIndex - Starting slice index (inclusive)
	 * @param {number} endIndex - Ending slice index (exclusive)
	 * @returns {Array} Array of cached slices (may contain nulls for missing slices)
	 */
	getSliceRange(startIndex, endIndex) {
		const slices = [];
		for (let i = startIndex; i < endIndex; i++) {
			const slice = this.getSlice(i);
			slices.push(slice);
		}
		return slices;
	}

	/**
	 * Check which slices in a range are missing from cache
	 * @param {number} startIndex - Starting slice index (inclusive)
	 * @param {number} endIndex - Ending slice index (exclusive)
	 * @returns {Array<number>} Array of missing slice indices
	 */
	getMissingSlices(startIndex, endIndex) {
		const missing = [];
		for (let i = startIndex; i < endIndex; i++) {
			if (!this.cache.has(i)) {
				missing.push(i);
			}
		}
		return missing;
	}

	/**
	 * Store a single slice in the cache
	 * @param {number} sliceIndex - The slice index
	 * @param {Object} sliceData - The slice data to cache
	 */
	setSlice(sliceIndex, sliceData) {
		// If already cached, just update access order
		if (this.cache.has(sliceIndex)) {
			this._updateAccessOrder(sliceIndex);
			this.cache.set(sliceIndex, sliceData);
			return;
		}

		// Check if we need to evict
		if (this.cache.size >= this.maxSize) {
			this._evictLRU();
		}

		// Add to cache
		this.cache.set(sliceIndex, sliceData);
		this.accessOrder.push(sliceIndex);
	}

	/**
	 * Store multiple slices in the cache
	 * @param {Array<Object>} slices - Array of slice objects with slice_index or custom_fields.slice_index
	 */
	setSlices(slices) {
		for (const slice of slices) {
			// Extract slice index from slice data
			const sliceIndex = slice.custom_fields?.slice_index ?? slice.slice_index;
			if (sliceIndex !== undefined) {
				this.setSlice(sliceIndex, slice);
			}
		}
	}

	/**
	 * Check if a slice is cached
	 * @param {number} sliceIndex - The slice index to check
	 * @returns {boolean} True if cached, false otherwise
	 */
	hasSlice(sliceIndex) {
		return this.cache.has(sliceIndex);
	}

	/**
	 * Get the number of cached slices
	 * @returns {number} Number of cached slices
	 */
	getSize() {
		return this.cache.size;
	}

	/**
	 * Clear all cached slices
	 */
	clear() {
		this.cache.clear();
		this.accessOrder = [];
	}

	/**
	 * Remove slices that are far from the given center index
	 * Used to evict slices outside the visible window
	 * @param {number} centerIndex - The center index to keep slices around
	 * @param {number} keepRange - Number of slices to keep on each side of center
	 */
	evictDistantSlices(centerIndex, keepRange) {
		const keepStart = Math.max(0, centerIndex - keepRange);
		const keepEnd = centerIndex + keepRange + 1; // +1 to make end inclusive

		const toRemove = [];
		for (const [sliceIndex] of this.cache) {
			if (sliceIndex < keepStart || sliceIndex >= keepEnd) {
				toRemove.push(sliceIndex);
			}
		}

		for (const sliceIndex of toRemove) {
			this._removeSlice(sliceIndex);
		}
	}

	/**
	 * Get cache statistics
	 * @returns {Object} Cache statistics
	 */
	getStats() {
		return {
			size: this.cache.size,
			maxSize: this.maxSize,
			utilization: (this.cache.size / this.maxSize) * 100,
		};
	}

	/**
	 * Update access order for LRU tracking
	 * @private
	 * @param {number} sliceIndex - The slice index that was accessed
	 */
	_updateAccessOrder(sliceIndex) {
		// Remove from current position
		const index = this.accessOrder.indexOf(sliceIndex);
		if (index > -1) {
			this.accessOrder.splice(index, 1);
		}
		// Add to end (most recently used)
		this.accessOrder.push(sliceIndex);
	}

	/**
	 * Evict the least recently used slice
	 * @private
	 */
	_evictLRU() {
		if (this.accessOrder.length === 0) return;

		// Remove the first item (least recently used)
		const lruIndex = this.accessOrder.shift();
		this.cache.delete(lruIndex);
	}

	/**
	 * Remove a slice from cache
	 * @private
	 * @param {number} sliceIndex - The slice index to remove
	 */
	_removeSlice(sliceIndex) {
		this.cache.delete(sliceIndex);
		const index = this.accessOrder.indexOf(sliceIndex);
		if (index > -1) {
			this.accessOrder.splice(index, 1);
		}
	}
}

// Make the class globally available
window.WaterfallSliceCache = WaterfallSliceCache;

export default WaterfallSliceCache;
