/**
 * Jest tests for WaterfallControls
 * Tests UI state, event handlers, slice/window updates, and playback
 */

jest.mock("../constants.js", () => ({
	WATERFALL_WINDOW_SIZE: 100,
}));

import "../WaterfallControls.js";

const WaterfallControls = window.WaterfallControls;

describe("WaterfallControls", () => {
	let controls;
	let onSliceChange;
	let mockElements;

	beforeEach(() => {
		onSliceChange = jest.fn();
		mockElements = {};
		const ids = [
			"playPauseBtn",
			"currentSlice",
			"decrementSlice",
			"incrementSlice",
			"sliceIndexInput",
			"playbackSpeed",
			"colorMap",
			"scrollUpBtn",
			"scrollDownBtn",
			"sliceCounter",
			"sliceMinLabel",
			"sliceMaxLabel",
			"scrollIndicatorAbove",
			"scrollIndicatorBelow",
		];
		for (const id of ids) {
			mockElements[id] = {
				addEventListener: jest.fn(),
				removeEventListener: jest.fn(),
				value: "0",
				max: "0",
				min: "1",
				textContent: "",
				innerHTML: "",
				classList: { add: jest.fn(), remove: jest.fn(), toggle: jest.fn() },
				disabled: false,
				dispatchEvent: jest.fn(),
				blur: jest.fn(),
				tagName: "BUTTON",
			};
		}
		document.getElementById = jest.fn((id) => mockElements[id] || null);
		document.addEventListener = jest.fn();
		document.removeEventListener = jest.fn();

		controls = new WaterfallControls(onSliceChange);
	});

	describe("constructor", () => {
		test("should set initial state", () => {
			expect(controls.onSliceChange).toBe(onSliceChange);
			expect(controls.isPlaying).toBe(false);
			expect(controls.currentSliceIndex).toBe(0);
			expect(controls.totalSlices).toBe(0);
			expect(controls.waterfallWindowStart).toBe(0);
			expect(controls.WATERFALL_WINDOW_SIZE).toBe(100);
			expect(controls.playbackSpeed).toBe(1);
			expect(controls.isLoading).toBe(false);
		});
	});

	describe("setupEventListeners", () => {
		test("should attach listeners to existing elements", () => {
			controls.setupEventListeners();
			expect(document.getElementById).toHaveBeenCalledWith("playPauseBtn");
			expect(document.getElementById).toHaveBeenCalledWith("currentSlice");
			expect(mockElements.playPauseBtn.addEventListener).toHaveBeenCalledWith(
				"click",
				controls.handlePlayPause,
			);
			expect(document.addEventListener).toHaveBeenCalledWith(
				"keydown",
				controls.handleKeyDown,
			);
		});
	});

	describe("setTotalSlices and updateSliceSlider", () => {
		test("setTotalSlices should update totalSlices and call updateSliceSlider", () => {
			controls.setTotalSlices(200);
			expect(controls.totalSlices).toBe(200);
			expect(mockElements.currentSlice?.max).toBe(199);
			expect(mockElements.sliceCounter?.textContent).toContain("200");
			expect(mockElements.sliceMaxLabel?.textContent).toBe("200");
		});

		test("updateSliceCounter should update counter display", () => {
			controls.totalSlices = 50;
			controls.currentSliceIndex = 10;
			controls.updateSliceCounter();
			expect(mockElements.sliceCounter.textContent).toBe("10 / 50");
		});
	});

	describe("ensureSliceVisible", () => {
		test("should shift window down when current slice is below window", () => {
			controls.totalSlices = 200;
			controls.waterfallWindowStart = 50;
			controls.currentSliceIndex = 40;
			controls.ensureSliceVisible();
			expect(controls.waterfallWindowStart).toBe(40);
		});

		test("should shift window up when current slice is above window", () => {
			controls.totalSlices = 200;
			controls.waterfallWindowStart = 0;
			controls.currentSliceIndex = 150;
			controls.ensureSliceVisible();
			expect(controls.waterfallWindowStart).toBe(51); // 150 - 100 + 1
		});

		test("should clamp window to valid range", () => {
			controls.totalSlices = 50;
			controls.waterfallWindowStart = 0;
			controls.currentSliceIndex = 0;
			controls.ensureSliceVisible();
			expect(controls.waterfallWindowStart).toBe(0);
		});
	});

	describe("updateSliceButtons", () => {
		test("should disable decrement at index 0", () => {
			controls.currentSliceIndex = 0;
			controls.totalSlices = 100;
			controls.updateSliceButtons();
			expect(mockElements.decrementSlice.disabled).toBe(true);
			expect(mockElements.incrementSlice.disabled).toBe(false);
		});

		test("should disable increment at last slice", () => {
			controls.currentSliceIndex = 99;
			controls.totalSlices = 100;
			controls.updateSliceButtons();
			expect(mockElements.decrementSlice.disabled).toBe(false);
			expect(mockElements.incrementSlice.disabled).toBe(true);
		});
	});

	describe("setCurrentSliceIndex and setWaterfallWindowStart", () => {
		test("setCurrentSliceIndex should update index and call updateSliceUI when different", () => {
			controls.totalSlices = 100;
			controls.setCurrentSliceIndex(5);
			expect(controls.currentSliceIndex).toBe(5);
			expect(mockElements.currentSlice?.value).toBe(5);
		});

		test("setCurrentSliceIndex should not update when same value", () => {
			controls.currentSliceIndex = 3;
			controls.setCurrentSliceIndex(3);
			expect(controls.currentSliceIndex).toBe(3);
		});

		test("setWaterfallWindowStart should update and call updateScrollIndicators", () => {
			controls.totalSlices = 200;
			controls.setWaterfallWindowStart(50);
			expect(controls.waterfallWindowStart).toBe(50);
		});
	});

	describe("setLoading", () => {
		test("should set isLoading and call updateScrollIndicators", () => {
			controls.setLoading(true);
			expect(controls.isLoading).toBe(true);
			controls.setLoading(false);
			expect(controls.isLoading).toBe(false);
		});
	});

	describe("playback", () => {
		test("handlePlayPause should start playback when not playing", () => {
			controls.totalSlices = 100;
			controls.handlePlayPause();
			expect(controls.isPlaying).toBe(true);
			expect(mockElements.playPauseBtn.innerHTML).toContain("Pause");
		});

		test("handlePlayPause should stop playback when playing", () => {
			controls.totalSlices = 100;
			controls.handlePlayPause();
			expect(controls.isPlaying).toBe(true);
			controls.handlePlayPause();
			expect(controls.isPlaying).toBe(false);
			expect(mockElements.playPauseBtn.innerHTML).toContain("Play");
		});

		test("stopPlayback should clear requestAnimationFrame", () => {
			controls.totalSlices = 100;
			const cancelSpy = jest
				.spyOn(global, "cancelAnimationFrame")
				.mockImplementation(() => {});
			controls.handlePlayPause();
			controls.handlePlayPause();
			expect(cancelSpy).toHaveBeenCalled();
			cancelSpy.mockRestore();
		});
	});

	describe("slice change handlers", () => {
		test("handleSliceChange should update index and call onSliceChange", () => {
			controls.totalSlices = 100;
			mockElements.currentSlice.value = 25;
			controls.handleSliceChange({ target: mockElements.currentSlice });
			expect(controls.currentSliceIndex).toBe(25);
			expect(onSliceChange).toHaveBeenCalledWith(25, 0);
		});

		test("handleSliceChange should not call onSliceChange when index unchanged", () => {
			controls.totalSlices = 100;
			controls.currentSliceIndex = 10;
			mockElements.currentSlice.value = 10;
			controls.handleSliceChange({ target: mockElements.currentSlice });
			expect(onSliceChange).not.toHaveBeenCalled();
		});

		test("handleSliceIndexInputChange should accept valid 1-based input", () => {
			controls.totalSlices = 100;
			mockElements.sliceIndexInput.value = 26; // 1-based -> 25 0-based
			controls.handleSliceIndexInputChange({
				target: mockElements.sliceIndexInput,
			});
			expect(controls.currentSliceIndex).toBe(25);
			expect(onSliceChange).toHaveBeenCalledWith(25, 0);
		});

		test("handleSliceIndexInputChange should reset input when invalid", () => {
			controls.totalSlices = 100;
			controls.currentSliceIndex = 10;
			mockElements.sliceIndexInput.value = "999";
			const updateSpy = jest.spyOn(controls, "updateSliceIndexInput");
			controls.handleSliceIndexInputChange({
				target: mockElements.sliceIndexInput,
			});
			expect(updateSpy).toHaveBeenCalled();
		});

		test("handleDecrementSlice should decrement and call onSliceChange", () => {
			controls.totalSlices = 100;
			controls.currentSliceIndex = 5;
			controls.handleDecrementSlice();
			expect(controls.currentSliceIndex).toBe(4);
			expect(onSliceChange).toHaveBeenCalledWith(4, 0);
		});

		test("handleDecrementSlice should not go below 0", () => {
			controls.currentSliceIndex = 0;
			controls.handleDecrementSlice();
			expect(controls.currentSliceIndex).toBe(0);
			expect(onSliceChange).not.toHaveBeenCalled();
		});

		test("handleIncrementSlice should increment and call onSliceChange", () => {
			controls.totalSlices = 100;
			controls.currentSliceIndex = 5;
			controls.handleIncrementSlice();
			expect(controls.currentSliceIndex).toBe(6);
			expect(onSliceChange).toHaveBeenCalledWith(6, 0);
		});

		test("handleIncrementSlice should not exceed totalSlices - 1", () => {
			controls.totalSlices = 100;
			controls.currentSliceIndex = 99;
			controls.handleIncrementSlice();
			expect(controls.currentSliceIndex).toBe(99);
			expect(onSliceChange).not.toHaveBeenCalled();
		});
	});

	describe("scroll handlers", () => {
		test("handleScrollUp should move window up and call onSliceChange", () => {
			controls.totalSlices = 200;
			controls.waterfallWindowStart = 50;
			controls.currentSliceIndex = 75;
			controls.handleScrollUp();
			// Max window start = totalSlices - WATERFALL_WINDOW_SIZE = 100
			expect(controls.waterfallWindowStart).toBe(100);
			expect(onSliceChange).toHaveBeenCalledWith(100, 100); // slice kept in view
		});

		test("handleScrollDown should move window down and call onSliceChange", () => {
			controls.totalSlices = 200;
			controls.waterfallWindowStart = 100;
			controls.currentSliceIndex = 150;
			controls.handleScrollDown();
			expect(controls.waterfallWindowStart).toBe(0);
			expect(onSliceChange).toHaveBeenCalled();
		});

		test("handleScrollUp should no-op when isLoading", () => {
			controls.totalSlices = 200;
			controls.waterfallWindowStart = 50;
			controls.isLoading = true;
			controls.handleScrollUp();
			expect(controls.waterfallWindowStart).toBe(50);
			expect(onSliceChange).not.toHaveBeenCalled();
		});
	});

	describe("handleColorMapChange and emitEvent", () => {
		test("handleColorMapChange should dispatch waterfall:colorMapChanged", () => {
			const dispatchSpy = jest.spyOn(document, "dispatchEvent");
			mockElements.colorMap.value = "plasma";
			controls.handleColorMapChange({ target: mockElements.colorMap });
			expect(dispatchSpy).toHaveBeenCalled();
			const event = dispatchSpy.mock.calls[0][0];
			expect(event.type).toBe("waterfall:colorMapChanged");
			expect(event.detail).toEqual({ colorMap: "plasma" });
		});
	});

	describe("handleKeyDown", () => {
		test("should ignore when target is INPUT or SELECT", () => {
			const preventDefault = jest.fn();
			controls.handleKeyDown({
				key: "ArrowUp",
				preventDefault,
				target: { tagName: "INPUT" },
			});
			expect(preventDefault).not.toHaveBeenCalled();
		});

		test("should call handleDecrementSlice for ArrowDown", () => {
			const preventDefault = jest.fn();
			const decrementSpy = jest.spyOn(controls, "handleDecrementSlice");
			controls.handleKeyDown({
				key: "ArrowDown",
				preventDefault,
				target: { tagName: "DIV" },
			});
			expect(preventDefault).toHaveBeenCalled();
			expect(decrementSpy).toHaveBeenCalled();
		});

		test("should call handleScrollUp for PageUp", () => {
			const preventDefault = jest.fn();
			const scrollUpSpy = jest.spyOn(controls, "handleScrollUp");
			controls.handleKeyDown({
				key: "PageUp",
				preventDefault,
				target: { tagName: "DIV" },
			});
			expect(preventDefault).toHaveBeenCalled();
			expect(scrollUpSpy).toHaveBeenCalled();
		});
	});

	describe("setHoveredSliceIndex", () => {
		test("should update hoveredSliceIndex", () => {
			controls.setHoveredSliceIndex(7);
			expect(controls.hoveredSliceIndex).toBe(7);
		});
	});

	describe("destroy", () => {
		test("should stop playback and remove keydown listener", () => {
			controls.setupEventListeners();
			controls.totalSlices = 100;
			controls.handlePlayPause();
			controls.destroy();
			expect(controls.isPlaying).toBe(false);
			expect(document.removeEventListener).toHaveBeenCalledWith(
				"keydown",
				controls.handleKeyDown,
			);
		});
	});
});
