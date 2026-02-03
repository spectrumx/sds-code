/**
 * Waterfall Slice Loader
 * Handles API requests for waterfall slices with batching, debouncing, and retry logic
 */

import {
	BATCH_SIZE,
	get_waterfall_slices_endpoint,
	get_waterfall_slices_stream_endpoint,
} from "./constants.js";

class WaterfallSliceLoader {
	constructor(captureUuid, cache, onSliceLoaded = null) {
		this.captureUuid = captureUuid;
		this.cache = cache;
		this.onSliceLoaded = onSliceLoaded; // Callback when slices are loaded

		// Streaming mode flag - when true, uses on-demand FFT computation
		this.useStreamingEndpoint = false;

		// Request tracking
		this.pendingRequests = new Map(); // Map of request key -> Promise
		this.requestQueue = [];
		this.isProcessingQueue = false;

		// Retry configuration
		this.maxRetries = 3;
		this.retryDelay = 1000; // 1 second

		// Debounce configuration
		this.debounceDelay = 100; // 100ms debounce
		this.debounceTimer = null;
		this.debouncePendingPromises = []; // Store pending promises to resolve when timer fires
	}

	/**
	 * Enable or disable streaming mode (on-demand FFT computation)
	 * @param {boolean} enabled - Whether to use streaming endpoint
	 */
	setStreamingMode(enabled) {
		this.useStreamingEndpoint = enabled;
	}

	/**
	 * Load a range of slices
	 * @param {number} startIndex - Starting slice index (inclusive)
	 * @param {number} endIndex - Ending slice index (exclusive)
	 * @param {string} processingType - Processing type (default: "waterfall")
	 * @returns {Promise<Array>} Promise resolving to array of loaded slices
	 */
	async loadSliceRange(startIndex, endIndex, processingType = "waterfall") {
		// Check cache first
		const missing = this.cache.getMissingSlices(startIndex, endIndex);
		if (missing.length === 0) {
			// All slices are cached
			return this.cache.getSliceRange(startIndex, endIndex);
		}

		// Batch missing slices into optimal request sizes
		const batches = this._batchIndices(missing, BATCH_SIZE);

		// Load all batches
		const loadPromises = batches.map((batch) =>
			this._loadBatch(batch.start, batch.end, processingType),
		);

		await Promise.all(loadPromises);

		// Return all slices (now from cache)
		return this.cache.getSliceRange(startIndex, endIndex);
	}

	/**
	 * Load slices with debouncing (for rapid requests)
	 * @param {number} startIndex - Starting slice index
	 * @param {number} endIndex - Ending slice index
	 * @param {string} processingType - Processing type
	 * @returns {Promise<Array>} Promise resolving to loaded slices
	 */
	loadSliceRangeDebounced(startIndex, endIndex, processingType = "waterfall") {
		return new Promise((resolve, reject) => {
			// Store this promise to resolve when timer fires
			this.debouncePendingPromises.push({ resolve, reject });

			// Clear existing debounce timer
			if (this.debounceTimer) {
				clearTimeout(this.debounceTimer);
			}

			// Set new debounce timer
			this.debounceTimer = setTimeout(async () => {
				try {
					const slices = await this.loadSliceRange(
						startIndex,
						endIndex,
						processingType,
					);
					// Resolve all pending promises with the result
					const promises = this.debouncePendingPromises;
					this.debouncePendingPromises = [];
					for (const { resolve: resolvePromise } of promises) {
						resolvePromise(slices);
					}
				} catch (error) {
					// Reject all pending promises with the error
					const promises = this.debouncePendingPromises;
					this.debouncePendingPromises = [];
					for (const { reject: rejectPromise } of promises) {
						rejectPromise(error);
					}
				}
			}, this.debounceDelay);
		});
	}

	/**
	 * Prefetch slices ahead of the current window
	 * @param {number} currentStart - Current window start index
	 * @param {number} currentEnd - Current window end index
	 * @param {number} prefetchMargin - Number of slices to prefetch ahead
	 * @param {string} processingType - Processing type
	 */
	async prefetchAhead(
		currentStart,
		currentEnd,
		prefetchMargin = 50,
		processingType = "waterfall",
	) {
		const prefetchStart = currentEnd;
		const prefetchEnd = currentEnd + prefetchMargin;

		// Check what's missing
		const missing = this.cache.getMissingSlices(prefetchStart, prefetchEnd);
		if (missing.length === 0) return;

		// Load in background (don't await)
		this.loadSliceRange(prefetchStart, prefetchEnd, processingType).catch(
			(error) => {
				console.warn("Prefetch failed:", error);
			},
		);
	}

