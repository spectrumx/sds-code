/**
 * Jest tests for captures file list page (FileListPageController).
 */

class MockSearchManager {
	constructor(options) {
		this.options = options;
	}
}

class MockModalManager {
	constructor(options) {
		this.options = options;
	}
}

const MockModalManagerConstructor = jest.fn(function MockMM(options) {
	return new MockModalManager(options);
});
MockModalManagerConstructor.attachDocumentCaptureClickDelegation = jest.fn(
	() => jest.fn(),
);

global.ModalManager = MockModalManagerConstructor;
global.window.ModalManager = MockModalManagerConstructor;
global.window.SearchManager = MockSearchManager;

global.window.FileListConfig = {
	DEBOUNCE_DELAY: 300,
	DEFAULT_SORT_BY: "created_at",
	DEFAULT_SORT_ORDER: "desc",
	MIN_LOADING_TIME: 500,
	ELEMENT_IDS: {
		SEARCH_INPUT: "search-input",
		START_DATE: "start_date",
		END_DATE: "end_date",
		CENTER_FREQ_MIN: "centerFreqMinInput",
		CENTER_FREQ_MAX: "centerFreqMaxInput",
		APPLY_FILTERS: "apply-filters-btn",
		CLEAR_FILTERS: "clear-filters-btn",
		ITEMS_PER_PAGE: "items-per-page",
	},
};

const { PageController } = require("../core/PageController.js");
const { PageLifecycleManager } = require("../core/PageLifecycleManager.js");
global.window.PageController = PageController;
global.window.PageLifecycleManager = PageLifecycleManager;

global.window.DOMUtils = {
	escapeHtml: jest.fn((str) => {
		if (!str) return "";
		return String(str)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#x27;");
	}),
	formatDateForModal: jest.fn((date) => {
		if (!date) return "-";
		const d = new Date(date);
		return d.toISOString().split("T")[0];
	}),
	initIconDropdowns: jest.fn(),
	renderLoading: jest.fn().mockResolvedValue(true),
	renderError: jest.fn().mockResolvedValue(true),
};

global.bootstrap.Dropdown = jest
	.fn()
	.mockImplementation((element, options) => ({
		show: jest.fn(),
		hide: jest.fn(),
		element: element,
		options: options,
	}));

const { FileListPageController } = require("../captures/FileListPageController.js");

