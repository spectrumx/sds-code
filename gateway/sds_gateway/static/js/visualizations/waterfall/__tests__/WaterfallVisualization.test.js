/**
 * Jest tests for WaterfallVisualization
 * Tests constructor, component initialization, canvas setup, event handlers, and destroy
 */

// Provide globals required by WaterfallVisualization (it uses them without import)
window.WaterfallRenderer = class MockWaterfallRenderer {
	constructor() {
		this.setColorMap = jest.fn();
		this.setScaleBounds = jest.fn();
		this.setCurrentSliceIndex = jest.fn();
		this.setWaterfallWindowStart = jest.fn();
		this.setTotalSlices = jest.fn();
		this.setHoveredSliceIndex = jest.fn();
		this.resizeCanvas = jest.fn();
		this.renderWaterfall = jest.fn();
		this.updateOverlay = jest.fn();
		this.generateColorMapGradient = jest
			.fn()
			.mockReturnValue("linear-gradient(to bottom, red, blue)");
		this.destroy = jest.fn();
		this.WATERFALL_WINDOW_SIZE = 100;
		this.TOP_MARGIN = 5;
		this.BOTTOM_MARGIN = 5;
	}
};

window.WaterfallControls = class MockWaterfallControls {
	constructor(onSliceChange) {
		this.onSliceChange = onSliceChange;
		this.setupEventListeners = jest.fn();
		this.setCurrentSliceIndex = jest.fn();
		this.setWaterfallWindowStart = jest.fn();
		this.setHoveredSliceIndex = jest.fn();
		this.updateSliceSlider = jest.fn();
		this.updateSliceUI = jest.fn();
		this.updateScrollIndicators = jest.fn();
		this.destroy = jest.fn();
		this.isPlaying = false;
	}
};

window.PeriodogramChart = class MockPeriodogramChart {
	constructor() {
		this.initialize = jest.fn();
		this.renderPeriodogram = jest.fn();
		this.showLoading = jest.fn();
		this.destroy = jest.fn();
	}
};

jest.mock("../../errorHandler.js", () => ({
	generateErrorMessage: jest.fn(() => ({
		message: "Error",
		errorDetail: null,
	})),
	setupErrorDisplay: jest.fn(),
}));

const mockCacheInstance = {
	getSlice: jest.fn(),
	getSliceRange: jest.fn(),
	getMissingSlices: jest.fn(() => []),
	setSlice: jest.fn(),
	setSlices: jest.fn(),
	clear: jest.fn(),
};
jest.mock("../WaterfallSliceCache.js", () => ({
	__esModule: true,
	default: jest.fn(() => mockCacheInstance),
}));

const mockLoaderInstance = {
	loadSliceRange: jest.fn().mockResolvedValue([]),
	setStreamingMode: jest.fn(),
	destroy: jest.fn(),
};
jest.mock("../WaterfallSliceLoader.js", () => ({
	__esModule: true,
	default: jest.fn(() => mockLoaderInstance),
}));

jest.mock("../constants.js", () => ({
	BATCH_SIZE: 300,
	DEFAULT_COLOR_MAP: "viridis",
	DEFAULT_SCALE_MAX: 0,
	DEFAULT_SCALE_MIN: -130,
	ERROR_MESSAGES: { API_ERROR: "API request failed" },
	LARGE_CAPTURE_THRESHOLD: 55000,
	PREFETCH_DISTANCE: 600,
	PREFETCH_TRIGGER: 200,
	WATERFALL_WINDOW_SIZE: 100,
	get_create_waterfall_endpoint: jest.fn(),
	get_waterfall_metadata_stream_endpoint: jest.fn(),
	get_waterfall_result_endpoint: jest.fn(),
	get_waterfall_status_endpoint: jest.fn(),
}));

import "../WaterfallVisualization.js";

const WaterfallVisualization = window.WaterfallVisualization;

