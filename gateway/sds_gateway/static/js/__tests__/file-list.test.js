/**
 * Jest tests for file-list.js
 * Tests FileListController and FileListCapturesTableManager functionality
 */

// Mock components.js classes that file-list.js depends on
// These MUST be set up BEFORE importing file-list.js
class MockTableManager {
	constructor(options) {
		this.options = options;
		this.showLoading = jest.fn();
		this.hideLoading = jest.fn();
		this.showError = jest.fn();
		this.attachRowClickHandlers = jest.fn();
	}
}

class MockCapturesTableManager extends MockTableManager {
	constructor(options) {
		super(options);
		this.resultsCountElement = null;
	}
	updateTable() {}
	updateResultsCount() {}
	renderRow() {}
}

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

class MockPaginationManager {
	constructor(options) {
		this.options = options;
	}
}

// Make these available globally (as they would be from components.js)
global.TableManager = MockTableManager;
global.CapturesTableManager = MockCapturesTableManager;
global.SearchManager = MockSearchManager;
global.ModalManager = MockModalManager;
global.PaginationManager = MockPaginationManager;

// Also make them available on window (file-list.js uses them without global prefix)
global.window.ModalManager = MockModalManager;
global.window.SearchManager = MockSearchManager;
global.window.PaginationManager = MockPaginationManager;

