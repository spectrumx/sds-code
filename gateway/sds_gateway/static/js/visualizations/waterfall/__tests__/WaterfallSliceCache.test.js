/**
 * Jest tests for WaterfallSliceCache
 * Tests LRU cache functionality for waterfall slices
 */

import WaterfallSliceCache from "../WaterfallSliceCache.js";

describe("WaterfallSliceCache", () => {
	let cache;

	beforeEach(() => {
		cache = new WaterfallSliceCache(5); // Use small cache size for testing
	});

	describe("Basic Cache Operations", () => {
		test("should store and retrieve a slice", () => {
			const sliceData = { data: "test", slice_index: 0 };
			cache.setSlice(0, sliceData);

			const retrieved = cache.getSlice(0);
			expect(retrieved).toEqual(sliceData);
		});

		test("should return null for non-existent slice", () => {
			const retrieved = cache.getSlice(999);
			expect(retrieved).toBeNull();
		});

		test("should check if slice exists", () => {
			cache.setSlice(0, { data: "test" });
			expect(cache.hasSlice(0)).toBe(true);
			expect(cache.hasSlice(1)).toBe(false);
		});

		test("should get cache size", () => {
			expect(cache.getSize()).toBe(0);
			cache.setSlice(0, { data: "test" });
			expect(cache.getSize()).toBe(1);
			cache.setSlice(1, { data: "test2" });
			expect(cache.getSize()).toBe(2);
		});

		test("should clear all cached slices", () => {
			cache.setSlice(0, { data: "test" });
			cache.setSlice(1, { data: "test2" });
			expect(cache.getSize()).toBe(2);

			cache.clear();
			expect(cache.getSize()).toBe(0);
			expect(cache.getSlice(0)).toBeNull();
			expect(cache.getSlice(1)).toBeNull();
		});
	});

	describe("Range Operations", () => {
		test("should get range of slices", () => {
			cache.setSlice(0, { data: "slice0" });
			cache.setSlice(1, { data: "slice1" });
			cache.setSlice(2, { data: "slice2" });

			const range = cache.getSliceRange(0, 3);
			expect(range).toHaveLength(3);
			expect(range[0]).toEqual({ data: "slice0" });
			expect(range[1]).toEqual({ data: "slice1" });
			expect(range[2]).toEqual({ data: "slice2" });
		});

		test("should return nulls for missing slices in range", () => {
			cache.setSlice(0, { data: "slice0" });
			cache.setSlice(2, { data: "slice2" });

			const range = cache.getSliceRange(0, 3);
			expect(range).toHaveLength(3);
			expect(range[0]).toEqual({ data: "slice0" });
			expect(range[1]).toBeNull();
			expect(range[2]).toEqual({ data: "slice2" });
		});

		test("should identify missing slices in range", () => {
			cache.setSlice(0, { data: "slice0" });
			cache.setSlice(2, { data: "slice2" });
			cache.setSlice(4, { data: "slice4" });

			const missing = cache.getMissingSlices(0, 5);
			expect(missing).toEqual([1, 3]);
		});

		test("should return empty array when all slices are cached", () => {
			cache.setSlice(0, { data: "slice0" });
			cache.setSlice(1, { data: "slice1" });

			const missing = cache.getMissingSlices(0, 2);
			expect(missing).toEqual([]);
		});
	});

	describe("Multiple Slices Operations", () => {
		test("should store multiple slices with custom_fields.slice_index", () => {
			const slices = [
				{ data: "slice0", custom_fields: { slice_index: 0 } },
				{ data: "slice1", custom_fields: { slice_index: 1 } },
				{ data: "slice2", custom_fields: { slice_index: 2 } },
			];

			cache.setSlices(slices);

			expect(cache.getSlice(0)).toEqual(slices[0]);
			expect(cache.getSlice(1)).toEqual(slices[1]);
			expect(cache.getSlice(2)).toEqual(slices[2]);
		});

		test("should store multiple slices with slice_index property", () => {
			const slices = [
				{ data: "slice0", slice_index: 0 },
				{ data: "slice1", slice_index: 1 },
			];

			cache.setSlices(slices);

			expect(cache.getSlice(0)).toEqual(slices[0]);
			expect(cache.getSlice(1)).toEqual(slices[1]);
		});

		test("should skip slices without index", () => {
			const slices = [
				{ data: "slice0", custom_fields: { slice_index: 0 } },
				{ data: "slice1" }, // No index
				{ data: "slice2", custom_fields: { slice_index: 2 } },
			];

			cache.setSlices(slices);

			expect(cache.getSlice(0)).toEqual(slices[0]);
			expect(cache.getSlice(1)).toBeNull();
			expect(cache.getSlice(2)).toEqual(slices[2]);
		});
	});

	describe("LRU Eviction", () => {
		test("should evict least recently used slice when cache is full", () => {
			// Fill cache to capacity
			for (let i = 0; i < 5; i++) {
				cache.setSlice(i, { data: `slice${i}` });
			}
			expect(cache.getSize()).toBe(5);

			// Access slices 0, 1, 2, 3 (making 4 the LRU)
			cache.getSlice(0);
			cache.getSlice(1);
			cache.getSlice(2);
			cache.getSlice(3);

			// Add new slice - should evict slice 4
			cache.setSlice(5, { data: "slice5" });

			expect(cache.getSize()).toBe(5);
			expect(cache.getSlice(4)).toBeNull(); // Evicted
			expect(cache.getSlice(5)).toEqual({ data: "slice5" }); // New slice
		});

		test("should update access order when slice is retrieved", () => {
			// Fill cache
			for (let i = 0; i < 5; i++) {
				cache.setSlice(i, { data: `slice${i}` });
			}

			// Access slice 0 (should move it to end of access order)
			cache.getSlice(0);

			// Add new slice - should evict slice 1 (not 0, since 0 was recently accessed)
			cache.setSlice(5, { data: "slice5" });

			expect(cache.getSlice(0)).not.toBeNull(); // Still cached
			expect(cache.getSlice(1)).toBeNull(); // Evicted
		});

		test("should update access order when slice is updated", () => {
			// Fill cache
			for (let i = 0; i < 5; i++) {
				cache.setSlice(i, { data: `slice${i}` });
			}

			// Update slice 0
			cache.setSlice(0, { data: "updated" });

			// Add new slice - should evict slice 1 (not 0)
			cache.setSlice(5, { data: "slice5" });

			expect(cache.getSlice(0)).toEqual({ data: "updated" });
			expect(cache.getSlice(1)).toBeNull();
		});
	});

	describe("Distant Slice Eviction", () => {
		test("should evict slices outside keep range", () => {
			// Create a cache large enough to hold all slices (maxSize >= 10)
			const largeCache = new WaterfallSliceCache(20);

			// Add slices 0-9
			for (let i = 0; i < 10; i++) {
				largeCache.setSlice(i, { data: `slice${i}` });
			}

			// Evict slices outside range 3-7 (center=5, keepRange=2)
			largeCache.evictDistantSlices(5, 2);

			// Slices 3, 4, 5, 6, 7 should remain
			for (let i = 3; i <= 7; i++) {
				expect(largeCache.hasSlice(i)).toBe(true);
			}

			// Slices 0, 1, 2, 8, 9 should be evicted
			for (const i of [0, 1, 2, 8, 9]) {
				expect(largeCache.hasSlice(i)).toBe(false);
			}
		});

		test("should handle center index at start", () => {
			for (let i = 0; i < 5; i++) {
				cache.setSlice(i, { data: `slice${i}` });
			}

			cache.evictDistantSlices(0, 2);

			// Slices 0, 1, 2 should remain
			for (let i = 0; i <= 2; i++) {
				expect(cache.hasSlice(i)).toBe(true);
			}

			// Slices 3, 4 should be evicted
			expect(cache.hasSlice(3)).toBe(false);
			expect(cache.hasSlice(4)).toBe(false);
		});
	});

	describe("Cache Statistics", () => {
		test("should return correct statistics", () => {
			cache.setSlice(0, { data: "slice0" });
			cache.setSlice(1, { data: "slice1" });

			const stats = cache.getStats();
			expect(stats.size).toBe(2);
			expect(stats.maxSize).toBe(5);
			expect(stats.utilization).toBe(40); // 2/5 * 100
		});

		test("should return 0% utilization for empty cache", () => {
			const stats = cache.getStats();
			expect(stats.size).toBe(0);
			expect(stats.utilization).toBe(0);
		});

		test("should return 100% utilization for full cache", () => {
			for (let i = 0; i < 5; i++) {
				cache.setSlice(i, { data: `slice${i}` });
			}

			const stats = cache.getStats();
			expect(stats.size).toBe(5);
			expect(stats.utilization).toBe(100);
		});
	});

	describe("Edge Cases", () => {
		test("should handle empty range", () => {
			const range = cache.getSliceRange(0, 0);
			expect(range).toEqual([]);

			const missing = cache.getMissingSlices(0, 0);
			expect(missing).toEqual([]);
		});

		test("should handle single slice range", () => {
			cache.setSlice(5, { data: "slice5" });

			const range = cache.getSliceRange(5, 6);
			expect(range).toHaveLength(1);
			expect(range[0]).toEqual({ data: "slice5" });
		});

		test("should handle very large indices", () => {
			const largeIndex = 1000000;
			cache.setSlice(largeIndex, { data: "large" });

			expect(cache.getSlice(largeIndex)).toEqual({ data: "large" });
			expect(cache.hasSlice(largeIndex)).toBe(true);
		});
	});
});