describe("WaterfallVisualization", () => {
	const captureUuid = "test-capture-uuid";
	let canvas;
	let overlayCanvas;
	let visualization;

	beforeEach(() => {
		canvas = {
			addEventListener: jest.fn(),
			removeEventListener: jest.fn(),
			getBoundingClientRect: () => ({
				width: 800,
				height: 400,
				top: 0,
				left: 0,
			}),
			parentElement: {
				getBoundingClientRect: () => ({ width: 800, height: 400 }),
			},
			style: {},
		};
		overlayCanvas = {
			width: 800,
			height: 400,
			style: { width: "", height: "" },
			parentElement: {
				getBoundingClientRect: () => ({ width: 800, height: 400 }),
			},
		};
		document.getElementById = jest.fn((id) => {
			if (id === "waterfallCanvas") return canvas;
			if (id === "waterfallOverlayCanvas") return overlayCanvas;
			return null;
		});
		window.addEventListener = jest.fn();
		window.removeEventListener = jest.fn();
		jest.clearAllMocks();
	});

	describe("constructor", () => {
		test("should set captureUuid and initial state", () => {
			visualization = new WaterfallVisualization(captureUuid);
			expect(visualization.captureUuid).toBe(captureUuid);
			expect(visualization.waterfallRenderer).toBeNull();
			expect(visualization.controls).toBeNull();
			expect(visualization.sliceCache).toBeNull();
			expect(visualization.sliceLoader).toBeNull();
			expect(visualization.totalSlices).toBe(0);
			expect(visualization.currentSliceIndex).toBe(0);
			expect(visualization.waterfallWindowStart).toBe(0);
			expect(visualization.isStreamingMode).toBe(false);
			expect(visualization.colorMap).toBe("viridis");
		});
	});

	describe("initializeCanvas", () => {
		test("should throw when waterfall canvas is not found", () => {
			visualization = new WaterfallVisualization(captureUuid);
			document.getElementById = jest.fn(() => null);
			expect(() => visualization.initializeCanvas()).toThrow(
				"Waterfall canvas not found",
			);
		});

		test("should throw when overlay canvas is not found", () => {
			visualization = new WaterfallVisualization(captureUuid);
			document.getElementById = jest.fn((id) =>
				id === "waterfallCanvas" ? canvas : null,
			);
			expect(() => visualization.initializeCanvas()).toThrow(
				"Waterfall overlay canvas not found",
			);
		});

		test("should set canvas and overlay and add resize listener", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.initializeCanvas();
			expect(visualization.canvas).toBe(canvas);
			expect(visualization.overlayCanvas).toBe(overlayCanvas);
			expect(window.addEventListener).toHaveBeenCalledWith(
				"resize",
				visualization.resizeCanvas,
			);
		});
	});

	describe("initializeComponents", () => {
		test("should create cache, loader, renderer, periodogramChart, and controls", () => {
			const WaterfallSliceCache = require("../WaterfallSliceCache.js").default;
			const WaterfallSliceLoader =
				require("../WaterfallSliceLoader.js").default;
			visualization = new WaterfallVisualization(captureUuid);
			visualization.initializeCanvas();
			visualization.initializeComponents();
			expect(WaterfallSliceCache).toHaveBeenCalled();
			expect(WaterfallSliceLoader).toHaveBeenCalledWith(
				captureUuid,
				expect.anything(),
				expect.any(Function),
			);
			expect(visualization.sliceCache).toBe(mockCacheInstance);
			expect(visualization.sliceLoader).toBe(mockLoaderInstance);
			expect(visualization.waterfallRenderer).toBeInstanceOf(
				window.WaterfallRenderer,
			);
			expect(visualization.periodogramChart).toBeInstanceOf(
				window.PeriodogramChart,
			);
			expect(visualization.controls).toBeInstanceOf(window.WaterfallControls);
			expect(visualization.controls.setupEventListeners).toHaveBeenCalled();
		});

		test("onSliceChange callback should update indices and call renderer/controls", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.initializeCanvas();
			visualization.initializeComponents();
			const onSliceChange = visualization.controls.onSliceChange;
			expect(onSliceChange).toBeDefined();
			onSliceChange(10, 5);
			expect(visualization.currentSliceIndex).toBe(10);
			expect(visualization.waterfallWindowStart).toBe(5);
			expect(
				visualization.waterfallRenderer.setCurrentSliceIndex,
			).toHaveBeenCalledWith(10);
			expect(
				visualization.waterfallRenderer.setWaterfallWindowStart,
			).toHaveBeenCalledWith(5);
		});
	});

	describe("resizeCanvas", () => {
		test("should no-op when canvas or overlay is null", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.resizeCanvas();
			expect(window.removeEventListener).not.toHaveBeenCalled();
		});

		test("should set canvas dimensions and call renderer.resizeCanvas when components exist", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.initializeCanvas();
			visualization.initializeComponents();
			visualization.resizeCanvas();
			expect(visualization.waterfallRenderer.resizeCanvas).toHaveBeenCalled();
		});
	});

	describe("setupEventListeners", () => {
		test("should add click, mousemove, mouseleave to canvas", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.canvas = canvas;
			visualization.setupEventListeners();
			expect(canvas.addEventListener).toHaveBeenCalledWith(
				"click",
				visualization.handleCanvasClick,
			);
			expect(canvas.addEventListener).toHaveBeenCalledWith(
				"mousemove",
				visualization.handleCanvasMouseMove,
			);
			expect(canvas.addEventListener).toHaveBeenCalledWith(
				"mouseleave",
				visualization.handleCanvasMouseLeave,
			);
		});
	});

	describe("setupComponentEventListeners", () => {
		test("should add waterfall:colorMapChanged listener", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.waterfallRenderer = {
				setColorMap: jest.fn(),
				generateColorMapGradient: jest.fn(),
			};
			visualization.updateColorLegend = jest.fn();
			visualization.renderWaterfall = jest.fn();
			document.addEventListener = jest.fn();
			visualization.setupComponentEventListeners();
			expect(document.addEventListener).toHaveBeenCalledWith(
				"waterfall:colorMapChanged",
				expect.any(Function),
			);
			const handler = document.addEventListener.mock.calls.find(
				(c) => c[0] === "waterfall:colorMapChanged",
			)[1];
			handler({ detail: { colorMap: "plasma" } });
			expect(visualization.colorMap).toBe("plasma");
			expect(visualization.waterfallRenderer.setColorMap).toHaveBeenCalledWith(
				"plasma",
			);
		});
	});

	describe("updateSliceHighlights", () => {
		test("should call waterfallRenderer.updateOverlay", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.waterfallRenderer = { updateOverlay: jest.fn() };
			visualization.updateSliceHighlights();
			expect(visualization.waterfallRenderer.updateOverlay).toHaveBeenCalled();
		});

		test("should no-op when waterfallRenderer is null", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.waterfallRenderer = null;
			expect(() => visualization.updateSliceHighlights()).not.toThrow();
		});
	});

	describe("handleCanvasClick", () => {
		test("should no-op when canvas is null", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.canvas = null;
			visualization.handleCanvasClick({ clientY: 200 });
			expect(visualization.currentSliceIndex).toBe(0);
		});

		test("should update slice index when click is within bounds", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.canvas = canvas;
			visualization.totalSlices = 100;
			visualization.waterfallWindowStart = 0;
			visualization.waterfallRenderer = {
				WATERFALL_WINDOW_SIZE: 100,
				TOP_MARGIN: 5,
				BOTTOM_MARGIN: 5,
				setCurrentSliceIndex: jest.fn(),
				updateOverlay: jest.fn(),
			};
			visualization.controls = {
				setCurrentSliceIndex: jest.fn(),
			};
			visualization.renderPeriodogram = jest.fn();
			canvas.height = 400;
			// Click in middle of plot: plotHeight = 390, sliceHeight = 3.9, so many rows
			visualization.handleCanvasClick({ clientY: 205 });
			expect(
				visualization.waterfallRenderer.setCurrentSliceIndex,
			).toHaveBeenCalled();
			expect(visualization.controls.setCurrentSliceIndex).toHaveBeenCalled();
		});
	});

	describe("handleCanvasMouseLeave", () => {
		test("should clear hover state on renderer and controls", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.canvas = { style: {} };
			visualization.waterfallRenderer = {
				setHoveredSliceIndex: jest.fn(),
				updateOverlay: jest.fn(),
			};
			visualization.controls = { setHoveredSliceIndex: jest.fn() };
			visualization.handleCanvasMouseLeave();
			expect(
				visualization.waterfallRenderer.setHoveredSliceIndex,
			).toHaveBeenCalledWith(null);
			expect(visualization.controls.setHoveredSliceIndex).toHaveBeenCalledWith(
				null,
			);
			expect(visualization.waterfallRenderer.updateOverlay).toHaveBeenCalled();
		});
	});

	describe("destroy", () => {
		test("should cleanup loader, cache, renderer, periodogramChart, controls and remove listeners", () => {
			visualization = new WaterfallVisualization(captureUuid);
			visualization.initializeCanvas();
			visualization.initializeComponents();
			visualization.destroy();
			expect(mockLoaderInstance.destroy).toHaveBeenCalled();
			expect(mockCacheInstance.clear).toHaveBeenCalled();
			expect(visualization.waterfallRenderer.destroy).toHaveBeenCalled();
			expect(visualization.periodogramChart.destroy).toHaveBeenCalled();
			expect(visualization.controls.destroy).toHaveBeenCalled();
			expect(window.removeEventListener).toHaveBeenCalledWith(
				"resize",
				visualization.resizeCanvas,
			);
			expect(canvas.removeEventListener).toHaveBeenCalledWith(
				"click",
				visualization.handleCanvasClick,
			);
			expect(visualization.canvas).toBeNull();
			expect(visualization.sliceCache).toBeNull();
			expect(visualization.sliceLoader).toBeNull();
		});

		test("should not throw when components are null", () => {
			visualization = new WaterfallVisualization(captureUuid);
			expect(() => visualization.destroy()).not.toThrow();
		});
	});
});