	/**
	 * Load a batch of slices from the API
	 * @private
	 * @param {number} startIndex - Starting slice index
	 * @param {number} endIndex - Ending slice index
	 * @param {string} processingType - Processing type
	 * @returns {Promise<Array>} Promise resolving to loaded slices
	 */
	async _loadBatch(startIndex, endIndex, processingType) {
		const requestKey = `${startIndex}-${endIndex}`;

		// Check if request is already pending
		if (this.pendingRequests.has(requestKey)) {
			return this.pendingRequests.get(requestKey);
		}

		// Create new request
		const requestPromise = this._fetchSlicesWithRetry(
			startIndex,
			endIndex,
			processingType,
		);

		this.pendingRequests.set(requestKey, requestPromise);

		try {
			const response = await requestPromise;
			const slices = response.slices || [];

			// Store in cache with index fallback
			// Use the position in the response array + startIndex if slice_index is missing
			const actualStartIndex = Number.parseInt(
				response.start_index ?? startIndex,
				10,
			);
			for (let i = 0; i < slices.length; i++) {
				const slice = slices[i];
				// Ensure sliceIndex is always a number (not string)
				const rawIndex =
					slice.custom_fields?.slice_index ??
					slice.slice_index ??
					actualStartIndex + i;
				const sliceIndex = Number.parseInt(rawIndex, 10);
				this.cache.setSlice(sliceIndex, slice);
			}

			// Notify callback
			if (this.onSliceLoaded) {
				this.onSliceLoaded(
					slices,
					actualStartIndex,
					actualStartIndex + slices.length,
				);
			}

			return slices;
		} catch (error) {
			console.error(`Failed to load slices ${startIndex}-${endIndex}:`, error);
			throw error;
		} finally {
			// Remove from pending requests
			this.pendingRequests.delete(requestKey);
		}
	}

	/**
	 * Fetch slices from API with retry logic
	 * @private
	 * @param {number} startIndex - Starting slice index
	 * @param {number} endIndex - Ending slice index
	 * @param {string} processingType - Processing type
	 * @param {number} retryCount - Current retry attempt
	 * @returns {Promise<Object>} Promise resolving to API response
	 */
	async _fetchSlicesWithRetry(
		startIndex,
		endIndex,
		processingType,
		retryCount = 0,
	) {
		try {
			// Use streaming endpoint if enabled, otherwise use preprocessed endpoint
			const url = this.useStreamingEndpoint
				? get_waterfall_slices_stream_endpoint(
						this.captureUuid,
						startIndex,
						endIndex,
					)
				: get_waterfall_slices_endpoint(
						this.captureUuid,
						startIndex,
						endIndex,
						processingType,
					);

			const response = await fetch(url, {
				method: "GET",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": this._getCSRFToken(),
				},
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(
					errorData.error || `HTTP ${response.status}: ${response.statusText}`,
				);
			}

			return await response.json();
		} catch (error) {
			// Retry on network errors or 5xx errors
			if (
				retryCount < this.maxRetries &&
				(error.message.includes("Failed to fetch") ||
					error.message.includes("HTTP 5"))
			) {
				// Exponential backoff
				const delay = this.retryDelay * 2 ** retryCount;
				await this._sleep(delay);

				return this._fetchSlicesWithRetry(
					startIndex,
					endIndex,
					processingType,
					retryCount + 1,
				);
			}

			// Max retries reached or non-retryable error
			throw error;
		}
	}

	/**
	 * Batch indices into optimal request sizes.
	 *
	 * This algorithm "fills gaps" - if missing indices are within batchSize of each other,
	 * they're combined into a single request. This reduces API calls at the cost of
	 * potentially fetching some already-cached slices (which just overwrite the cache).
	 *
	 * @private
	 * @param {Array<number>} indices - Array of missing slice indices
	 * @param {number} batchSize - Maximum batch size
	 * @returns {Array<Object>} Array of batch objects with start and end
	 */
	_batchIndices(indices, batchSize) {
		if (indices.length === 0) return [];

		// Sort indices
		const sorted = [...indices].sort((a, b) => a - b);

		const batches = [];
		let currentBatchStart = sorted[0];
		let currentBatchEnd = sorted[0] + 1;

		for (let i = 1; i < sorted.length; i++) {
			const index = sorted[i];

			// Check if including this index (and filling any gap) would exceed batch size
			const wouldBeEnd = index + 1;
			const wouldBeLength = wouldBeEnd - currentBatchStart;

			if (wouldBeLength <= batchSize) {
				// Include this index in current batch (filling any gap)
				currentBatchEnd = wouldBeEnd;
			} else {
				// Would exceed batch size - finalize current batch and start new one
				batches.push({
					start: currentBatchStart,
					end: currentBatchEnd,
				});
				currentBatchStart = index;
				currentBatchEnd = index + 1;
			}
		}

		// Add final batch
		batches.push({
			start: currentBatchStart,
			end: currentBatchEnd,
		});

		return batches;
	}

	/**
	 * Get CSRF token from form input
	 * @private
	 * @returns {string} CSRF token
	 */
	_getCSRFToken() {
		const token = document.querySelector("[name=csrfmiddlewaretoken]");
		if (!token) {
			console.warn(
				"WaterfallSliceLoader: CSRF token element '[name=csrfmiddlewaretoken]' not found. " +
					"API requests may fail due to missing CSRF token.",
			);
			return "";
		}
		return token.value;
	}

	/**
	 * Sleep utility for retry delays
	 * @private
	 * @param {number} ms - Milliseconds to sleep
	 * @returns {Promise} Promise that resolves after delay
	 */
	_sleep(ms) {
		return new Promise((resolve) => setTimeout(resolve, ms));
	}

	/**
	 * Cancel all pending requests
	 */
	cancelPendingRequests() {
		// Clear debounce timer
		if (this.debounceTimer) {
			clearTimeout(this.debounceTimer);
			this.debounceTimer = null;
		}

		// Clear pending requests
		this.pendingRequests.clear();
	}

	/**
	 * Cleanup resources
	 */
	destroy() {
		this.cancelPendingRequests();
		this.cache = null;
		this.onSliceLoaded = null;
	}
}

// Make the class globally available
window.WaterfallSliceLoader = WaterfallSliceLoader;

export default WaterfallSliceLoader;
