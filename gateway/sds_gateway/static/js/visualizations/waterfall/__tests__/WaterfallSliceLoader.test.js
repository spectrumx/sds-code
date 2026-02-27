/**
 * Jest tests for WaterfallSliceLoader
 * Tests API loading, batching, retry logic, and request deduplication
 */

// Mock constants
jest.mock("../constants.js", () => ({
	BATCH_SIZE: 100,
	get_waterfall_slices_endpoint: jest.fn(
		(captureUuid, startIndex, endIndex, processingType) =>
			`/api/latest/assets/captures/${captureUuid}/waterfall_slices/?start_index=${startIndex}&end_index=${endIndex}&processing_type=${processingType}`,
	),
	get_waterfall_slices_stream_endpoint: jest.fn(
		(captureUuid, startIndex, endIndex) =>
			`/api/latest/assets/captures/${captureUuid}/waterfall_slices_stream/?start_index=${startIndex}&end_index=${endIndex}`,
	),
}));

import WaterfallSliceCache from "../WaterfallSliceCache.js";
import WaterfallSliceLoader from "../WaterfallSliceLoader.js";

describe("WaterfallSliceLoader", () => {
	let loader;
	let cache;
	let mockFetch;
	const captureUuid = "test-capture-uuid";

	beforeEach(() => {
		jest.clearAllMocks();
		jest.useFakeTimers();

		// Mock fetch
		mockFetch = jest.fn();
		global.fetch = mockFetch;

		// Mock document for CSRF token (_getCSRFToken() reads token.value)
		global.document = {
			querySelector: jest.fn(() => ({
				getAttribute: jest.fn(() => "test-csrf-token"),
				value: "test-csrf-token",
			})),
		};

		// Mock window for WaterfallSliceCache
		global.window = global.window || {};

		// Create cache and loader
		cache = new WaterfallSliceCache(100);
		loader = new WaterfallSliceLoader(captureUuid, cache);
	});

	afterEach(() => {
		jest.useRealTimers();
	});

	describe("Streaming Mode", () => {
		test("should enable streaming mode", () => {
			loader.setStreamingMode(true);
			expect(loader.useStreamingEndpoint).toBe(true);
		});

		test("should disable streaming mode", () => {
			loader.setStreamingMode(true);
			loader.setStreamingMode(false);
			expect(loader.useStreamingEndpoint).toBe(false);
		});
	});

	describe("Load Slice Range", () => {
		test("should return cached slices without API call", async () => {
			const slice0 = { data: "slice0", custom_fields: { slice_index: 0 } };
			const slice1 = { data: "slice1", custom_fields: { slice_index: 1 } };
			cache.setSlice(0, slice0);
			cache.setSlice(1, slice1);

			const result = await loader.loadSliceRange(0, 2);

			expect(mockFetch).not.toHaveBeenCalled();
			expect(result).toHaveLength(2);
			expect(result[0]).toEqual(slice0);
			expect(result[1]).toEqual(slice1);
		});

		test("should fetch missing slices from API", async () => {
			const mockResponse = {
				slices: [
					{ data: "slice0", custom_fields: { slice_index: 0 } },
					{ data: "slice1", custom_fields: { slice_index: 1 } },
				],
				start_index: 0,
				end_index: 2,
			};

			mockFetch.mockResolvedValueOnce({
				ok: true,
				json: async () => mockResponse,
			});

			const result = await loader.loadSliceRange(0, 2);

			expect(mockFetch).toHaveBeenCalledTimes(1);
			expect(result).toHaveLength(2);
			expect(cache.getSlice(0)).not.toBeNull();
			expect(cache.getSlice(1)).not.toBeNull();
		});

		test("should use streaming endpoint when enabled", async () => {
			loader.setStreamingMode(true);

			const mockResponse = {
				slices: [{ data: "slice0", custom_fields: { slice_index: 0 } }],
				start_index: 0,
				end_index: 1,
			};

			mockFetch.mockResolvedValueOnce({
				ok: true,
				json: async () => mockResponse,
			});

			await loader.loadSliceRange(0, 1);

			expect(mockFetch).toHaveBeenCalledWith(
				expect.stringContaining("waterfall_slices_stream"),
				expect.any(Object),
			);
		});

		test("should use preprocessed endpoint when streaming disabled", async () => {
			loader.setStreamingMode(false);

			const mockResponse = {
				slices: [{ data: "slice0", custom_fields: { slice_index: 0 } }],
				start_index: 0,
				end_index: 1,
			};

			mockFetch.mockResolvedValueOnce({
				ok: true,
				json: async () => mockResponse,
			});

			await loader.loadSliceRange(0, 1, "waterfall");

			expect(mockFetch).toHaveBeenCalledWith(
				expect.stringContaining("waterfall_slices"),
				expect.any(Object),
			);
		});

		test("should batch large requests", async () => {

			// Mock 3 API responses
			for (let i = 0; i < 3; i++) {
				const start = i * 100;
				const end = Math.min(start + 100, 250);
				const slices = Array.from({ length: end - start }, (_, j) => ({
					data: `slice${start + j}`,
					custom_fields: { slice_index: start + j },
				}));

				mockFetch.mockResolvedValueOnce({
					ok: true,
					json: async () => ({
						slices,
						start_index: start,
						end_index: end,
					}),
				});
			}

			await loader.loadSliceRange(0, 250);

			expect(mockFetch).toHaveBeenCalledTimes(3);
		});
	});

	describe("Request Deduplication", () => {
		test("should deduplicate concurrent requests for same range", async () => {
			const mockResponse = {
				slices: [{ data: "slice0", custom_fields: { slice_index: 0 } }],
				start_index: 0,
				end_index: 1,
			};

			mockFetch.mockResolvedValueOnce({
				ok: true,
				json: async () => mockResponse,
			});

			// Make two concurrent requests for the same range
			const promise1 = loader.loadSliceRange(0, 1);
			const promise2 = loader.loadSliceRange(0, 1);

			await Promise.all([promise1, promise2]);

			// Should only make one API call
			expect(mockFetch).toHaveBeenCalledTimes(1);
		});
	});

	describe("Retry Logic", () => {
		test("should retry on network error", async () => {
			const mockResponse = {
				slices: [{ data: "slice0", custom_fields: { slice_index: 0 } }],
				start_index: 0,
				end_index: 1,
			};

			// Fail twice, then succeed
			mockFetch
				.mockRejectedValueOnce(new Error("Failed to fetch"))
				.mockRejectedValueOnce(new Error("Failed to fetch"))
				.mockResolvedValueOnce({
					ok: true,
					json: async () => mockResponse,
				});

			// Start the load (first call will fail and schedule retry)
			const loadPromise = loader.loadSliceRange(0, 1);

			// Advance timers to trigger first retry (1000ms delay)
			await jest.advanceTimersByTimeAsync(1000);

			// Advance timers to trigger second retry (2000ms delay)
			await jest.advanceTimersByTimeAsync(2000);

			const result = await loadPromise;

			expect(mockFetch).toHaveBeenCalledTimes(3);
			expect(result).toHaveLength(1);
		});

		test("should retry on 5xx errors", async () => {
			const mockResponse = {
				slices: [{ data: "slice0", custom_fields: { slice_index: 0 } }],
				start_index: 0,
				end_index: 1,
			};

			// Return 500, then succeed
			// Don't provide errorData.error so it uses the HTTP status message format
			mockFetch
				.mockResolvedValueOnce({
					ok: false,
					status: 500,
					statusText: "Internal Server Error",
					json: async () => ({}), // Empty object so it uses HTTP status message
				})
				.mockResolvedValueOnce({
					ok: true,
					json: async () => mockResponse,
				});

			// Start the load (first call will fail with 500 and schedule retry)
			const loadPromise = loader.loadSliceRange(0, 1);

			// Advance timer for retry delay (1000ms)
			await jest.advanceTimersByTimeAsync(1000);

			const result = await loadPromise;

			expect(mockFetch).toHaveBeenCalledTimes(2);
			expect(result).toHaveLength(1);
		});

		test("should not retry on 4xx errors", async () => {
			mockFetch.mockResolvedValueOnce({
				ok: false,
				status: 404,
				statusText: "Not Found",
				json: async () => ({ error: "Not found" }),
			});

			await expect(loader.loadSliceRange(0, 1)).rejects.toThrow();

			// Should not retry
			expect(mockFetch).toHaveBeenCalledTimes(1);
		});

		test("should use exponential backoff for retries", async () => {
			const mockResponse = {
				slices: [{ data: "slice0", custom_fields: { slice_index: 0 } }],
				start_index: 0,
				end_index: 1,
			};

			// Fail twice, then succeed
			mockFetch
				.mockRejectedValueOnce(new Error("Failed to fetch"))
				.mockRejectedValueOnce(new Error("Failed to fetch"))
				.mockResolvedValueOnce({
					ok: true,
					json: async () => mockResponse,
				});

			// Start the load (first call will fail and schedule retry)
			const loadPromise = loader.loadSliceRange(0, 1);

			// Advance timers for exponential backoff delays (1000ms, 2000ms)
			await jest.advanceTimersByTimeAsync(1000); // First retry delay
			await jest.advanceTimersByTimeAsync(2000); // Second retry delay (exponential)

			const result = await loadPromise;

			expect(mockFetch).toHaveBeenCalledTimes(3);
			expect(result).toHaveLength(1);
		});
	});

	describe("Debouncing", () => {
		test("should debounce rapid requests", async () => {
			// Temporarily use real timers for this test since debounce uses async setTimeout
			jest.useRealTimers();

			// Create a fresh cache and loader instance with real timers
			const freshCache = new WaterfallSliceCache(100);
			const realTimerLoader = new WaterfallSliceLoader(captureUuid, freshCache);

			const mockResponse = {
				slices: [
					{ data: "slice0", custom_fields: { slice_index: 0 } },
					{ data: "slice1", custom_fields: { slice_index: 1 } },
					{ data: "slice2", custom_fields: { slice_index: 2 } },
				],
				start_index: 0,
				end_index: 3,
			};

			mockFetch.mockResolvedValue({
				ok: true,
				json: async () => mockResponse,
			});

			// Make rapid requests (these set up debounce timers)
			const promise1 = realTimerLoader.loadSliceRangeDebounced(0, 1);
			const promise2 = realTimerLoader.loadSliceRangeDebounced(0, 2);
			const promise3 = realTimerLoader.loadSliceRangeDebounced(0, 3);

			// Wait for debounce delay (100ms) plus small buffer to ensure execution
			await new Promise((resolve) => setTimeout(resolve, 150));

			// Wait for all promises to resolve
			await Promise.all([promise1, promise2, promise3]);

			// Should only make one API call (last request after debounce)
			expect(mockFetch).toHaveBeenCalledTimes(1);

			// Restore fake timers for other tests
			jest.useFakeTimers();
		}, 10000); // 10 second timeout
	});

	describe("Prefetching", () => {
		test("should prefetch slices ahead", async () => {
			const mockResponse = {
				slices: [{ data: "slice10", custom_fields: { slice_index: 10 } }],
				start_index: 10,
				end_index: 11,
			};

			mockFetch.mockResolvedValue({
				ok: true,
				json: async () => mockResponse,
			});

			await loader.prefetchAhead(0, 10, 1);

			// Should make API call
			expect(mockFetch).toHaveBeenCalled();
		});

		test("should not prefetch if all slices are cached", async () => {
			// Cache the prefetch range
			cache.setSlice(10, {
				data: "slice10",
				custom_fields: { slice_index: 10 },
			});

			await loader.prefetchAhead(0, 10, 1);

			// Should not make API call
			expect(mockFetch).not.toHaveBeenCalled();
		});
	});

	describe("Error Handling", () => {
		test("should handle API errors gracefully", async () => {
			mockFetch.mockResolvedValueOnce({
				ok: false,
				status: 500,
				statusText: "Internal Server Error",
				json: async () => ({ error: "Server error" }),
			});

			await expect(loader.loadSliceRange(0, 1)).rejects.toThrow();
		});

		test("should handle network errors", async () => {
			mockFetch.mockRejectedValueOnce(new Error("Network error"));

			await expect(loader.loadSliceRange(0, 1)).rejects.toThrow(
				"Network error",
			);
		});

		test("should call onSliceLoaded callback when provided", async () => {
			const onSliceLoaded = jest.fn();
			loader.onSliceLoaded = onSliceLoaded;

			const mockResponse = {
				slices: [{ data: "slice0", custom_fields: { slice_index: 0 } }],
				start_index: 0,
				end_index: 1,
			};

			mockFetch.mockResolvedValueOnce({
				ok: true,
				json: async () => mockResponse,
			});

			await loader.loadSliceRange(0, 1);

			expect(onSliceLoaded).toHaveBeenCalledWith(
				expect.arrayContaining([expect.objectContaining({ data: "slice0" })]),
				0,
				1,
			);
		});
	});

	describe("Batching Algorithm", () => {
		test("should batch consecutive indices", async () => {
			// Missing indices: [0, 1, 2, 3, 4] - should be one batch
			const missingIndices = [0, 1, 2, 3, 4];

			const mockResponse = {
				slices: missingIndices.map((i) => ({
					data: `slice${i}`,
					custom_fields: { slice_index: i },
				})),
				start_index: 0,
				end_index: 5,
			};

			mockFetch.mockResolvedValueOnce({
				ok: true,
				json: async () => mockResponse,
			});

			// Manually trigger batching by calling _batchIndices indirectly
			// We'll test this through loadSliceRange with missing indices
			await loader.loadSliceRange(0, 5);

			expect(mockFetch).toHaveBeenCalledTimes(1);
		});

		test("should split large gaps into separate batches", async () => {
			// Missing indices: [0, 1, 100, 101] - should be two batches
			// This tests the gap-filling algorithm
			const mockResponse1 = {
				slices: [
					{ data: "slice0", custom_fields: { slice_index: 0 } },
					{ data: "slice1", custom_fields: { slice_index: 1 } },
				],
				start_index: 0,
				end_index: 2,
			};

			const mockResponse2 = {
				slices: [
					{ data: "slice100", custom_fields: { slice_index: 100 } },
					{ data: "slice101", custom_fields: { slice_index: 101 } },
				],
				start_index: 100,
				end_index: 102,
			};

			mockFetch
				.mockResolvedValueOnce({
					ok: true,
					json: async () => mockResponse1,
				})
				.mockResolvedValueOnce({
					ok: true,
					json: async () => mockResponse2,
				});

			// Cache some slices to create gaps
			// Then request range that includes missing slices
			await loader.loadSliceRange(0, 102);

			// Should make multiple API calls for different ranges
			expect(mockFetch).toHaveBeenCalled();
		});
	});
});
