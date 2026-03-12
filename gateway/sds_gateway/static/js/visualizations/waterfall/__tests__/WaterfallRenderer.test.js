/**
 * Jest tests for WaterfallRenderer
 * Tests canvas drawing, color mapping, state setters, and overlay updates
 */

jest.mock("../constants.js", () => ({
	DEFAULT_COLOR_MAP: "viridis",
	DEFAULT_SCALE_MAX: 0,
	DEFAULT_SCALE_MIN: -130,
	PLOTS_LEFT_MARGIN: 85,
	PLOTS_RIGHT_MARGIN: 80,
	WATERFALL_BOTTOM_MARGIN: 5,
	WATERFALL_TOP_MARGIN: 5,
	WATERFALL_WINDOW_SIZE: 100,
}));

import "../WaterfallRenderer.js";

const WaterfallRenderer = window.WaterfallRenderer;

describe("WaterfallRenderer", () => {
	let canvas;
	let overlayCanvas;
	let mockCtx;
	let mockOverlayCtx;
	let renderer;

	function createMockCanvas() {
		const ctx = {
			clearRect: jest.fn(),
			fillStyle: "",
			fillRect: jest.fn(),
			fillText: jest.fn(),
			font: "",
			textAlign: "",
			strokeStyle: "",
			lineWidth: 0,
			strokeRect: jest.fn(),
		};
		return {
			width: 800,
			height: 400,
			style: { width: "", height: "" },
			getContext: jest.fn(() => ctx),
			parentElement: {
				getBoundingClientRect: () => ({ width: 800, height: 400 }),
			},
			_ctx: ctx,
		};
	}

	beforeEach(() => {
		canvas = createMockCanvas();
		mockCtx = canvas._ctx;
		overlayCanvas = createMockCanvas();
		mockOverlayCtx = overlayCanvas._ctx;

		renderer = new WaterfallRenderer(canvas, overlayCanvas);
	});

	describe("constructor and state", () => {
		test("should store canvas and overlay and get 2d contexts", () => {
			expect(renderer.canvas).toBe(canvas);
			expect(renderer.overlayCanvas).toBe(overlayCanvas);
			expect(renderer.ctx).toBe(mockCtx);
			expect(renderer.overlayCtx).toBe(mockOverlayCtx);
			expect(renderer.colorMap).toBe("viridis");
			expect(renderer.scaleMin).toBe(-130);
			expect(renderer.scaleMax).toBe(0);
			expect(renderer.currentSliceIndex).toBe(0);
			expect(renderer.waterfallWindowStart).toBe(0);
			expect(renderer.totalSlices).toBe(0);
			expect(renderer.hoveredSliceIndex).toBeNull();
		});

		test("should handle null canvas", () => {
			const r = new WaterfallRenderer(null, null);
			expect(r.ctx).toBeNull();
			expect(r.overlayCtx).toBeNull();
		});
	});

	describe("setters", () => {
		test("setColorMap should update colorMap", () => {
			renderer.setColorMap("plasma");
			expect(renderer.colorMap).toBe("plasma");
		});

		test("setScaleBounds should update scaleMin and scaleMax", () => {
			renderer.setScaleBounds(-100, 10);
			expect(renderer.scaleMin).toBe(-100);
			expect(renderer.scaleMax).toBe(10);
		});

		test("setCurrentSliceIndex should update currentSliceIndex", () => {
			renderer.setCurrentSliceIndex(5);
			expect(renderer.currentSliceIndex).toBe(5);
		});

		test("setWaterfallWindowStart should update waterfallWindowStart", () => {
			renderer.setWaterfallWindowStart(10);
			expect(renderer.waterfallWindowStart).toBe(10);
		});

		test("setTotalSlices should update totalSlices", () => {
			renderer.setTotalSlices(200);
			expect(renderer.totalSlices).toBe(200);
		});

		test("setHoveredSliceIndex should update hoveredSliceIndex", () => {
			renderer.setHoveredSliceIndex(3);
			expect(renderer.hoveredSliceIndex).toBe(3);
			renderer.setHoveredSliceIndex(null);
			expect(renderer.hoveredSliceIndex).toBeNull();
		});
	});

	describe("resizeCanvas", () => {
		test("should no-op when canvas or overlay is null", () => {
			renderer.canvas = null;
			renderer.resizeCanvas();
			expect(mockCtx.clearRect).not.toHaveBeenCalled();
		});

		test("should set canvas dimensions from container rect and clear overlay", () => {
			renderer.resizeCanvas();
			expect(canvas.width).toBe(800);
			expect(canvas.height).toBe(400);
			expect(overlayCanvas.width).toBe(800);
			expect(overlayCanvas.height).toBe(400);
			expect(mockOverlayCtx.clearRect).toHaveBeenCalledWith(0, 0, 800, 400);
		});
	});

	describe("renderWaterfall", () => {
		test("should return early when ctx or canvas is null", () => {
			renderer.ctx = null;
			renderer.renderWaterfall([], 10, 0);
			expect(mockCtx.clearRect).not.toHaveBeenCalled();
		});

		test("should clear canvas and draw slices with data", () => {
			const sliceData = new Array(64).fill(-50);
			const slices = [{ data: sliceData }];
			renderer.renderWaterfall(slices, 1, 0);
			expect(mockCtx.clearRect).toHaveBeenCalledWith(0, 0, 800, 400);
			expect(mockCtx.fillRect).toHaveBeenCalled();
		});

		test("should draw loading placeholder for missing slice", () => {
			renderer.renderWaterfall([null], 1, 0);
			expect(mockCtx.fillText).toHaveBeenCalledWith(
				"Loading...",
				expect.any(Number),
				expect.any(Number),
			);
		});

		test("should draw gap placeholder for slice with _gap", () => {
			renderer.renderWaterfall([{ _gap: true }], 1, 0);
			expect(mockCtx.fillText).toHaveBeenCalledWith(
				"No data",
				expect.any(Number),
				expect.any(Number),
			);
		});

		test("should use startIndex for data array indexing in streaming mode", () => {
			const sliceData = new Array(64).fill(-50);
			// startIndex 5: slice at window index 5 maps to dataIndex 0
			renderer.waterfallWindowStart = 5;
			renderer.renderWaterfall([{ data: sliceData }], 10, 5);
			expect(mockCtx.fillRect).toHaveBeenCalled();
		});
	});

	describe("getColorForPower", () => {
		test("should return rgb string for viridis", () => {
			renderer.colorMap = "viridis";
			const color = renderer.getColorForPower(0.5);
			expect(color).toMatch(/^rgb\(\d+,\s*\d+,\s*\d+\)$/);
		});

		test("should return rgb string for plasma", () => {
			renderer.colorMap = "plasma";
			const color = renderer.getColorForPower(0.25);
			expect(color).toMatch(/^rgb\(\d+,\s*\d+,\s*\d+\)$/);
		});

		test("should return gray for gray color map", () => {
			renderer.colorMap = "gray";
			const color = renderer.getColorForPower(0.5);
			expect(color).toBe("rgb(127, 127, 127)");
		});

		test("should return rgb for hot color map", () => {
			renderer.colorMap = "hot";
			const color = renderer.getColorForPower(0.5);
			expect(color).toMatch(/^rgb\(\d+,\s*\d+,\s*\d+\)$/);
		});

		test("should return rgb for inferno and magma", () => {
			renderer.colorMap = "inferno";
			expect(renderer.getColorForPower(0.33)).toMatch(/^rgb\(/);
			renderer.colorMap = "magma";
			expect(renderer.getColorForPower(0.5)).toMatch(/^rgb\(/);
		});

		test("should default to viridis-like for unknown color map", () => {
			renderer.colorMap = "unknown";
			const color = renderer.getColorForPower(0.5);
			expect(color).toMatch(/^rgb\(\d+,\s*\d+,\s*\d+\)$/);
		});
	});

	describe("overlay", () => {
		test("clearOverlay should clear overlay context", () => {
			renderer.clearOverlay();
			expect(mockOverlayCtx.clearRect).toHaveBeenCalledWith(0, 0, 800, 400);
		});

		test("updateOverlay should no-op when overlay or overlayCtx is null", () => {
			renderer.overlayCanvas = null;
			renderer.updateOverlay();
			expect(mockOverlayCtx.clearRect).not.toHaveBeenCalled();
		});

		test("updateOverlay should clear overlay and draw highlights", () => {
			renderer.totalSlices = 50;
			renderer.updateOverlay();
			expect(mockOverlayCtx.clearRect).toHaveBeenCalled();
			expect(mockOverlayCtx.strokeRect).toHaveBeenCalled();
		});
	});

	describe("generateColorMapGradient", () => {
		test("should return linear-gradient string with color stops", () => {
			const gradient = renderer.generateColorMapGradient();
			expect(gradient).toMatch(/^linear-gradient\(to bottom,/);
			expect(gradient).toContain("%");
		});
	});

	describe("destroy", () => {
		test("should null out canvas and contexts", () => {
			renderer.destroy();
			expect(renderer.canvas).toBeNull();
			expect(renderer.overlayCanvas).toBeNull();
			expect(renderer.ctx).toBeNull();
			expect(renderer.overlayCtx).toBeNull();
		});
	});
});