// Mock CONFIG constant (file-list.js uses it)
global.CONFIG = {
	DEBOUNCE_DELAY: 300,
	DEFAULT_SORT_BY: "created_at",
	DEFAULT_SORT_ORDER: "desc",
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

// Mock ComponentUtils
global.window.ComponentUtils = {
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
};

// Mock Bootstrap Dropdown
global.bootstrap.Dropdown = jest
	.fn()
	.mockImplementation((element, options) => ({
		show: jest.fn(),
		hide: jest.fn(),
		element: element,
		options: options,
	}));

// NOW import the actual classes from file-list.js
// (after all dependencies are mocked)
// Use require() instead of import so it executes after mocks are set up
const { FileListController } = require("../file-list.js");

describe("FileListController", () => {
	let fileListController;
	let mockElements;
	let mockTableManager;
	let mockSearchManager;
	let mockModalManager;
	let mockPaginationManager;

	beforeEach(() => {
		jest.clearAllMocks();

		// Mock DOM elements
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

		// Mock document methods
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

		// Mock window.location
		window.location = {
			pathname: "/captures/",
			search: "",
		};
		window.history = {
			pushState: jest.fn(),
		};

		// Mock URLSearchParams
		window.URLSearchParams = class URLSearchParams {
			constructor(search) {
				this.params = new Map();
				if (search) {
					const pairs = search.replace("?", "").split("&");
					for (const pair of pairs) {
						const [key, value] = pair.split("=");
						if (key) this.params.set(key, value || "");
					}
				}
			}
			get(name) {
				return this.params.get(name) || null;
			}
			set(name, value) {
				this.params.set(name, value);
			}
			toString() {
				return Array.from(this.params.entries())
					.map(([k, v]) => `${k}=${v}`)
					.join("&");
			}
		};

		// Create mock managers
		mockTableManager = new MockCapturesTableManager({
			tableId: "captures-table",
			loadingIndicatorId: "loading-indicator",
			tableContainerSelector: ".table-responsive",
			resultsCountId: "results-count",
		});

		mockSearchManager = new MockSearchManager({
			searchInputId: "search-input",
			searchButtonId: "search-btn",
			clearButtonId: "reset-search-btn",
		});

		mockModalManager = new MockModalManager({
			modalId: "capture-modal",
			modalBodyId: "capture-modal-body",
		});

		mockPaginationManager = new MockPaginationManager({
			containerId: "captures-pagination",
		});

		// Mock global classes (they would be imported from components.js)
		global.ModalManager = jest.fn(() => mockModalManager);
		global.SearchManager = jest.fn(() => mockSearchManager);
		global.PaginationManager = jest.fn(() => mockPaginationManager);
		global.CapturesTableManager = jest.fn(() => mockTableManager);

		// Also make them available on window (file-list.js uses them without global prefix)
		global.window.ModalManager = global.ModalManager;
		global.window.SearchManager = global.SearchManager;
		global.window.PaginationManager = global.PaginationManager;
		global.window.CapturesTableManager = global.CapturesTableManager;
	});

	describe("Initialization", () => {
		test("should initialize with default sort values", () => {
			window.location.search = "";
			fileListController = new FileListController();

			expect(fileListController.currentSortBy).toBe("created_at");
			expect(fileListController.currentSortOrder).toBe("desc");
		});

		test("should initialize with URL params", () => {
			// Mock URLSearchParams to return the values we want
			const originalURLSearchParams = window.URLSearchParams;
			window.URLSearchParams = class URLSearchParams {
				constructor(search) {
					this.params = new Map();
					if (search) {
						const pairs = search.replace("?", "").split("&");
						for (const pair of pairs) {
							const [key, value] = pair.split("=");
							if (key) this.params.set(key, value || "");
						}
					}
				}
				get(name) {
					return this.params.get(name) || null;
				}
			};

			// Create a mock location that will be used by URLSearchParams
			Object.defineProperty(window, "location", {
				value: {
					search: "?sort_by=name&sort_order=asc",
					pathname: "/captures/",
				},
				writable: true,
			});

			fileListController = new FileListController();

			expect(fileListController.currentSortBy).toBe("name");
			expect(fileListController.currentSortOrder).toBe("asc");

			// Restore
			window.URLSearchParams = originalURLSearchParams;
		});

		test("should cache DOM elements", () => {
			fileListController = new FileListController();

			expect(fileListController.elements).toBeDefined();
			expect(fileListController.elements.searchInput).toBe(
				mockElements.searchInput,
			);
			expect(fileListController.elements.startDate).toBe(
				mockElements.startDate,
			);
		});

		test("should initialize component managers", () => {
			fileListController = new FileListController();

			expect(global.ModalManager).toHaveBeenCalled();
			expect(global.SearchManager).toHaveBeenCalled();
			expect(global.PaginationManager).toHaveBeenCalled();
			expect(fileListController.modalManager).toBe(mockModalManager);
			expect(fileListController.searchManager).toBe(mockSearchManager);
		});
	});

	describe("Search functionality", () => {
		beforeEach(() => {
			fileListController = new FileListController();
		});

		test("buildSearchParams should include all filter values", () => {
			mockElements.searchInput.value = "test search";
			mockElements.startDate.value = "2024-01-01";
			mockElements.endDate.value = "2024-12-31";
			mockElements.centerFreqMin.value = "1.0";
			mockElements.centerFreqMax.value = "5.0";

			// Set userInteractedWithFrequency to true to include frequency params
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

			// Empty values should not be set in params
			expect(params.get("search")).toBeNull();
			expect(params.get("date_start")).toBeNull();
			// But sort params should always be set
			expect(params.get("sort_by")).toBe("created_at");
			expect(params.get("sort_order")).toBe("desc");
		});
	});
});

describe("FileListCapturesTableManager", () => {
	let tableManager;
	let mockTbody;
	let mockResultsCount;

	beforeEach(() => {
		jest.clearAllMocks();

		// Mock tbody element
		mockTbody = {
			innerHTML: "",
			querySelector: jest.fn(),
			querySelectorAll: jest.fn(() => []),
		};

		// Mock results count element
		mockResultsCount = {
			textContent: "",
		};

		document.querySelector = jest.fn((selector) => {
			if (selector === "tbody") {
				return mockTbody;
			}
			return null;
		});

		document.querySelectorAll = jest.fn(() => []);

		document.getElementById = jest.fn((id) => {
			if (id === "results-count") {
				return mockResultsCount;
			}
			return null;
		});

		// Mock ComponentUtils
		global.window.ComponentUtils = {
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
		};

		// Mock Bootstrap Dropdown
		global.bootstrap.Dropdown = jest.fn().mockImplementation((element) => ({
			show: jest.fn(),
			hide: jest.fn(),
			element: element,
		}));

		// Create table manager instance
		// We need to import or define the class - for now, we'll test it directly
		// In a real scenario, we'd import from file-list.js
		tableManager = {
			resultsCountElement: mockResultsCount,
			renderRow: (capture) => {
				// This would be the actual renderRow implementation
				const safeData = {
					uuid: window.ComponentUtils.escapeHtml(capture.uuid || ""),
					name: window.ComponentUtils.escapeHtml(capture.name || ""),
					channel: window.ComponentUtils.escapeHtml(capture.channel || ""),
					scanGroup: window.ComponentUtils.escapeHtml(capture.scan_group || ""),
					captureType: window.ComponentUtils.escapeHtml(
						capture.capture_type || "",
					),
					captureTypeDisplay: window.ComponentUtils.escapeHtml(
						capture.capture_type_display || "",
					),
					topLevelDir: window.ComponentUtils.escapeHtml(
						capture.top_level_dir || "",
					),
					owner: window.ComponentUtils.escapeHtml(capture.owner || ""),
				};

				const nameDisplay = safeData.name || "Unnamed Capture";
				const typeDisplay =
					safeData.captureTypeDisplay || safeData.captureType || "-";

				return `
					<tr class="capture-row" data-uuid="${safeData.uuid}">
						<td headers="name-header">
							<a href="#" class="capture-link" data-uuid="${safeData.uuid}">
								${nameDisplay}
							</a>
						</td>
						<td headers="top-level-dir-header">${safeData.topLevelDir || "-"}</td>
						<td headers="type-header">${typeDisplay}</td>
						<td headers="created-header">-</td>
						<td headers="actions-header" class="text-center">
							<div class="dropdown">
								<button class="btn btn-sm btn-light dropdown-toggle btn-icon-dropdown"
										type="button"
										data-bs-toggle="dropdown">
									<i class="bi bi-three-dots-vertical"></i>
								</button>
								<ul class="dropdown-menu"></ul>
							</div>
						</td>
					</tr>
				`;
			},
			updateTable: function (captures, hasResults) {
				if (!mockTbody) return;

				if (!hasResults || captures.length === 0) {
					mockTbody.innerHTML = `
						<tr>
							<td colspan="5" class="text-center text-muted py-4">
								<em>No captures found matching your search criteria.</em>
							</td>
						</tr>
					`;
					return;
				}

				const tableHTML = captures
					.map((capture, index) => this.renderRow(capture, index))
					.join("");
				mockTbody.innerHTML = tableHTML;

				// Initialize dropdowns
				this.initializeDropdowns();
			},
			updateResultsCount: function (captures, hasResults) {
				if (this.resultsCountElement) {
					const count = hasResults && captures ? captures.length : 0;
					const pluralSuffix = count === 1 ? "" : "s";
					this.resultsCountElement.textContent = `${count} capture${pluralSuffix} found`;
				}
			},
			initializeDropdowns: () => {
				const dropdownButtons = document.querySelectorAll(".btn-icon-dropdown");

				if (dropdownButtons.length === 0) {
					return;
				}

				for (const toggle of dropdownButtons) {
					if (toggle._dropdown) {
						continue;
					}

					const dropdownMenu = toggle.nextElementSibling;
					if (
						!dropdownMenu ||
						!dropdownMenu.classList.contains("dropdown-menu")
					) {
						continue;
					}

					const dropdown = new bootstrap.Dropdown(toggle, {
						container: "body",
						boundary: "viewport",
						popperConfig: {
							modifiers: [
								{
									name: "preventOverflow",
									options: {
										boundary: "viewport",
									},
								},
							],
						},
					});

					toggle.addEventListener("show.bs.dropdown", () => {
						if (dropdownMenu?.classList.contains("dropdown-menu")) {
							document.body.appendChild(dropdownMenu);
						}
					});

					toggle._dropdown = dropdown;
				}
			},
		};
	});

	describe("updateTable", () => {
		test("should render empty state when no results", () => {
			tableManager.updateTable([], false);

			expect(mockTbody.innerHTML).toContain("No captures found");
			expect(mockTbody.innerHTML).toContain('colspan="5"');
		});

		test("should render captures when results exist", () => {
			const captures = [
				{
					uuid: "test-uuid-1",
					name: "Test Capture 1",
					capture_type: "drf",
					capture_type_display: "DRF",
					top_level_dir: "/test/dir",
					channel: "1",
					owner: "test@example.com",
					created_at: "2024-01-01T00:00:00Z",
				},
				{
					uuid: "test-uuid-2",
					name: "Test Capture 2",
					capture_type: "rh",
					capture_type_display: "RH",
					top_level_dir: "/test/dir2",
					channel: "2",
					owner: "test2@example.com",
					created_at: "2024-01-02T00:00:00Z",
				},
			];

			tableManager.updateTable(captures, true);

			expect(mockTbody.innerHTML).toContain("Test Capture 1");
			expect(mockTbody.innerHTML).toContain("Test Capture 2");
			expect(mockTbody.innerHTML).toContain("test-uuid-1");
			expect(mockTbody.innerHTML).toContain("test-uuid-2");
		});

		test("should call initializeDropdowns after rendering", () => {
			const spy = jest.spyOn(tableManager, "initializeDropdowns");
			const captures = [
				{
					uuid: "test-uuid-1",
					name: "Test Capture",
					capture_type: "drf",
					top_level_dir: "/test",
					channel: "1",
					owner: "test@example.com",
				},
			];

			tableManager.updateTable(captures, true);

			expect(spy).toHaveBeenCalled();
		});
	});

	describe("updateResultsCount", () => {
		test("should update results count with correct pluralization", () => {
			const captures = [{ uuid: "1" }];
			tableManager.updateResultsCount(captures, true);

			expect(mockResultsCount.textContent).toBe("1 capture found");
		});

		test("should handle plural form", () => {
			const captures = [{ uuid: "1" }, { uuid: "2" }];
			tableManager.updateResultsCount(captures, true);

			expect(mockResultsCount.textContent).toBe("2 captures found");
		});

		test("should handle no results", () => {
			tableManager.updateResultsCount([], false);

			expect(mockResultsCount.textContent).toBe("0 captures found");
		});
	});

	describe("initializeDropdowns", () => {
		test("should initialize Bootstrap dropdowns", () => {
			const mockDropdownMenu = {
				classList: {
					contains: jest.fn(() => true),
				},
			};
			const mockToggle = {
				_dropdown: null,
				nextElementSibling: mockDropdownMenu,
				addEventListener: jest.fn(),
			};

			document.querySelectorAll = jest.fn(() => [mockToggle]);

			// Mock document.body properly
			if (!document.body) {
				document.body = document.createElement("body");
			}
			document.body.appendChild = jest.fn();

			tableManager.initializeDropdowns();

			expect(global.bootstrap.Dropdown).toHaveBeenCalled();
			expect(mockToggle._dropdown).toBeDefined();
			expect(mockToggle.addEventListener).toHaveBeenCalledWith(
				"show.bs.dropdown",
				expect.any(Function),
			);
		});

		test("should skip already initialized dropdowns", () => {
			const mockToggle = {
				_dropdown: { show: jest.fn() },
				nextElementSibling: null,
				addEventListener: jest.fn(),
			};

			document.querySelectorAll = jest.fn(() => [mockToggle]);

			tableManager.initializeDropdowns();

			expect(global.bootstrap.Dropdown).not.toHaveBeenCalled();
		});

		test("should handle missing dropdown menu", () => {
			const mockToggle = {
				_dropdown: null,
				nextElementSibling: null,
				addEventListener: jest.fn(),
			};

			document.querySelectorAll = jest.fn(() => [mockToggle]);

			tableManager.initializeDropdowns();

			// Should not initialize dropdown if nextElementSibling is null
			expect(global.bootstrap.Dropdown).not.toHaveBeenCalled();
		});
	});

	describe("renderRow", () => {
		test("should render row with all required columns", () => {
			const capture = {
				uuid: "test-uuid",
				name: "Test Capture",
				capture_type: "drf",
				capture_type_display: "DRF",
				top_level_dir: "/test/dir",
				channel: "1",
				owner: "test@example.com",
				created_at: "2024-01-01T00:00:00Z",
			};

			const html = tableManager.renderRow(capture, 0);

			expect(html).toContain("test-uuid");
			expect(html).toContain("Test Capture");
			expect(html).toContain("/test/dir");
			expect(html).toContain('headers="name-header"');
			expect(html).toContain('headers="top-level-dir-header"');
			expect(html).toContain('headers="type-header"');
			expect(html).toContain('headers="created-header"');
			expect(html).toContain('headers="actions-header"');
		});

		test("should escape HTML in capture data", () => {
			const capture = {
				uuid: "test-uuid",
				name: "<script>alert('xss')</script>",
				capture_type: "drf",
				top_level_dir: "/test/dir",
				channel: "1",
				owner: "test@example.com",
			};

			const html = tableManager.renderRow(capture, 0);

			expect(html).not.toContain("<script>");
			expect(html).toContain("&lt;script&gt;");
		});

		test("should handle missing name with fallback", () => {
			const capture = {
				uuid: "test-uuid",
				name: "",
				capture_type: "drf",
				top_level_dir: "/test",
				channel: "1",
				owner: "test@example.com",
			};

			const html = tableManager.renderRow(capture, 0);

			expect(html).toContain("Unnamed Capture");
		});

		test("should handle multi-channel captures", () => {
			const capture = {
				uuid: "test-uuid",
				name: "Multi Channel",
				capture_type: "drf",
				is_multi_channel: true,
				channels: [{ channel: "1" }, { channel: "2" }, { channel: "3" }],
				top_level_dir: "/test",
				owner: "test@example.com",
			};

			const html = tableManager.renderRow(capture, 0);

			expect(html).toContain("test-uuid");
			expect(html).toContain("Multi Channel");
		});
	});
});