describe("FileListPageController", () => {
	let fileListController;
	let mockElements;
	let mockSearchManager;
	let mockModalManager;
	let loadTableSpy;

	beforeEach(() => {
		jest.clearAllMocks();

		delete global.window.__FILE_LIST_PAGE_LIFECYCLE__;
		delete global.window.__FILE_LIST_LIST_REFRESH__;
		delete global.window.pageLifecycleManager;
		loadTableSpy = jest.fn().mockResolvedValue("<div></div>");
		global.window.listRefreshManager = { loadTable: loadTableSpy };

		mockElements = {
			searchInput: {
				value: "",
				addEventListener: jest.fn(),
			},
			startDate: { value: "", addEventListener: jest.fn() },
			endDate: { value: "", addEventListener: jest.fn() },
			centerFreqMin: { value: "", addEventListener: jest.fn() },
			centerFreqMax: { value: "", addEventListener: jest.fn() },
			applyFilters: { addEventListener: jest.fn() },
			clearFilters: { addEventListener: jest.fn() },
			itemsPerPage: { value: "25", addEventListener: jest.fn() },
			sortableHeaders: [],
			frequencyButton: { addEventListener: jest.fn() },
			frequencyCollapse: {},
			dateButton: { addEventListener: jest.fn() },
			dateCollapse: {},
		};

		document.getElementById = jest.fn((id) => {
			const idMap = {
				"search-input": mockElements.searchInput,
				start_date: mockElements.startDate,
				end_date: mockElements.endDate,
				centerFreqMinInput: mockElements.centerFreqMin,
				centerFreqMaxInput: mockElements.centerFreqMax,
				"apply-filters-btn": mockElements.applyFilters,
				"clear-filters-btn": mockElements.clearFilters,
				"items-per-page": mockElements.itemsPerPage,
				collapseFrequency: mockElements.frequencyCollapse,
				collapseDate: mockElements.dateCollapse,
				"captures-table": { classList: { contains: jest.fn(), add: jest.fn(), remove: jest.fn() }, addEventListener: jest.fn(), querySelector: jest.fn() },
				"add-captures-to-dataset-btn": null,
			};
			return idMap[id] || null;
		});

		document.querySelector = jest.fn((selector) => {
			if (selector === '[data-bs-target="#collapseFrequency"]') {
				return mockElements.frequencyButton;
			}
			if (selector === '[data-bs-target="#collapseDate"]') {
				return mockElements.dateButton;
			}
			if (selector === "th.sortable") {
				return [];
			}
			return null;
		});

		document.querySelectorAll = jest.fn(() => []);

		window.location = {
			pathname: "/users/capture-list/",
			search: "",
		};
		window.history = {
			pushState: jest.fn(),
		};

		window.URLSearchParams = class URLSearchParams {
			constructor(search) {
				this.params = new Map();
				const q = typeof search === "string" ? search.replace("?", "") : "";
				if (q) {
					for (const pair of q.split("&")) {
						const [key, value] = pair.split("=");
						if (key) this.params.set(key, decodeURIComponent(value || ""));
					}
				}
			}
			get(name) {
				return this.params.has(name) ? this.params.get(name) : null;
			}
			set(name, value) {
				this.params.set(name, value);
			}
			delete(name) {
				this.params.delete(name);
			}
			*entries() {
				yield* this.params.entries();
			}
			toString() {
				return Array.from(this.params.entries())
					.map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
					.join("&");
			}
		};

		mockSearchManager = new MockSearchManager({
			searchInputId: "search-input",
			searchButtonId: "search-btn",
			clearButtonId: "reset-search-btn",
		});

		mockModalManager = new MockModalManager({
			modalId: "capture-modal",
			modalBodyId: "capture-modal-body",
		});

		MockModalManagerConstructor.mockImplementation(() => mockModalManager);
		global.SearchManager = jest.fn(() => mockSearchManager);
		global.window.SearchManager = global.SearchManager;
	});

	describe("Initialization", () => {
		test("should initialize with default sort values", () => {
			window.location.search = "";
			fileListController = new FileListPageController();

			expect(fileListController.currentSortBy).toBe("created_at");
			expect(fileListController.currentSortOrder).toBe("desc");
		});

		test("should initialize with URL params", () => {
			Object.defineProperty(window, "location", {
				value: {
					search: "?sort_by=name&sort_order=asc",
					pathname: "/captures/",
				},
				writable: true,
			});

			fileListController = new FileListPageController();

			expect(fileListController.currentSortBy).toBe("name");
			expect(fileListController.currentSortOrder).toBe("asc");
		});

		test("should cache DOM elements", () => {
			fileListController = new FileListPageController();

			expect(fileListController.elements).toBeDefined();
			expect(fileListController.elements.searchInput).toBe(
				mockElements.searchInput,
			);
			expect(fileListController.elements.startDate).toBe(
				mockElements.startDate,
			);
		});

		test("should initialize component managers", () => {
			fileListController = new FileListPageController();

			expect(global.ModalManager).toHaveBeenCalled();
			expect(global.SearchManager).toHaveBeenCalled();
			expect(ModalManager.attachDocumentCaptureClickDelegation).toHaveBeenCalled();
			expect(fileListController.modalManager).toBe(mockModalManager);
			expect(fileListController.searchManager).toBe(mockSearchManager);
			expect(fileListController.listRefreshManager).toBe(
				global.window.listRefreshManager,
			);
		});
	});

	describe("Search functionality", () => {
		beforeEach(() => {
			fileListController = new FileListPageController();
		});

		test("buildSearchParams should include all filter values", () => {
			mockElements.searchInput.value = "test search";
			mockElements.startDate.value = "2024-01-01";
			mockElements.endDate.value = "2024-12-31";
			mockElements.centerFreqMin.value = "1.0";
			mockElements.centerFreqMax.value = "5.0";

			fileListController.userInteractedWithFrequency = true;

			const params = fileListController.buildSearchParams();

			expect(params.get("search")).toBe("test search");
			expect(params.get("date_start")).toBe("2024-01-01");
			expect(params.get("date_end")).toBe("2024-12-31T23:59:59");
			expect(params.get("min_freq")).toBe("1.0");
			expect(params.get("max_freq")).toBe("5.0");
			expect(params.get("sort_by")).toBe("created_at");
			expect(params.get("sort_order")).toBe("desc");
		});

		test("buildSearchParams should handle empty values", () => {
			mockElements.searchInput.value = "";
			mockElements.startDate.value = "";

			const params = fileListController.buildSearchParams();

			expect(params.get("search")).toBeNull();
			expect(params.get("date_start")).toBeNull();
			expect(params.get("sort_by")).toBe("created_at");
			expect(params.get("sort_order")).toBe("desc");
		});

		test("performSearch should load table via ListRefreshManager", async () => {
			jest.spyOn(window.history, "pushState").mockImplementation(() => {});
			await fileListController.performSearch();

			expect(loadTableSpy).toHaveBeenCalled();
			expect(window.history.pushState).toHaveBeenCalled();
		});
	});
});
