/**
 * Jest tests for KeywordChipInput
 * Tests keyword chip input functionality, autocomplete, and initialization helpers
 */

// Import classes and functions
// Note: These are exported to window, so we'll access them via window in tests
import "../KeywordChipInput.js";

describe("KeywordChipInput", () => {
	let chipInput;
	let mockInput;
	let mockHiddenInput;
	let mockChipContainer;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Create mock DOM elements
		mockChipContainer = document.createElement("div");
		mockChipContainer.className = "keyword-chips-wrapper";

		mockInput = document.createElement("input");
		mockInput.type = "text";
		mockInput.className = "keyword-input";
		mockChipContainer.appendChild(mockInput);

		mockHiddenInput = document.createElement("input");
		mockHiddenInput.type = "hidden";
		mockHiddenInput.id = "keywords-hidden";
		mockHiddenInput.value = "";

		// Add to document body for proper DOM structure
		document.body.appendChild(mockChipContainer);
		document.body.appendChild(mockHiddenInput);

		// Mock parentElement
		Object.defineProperty(mockInput, "parentElement", {
			get: () => mockChipContainer,
			configurable: true,
		});
	});

	afterEach(() => {
		// Clean up DOM
		if (mockChipContainer.parentNode) {
			mockChipContainer.parentNode.removeChild(mockChipContainer);
		}
		if (mockHiddenInput.parentNode) {
			mockHiddenInput.parentNode.removeChild(mockHiddenInput);
		}
	});

	describe("Initialization", () => {
		test("should initialize with input and hidden input elements", () => {
			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);

			expect(chipInput.input).toBe(mockInput);
			expect(chipInput.hiddenInput).toBe(mockHiddenInput);
			expect(chipInput.chips).toEqual([]);
			expect(chipInput.chipContainer).toBe(mockChipContainer);
		});

		test("should load existing keywords from hidden input", () => {
			mockHiddenInput.value = "keyword1,keyword2,keyword3";

			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);

			expect(chipInput.chips).toEqual(["keyword1", "keyword2", "keyword3"]);
		});

		test("should handle empty hidden input", () => {
			mockHiddenInput.value = "";

			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);

			expect(chipInput.chips).toEqual([]);
		});

		test("should trim whitespace from loaded keywords", () => {
			mockHiddenInput.value = " keyword1 , keyword2 , keyword3 ";

			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);

			expect(chipInput.chips).toEqual(["keyword1", "keyword2", "keyword3"]);
		});

		test("should filter out empty keywords", () => {
			mockHiddenInput.value = "keyword1,,keyword2, ,keyword3";

			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);

			expect(chipInput.chips).toEqual(["keyword1", "keyword2", "keyword3"]);
		});

		test("should setup event listeners on initialization", () => {
			const keydownSpy = jest.spyOn(mockInput, "addEventListener");
			const blurSpy = jest.spyOn(mockInput, "addEventListener");
			const pasteSpy = jest.spyOn(mockInput, "addEventListener");

			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);

			expect(keydownSpy).toHaveBeenCalledWith("keydown", expect.any(Function));
			expect(blurSpy).toHaveBeenCalledWith("blur", expect.any(Function));
			expect(pasteSpy).toHaveBeenCalledWith("paste", expect.any(Function));
		});
	});

	describe("Adding Chips", () => {
		beforeEach(() => {
			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);
		});

		test("should add a chip from input value", () => {
			mockInput.value = "newkeyword";

			chipInput.addChip("newkeyword");

			expect(chipInput.chips).toContain("newkeyword");
			expect(mockInput.value).toBe("");
			expect(mockHiddenInput.value).toBe("newkeyword");
		});

		test("should prevent duplicate chips", () => {
			chipInput.chips = ["existing"];

			chipInput.addChip("existing");

			expect(chipInput.chips).toEqual(["existing"]);
			expect(chipInput.chips.length).toBe(1);
		});

		test("should not add empty chips", () => {
			chipInput.addChip("");
			chipInput.addChip("   ");

			expect(chipInput.chips).toEqual([]);
		});

		test("should render chips after adding", () => {
			chipInput.addChip("keyword1");
			chipInput.addChip("keyword2");

			const chips = mockChipContainer.querySelectorAll(".keyword-chip");
			expect(chips.length).toBe(2);
		});

		test("should update hidden input when adding chips", () => {
			chipInput.addChip("keyword1");
			chipInput.addChip("keyword2");

			expect(mockHiddenInput.value).toBe("keyword1,keyword2");
		});
	});

	describe("Removing Chips", () => {
		beforeEach(() => {
			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);
			chipInput.chips = ["keyword1", "keyword2", "keyword3"];
		});

		test("should remove chip by index", () => {
			chipInput.removeChip(1);

			expect(chipInput.chips).toEqual(["keyword1", "keyword3"]);
			expect(mockHiddenInput.value).toBe("keyword1,keyword3");
		});

		test("should remove chip by keyword", () => {
			chipInput.removeChipByKeyword("keyword2");

			expect(chipInput.chips).toEqual(["keyword1", "keyword3"]);
		});

		test("should not remove chip if index is out of bounds", () => {
			const originalChips = [...chipInput.chips];

			chipInput.removeChip(10);
			chipInput.removeChip(-1);

			expect(chipInput.chips).toEqual(originalChips);
		});

		test("should not remove chip if keyword not found", () => {
			const originalChips = [...chipInput.chips];

			chipInput.removeChipByKeyword("nonexistent");

			expect(chipInput.chips).toEqual(originalChips);
		});

		test("should focus input after removing chip", () => {
			const focusSpy = jest.spyOn(mockInput, "focus");

			chipInput.removeChip(0);

			expect(focusSpy).toHaveBeenCalled();
		});

		test("should update hidden input when removing chips", () => {
			chipInput.removeChip(1);

			expect(mockHiddenInput.value).toBe("keyword1,keyword3");
		});
	});

	describe("Keyboard Events", () => {
		beforeEach(() => {
			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);
		});

		test("should create chip on comma key", () => {
			mockInput.value = "newkeyword";
			const event = new KeyboardEvent("keydown", { key: "," });

			mockInput.dispatchEvent(event);

			expect(chipInput.chips).toContain("newkeyword");
			expect(mockInput.value).toBe("");
		});

		test("should create chip on Enter key", () => {
			mockInput.value = "newkeyword";
			const event = new KeyboardEvent("keydown", { key: "Enter" });

			mockInput.dispatchEvent(event);

			expect(chipInput.chips).toContain("newkeyword");
			expect(mockInput.value).toBe("");
		});

		test("should remove last chip on Backspace when input is empty", () => {
			chipInput.chips = ["keyword1", "keyword2"];
			mockInput.value = "";

			const event = new KeyboardEvent("keydown", { key: "Backspace" });
			mockInput.dispatchEvent(event);

			expect(chipInput.chips).toEqual(["keyword1"]);
		});

		test("should not remove chip on Backspace when input has value", () => {
			chipInput.chips = ["keyword1"];
			mockInput.value = "text";

			const event = new KeyboardEvent("keydown", { key: "Backspace" });
			mockInput.dispatchEvent(event);

			expect(chipInput.chips).toEqual(["keyword1"]);
		});

		test("should not remove chip on Backspace when no chips exist", () => {
			chipInput.chips = [];
			mockInput.value = "";

			const event = new KeyboardEvent("keydown", { key: "Backspace" });
			mockInput.dispatchEvent(event);

			expect(chipInput.chips).toEqual([]);
		});
	});

	describe("Blur Event", () => {
		beforeEach(() => {
			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);
		});

		test("should add chip on blur if input has value", () => {
			mockInput.value = "newkeyword";

			mockInput.dispatchEvent(new Event("blur"));

			expect(chipInput.chips).toContain("newkeyword");
			expect(mockInput.value).toBe("");
		});

		test("should not add chip on blur if input is empty", () => {
			mockInput.value = "";

			mockInput.dispatchEvent(new Event("blur"));

			expect(chipInput.chips).toEqual([]);
		});

		test("should not add chip on blur if input only has whitespace", () => {
			mockInput.value = "   ";

			mockInput.dispatchEvent(new Event("blur"));

			expect(chipInput.chips).toEqual([]);
		});
	});

	describe("Paste Event", () => {
		beforeEach(() => {
			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);
			jest.useFakeTimers();
		});

		afterEach(() => {
			jest.useRealTimers();
		});

		test("should parse comma-separated pasted values", () => {
			mockInput.value = "keyword1,keyword2,keyword3";

			mockInput.dispatchEvent(new Event("paste"));

			jest.advanceTimersByTime(10);

			expect(chipInput.chips).toEqual(["keyword1", "keyword2", "keyword3"]);
			expect(mockInput.value).toBe("");
		});

		test("should handle paste with whitespace", () => {
			mockInput.value = " keyword1 , keyword2 , keyword3 ";

			mockInput.dispatchEvent(new Event("paste"));

			jest.advanceTimersByTime(10);

			expect(chipInput.chips).toEqual(["keyword1", "keyword2", "keyword3"]);
		});

		test("should not process paste if no commas", () => {
			mockInput.value = "singlekeyword";

			mockInput.dispatchEvent(new Event("paste"));

			jest.advanceTimersByTime(10);

			expect(chipInput.chips).toEqual([]);
		});
	});

	describe("Rendering Chips", () => {
		beforeEach(() => {
			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);
		});

		test("should render chips with correct structure", () => {
			chipInput.chips = ["keyword1", "keyword2"];

			chipInput.renderChips();

			const chips = mockChipContainer.querySelectorAll(".keyword-chip");
			expect(chips.length).toBe(2);

			// Check chip structure
			const firstChip = chips[0];
			expect(firstChip.textContent).toContain("keyword1");
			expect(firstChip.querySelector(".btn-close")).toBeTruthy();
		});

		test("should escape HTML in chip text", () => {
			chipInput.chips = ["<script>alert('xss')</script>"];

			chipInput.renderChips();

			const chip = mockChipContainer.querySelector(".keyword-chip");
			expect(chip.innerHTML).not.toContain("<script>");
		});

		test("should remove existing chips before rendering", () => {
			chipInput.chips = ["keyword1"];
			chipInput.renderChips();

			chipInput.chips = ["keyword2"];
			chipInput.renderChips();

			const chips = mockChipContainer.querySelectorAll(".keyword-chip");
			expect(chips.length).toBe(1);
			expect(chips[0].textContent).toContain("keyword2");
		});

		test("should handle remove button click", () => {
			chipInput.chips = ["keyword1"];
			chipInput.renderChips();

			const chip = mockChipContainer.querySelector(".keyword-chip");
			const removeBtn = chip.querySelector(".btn-close");

			removeBtn.click();

			expect(chipInput.chips).toEqual([]);
		});
	});

	describe("Utility Methods", () => {
		beforeEach(() => {
			chipInput = new window.KeywordChipInput(mockInput, mockHiddenInput);
		});

		test("should get keywords array", () => {
			chipInput.chips = ["keyword1", "keyword2"];

			expect(chipInput.getKeywords()).toEqual(["keyword1", "keyword2"]);
		});

		test("should clear all chips", () => {
			chipInput.chips = ["keyword1", "keyword2"];
			mockInput.value = "text";

			chipInput.clear();

			expect(chipInput.chips).toEqual([]);
			expect(mockInput.value).toBe("");
			expect(mockHiddenInput.value).toBe("");
		});

		test("should escape HTML correctly", () => {
			const escaped = chipInput.escapeHtml("<script>alert('xss')</script>");

			expect(escaped).not.toContain("<script>");
			expect(escaped).toContain("&lt;");
		});
	});
});

describe("initializeKeywordChipInput", () => {
	let mockContainer;
	let mockWrapper;
	let mockInput;
	let mockHiddenInput;

	beforeEach(() => {
		jest.clearAllMocks();

		mockContainer = document.createElement("div");
		mockWrapper = document.createElement("div");
		mockWrapper.className = "keyword-chips-wrapper";
		mockInput = document.createElement("input");
		mockInput.type = "text";
		mockWrapper.appendChild(mockInput);
		mockContainer.appendChild(mockWrapper);

		mockHiddenInput = document.createElement("input");
		mockHiddenInput.type = "hidden";
		mockHiddenInput.id = "keywords-hidden";

		document.body.appendChild(mockContainer);
		document.body.appendChild(mockHiddenInput);

		document.getElementById = jest.fn((id) => {
			if (id === "keywords-hidden") return mockHiddenInput;
			return null;
		});
	});

	afterEach(() => {
		if (mockContainer.parentNode) {
			mockContainer.parentNode.removeChild(mockContainer);
		}
		if (mockHiddenInput.parentNode) {
			mockHiddenInput.parentNode.removeChild(mockHiddenInput);
		}
	});

	test("should initialize KeywordChipInput with default options", () => {
		const result = window.KeywordChipInputInitializer.initialize(mockContainer);

		expect(result).toBeInstanceOf(window.KeywordChipInput);
		expect(window.keywordChipInput).toBe(result);
	});

	test("should return null if container not found", () => {
		const result =
			window.KeywordChipInputInitializer.initialize("#nonexistent");

		expect(result).toBeNull();
	});

	test("should return null if wrapper not found", () => {
		mockContainer.removeChild(mockWrapper);

		const result = window.KeywordChipInputInitializer.initialize(mockContainer);

		expect(result).toBeNull();
	});

	test("should return null if input not found", () => {
		mockWrapper.removeChild(mockInput);

		const result = window.KeywordChipInputInitializer.initialize(mockContainer);

		expect(result).toBeNull();
	});

	test("should return null if hidden input not found", () => {
		document.getElementById.mockReturnValue(null);

		const result = window.KeywordChipInputInitializer.initialize(mockContainer);

		expect(result).toBeNull();
	});

	test("should use custom selectors", () => {
		mockWrapper.className = "custom-wrapper";
		mockInput.className = "custom-input";
		mockHiddenInput.id = "custom-hidden";

		const result = window.KeywordChipInputInitializer.initialize(
			mockContainer,
			{
				wrapperSelector: ".custom-wrapper",
				inputSelector: ".custom-input",
				hiddenInputId: "custom-hidden",
			},
		);

		expect(result).toBeInstanceOf(window.KeywordChipInput);
	});

	test("should allow multiple instances when allowMultiple is true", () => {
		const result1 = window.KeywordChipInputInitializer.initialize(
			mockContainer,
			{
				allowMultiple: true,
			},
		);

		const result2 = window.KeywordChipInputInitializer.initialize(
			mockContainer,
			{
				allowMultiple: true,
			},
		);

		expect(result1).not.toBe(result2);
	});

	test("should reuse existing instance when allowMultiple is false", () => {
		const result1 =
			window.KeywordChipInputInitializer.initialize(mockContainer);

		const result2 =
			window.KeywordChipInputInitializer.initialize(mockContainer);

		expect(result1).toBe(result2);
		expect(window.keywordChipInput).toBe(result1);
	});

	test("should add required classes to input", () => {
		window.KeywordChipInputInitializer.initialize(mockContainer);

		expect(mockInput.classList.contains("keyword-input")).toBe(true);
		expect(mockInput.classList.contains("border-0")).toBe(true);
		expect(mockInput.classList.contains("flex-grow-1")).toBe(true);
	});

	test("should set input placeholder if not set", () => {
		mockInput.placeholder = "";

		window.KeywordChipInputInitializer.initialize(mockContainer);

		expect(mockInput.placeholder).toBe("Type keywords and press comma");
	});

	test("should not override existing placeholder", () => {
		mockInput.placeholder = "Custom placeholder";

		window.KeywordChipInputInitializer.initialize(mockContainer);

		expect(mockInput.placeholder).toBe("Custom placeholder");
	});
});

describe("initializeKeywordChipInputOnCollapseShow", () => {
	let mockCollapse;
	let mockWrapper;
	let mockInput;
	let mockHiddenInput;

	beforeEach(() => {
		jest.clearAllMocks();

		mockCollapse = document.createElement("div");
		mockCollapse.className = "collapse";

		mockWrapper = document.createElement("div");
		mockWrapper.className = "keyword-chips-wrapper";
		mockInput = document.createElement("input");
		mockInput.type = "text";
		mockWrapper.appendChild(mockInput);
		mockCollapse.appendChild(mockWrapper);

		mockHiddenInput = document.createElement("input");
		mockHiddenInput.type = "hidden";
		mockHiddenInput.id = "keywords-hidden";

		document.body.appendChild(mockCollapse);
		document.body.appendChild(mockHiddenInput);

		document.getElementById = jest.fn((id) => {
			if (id === "keywords-hidden") return mockHiddenInput;
			return null;
		});

		// Mock Bootstrap
		window.bootstrap = {
			Collapse: jest.fn(),
		};
	});

	afterEach(() => {
		if (mockCollapse.parentNode) {
			mockCollapse.parentNode.removeChild(mockCollapse);
		}
		if (mockHiddenInput.parentNode) {
			mockHiddenInput.parentNode.removeChild(mockHiddenInput);
		}
	});

	test("should initialize immediately if collapse is already shown", () => {
		mockCollapse.classList.add("show");

		const result =
			window.KeywordChipInputInitializer.initializeOnCollapseShow(mockCollapse);

		expect(result).toBeInstanceOf(window.KeywordChipInput);
	});

	test("should wait for collapse show event if not shown", () => {
		const result =
			window.KeywordChipInputInitializer.initializeOnCollapseShow(mockCollapse);

		expect(result).toBeNull();

		// Simulate collapse show event
		mockCollapse.classList.add("show");
		const event = new Event("shown.bs.collapse");
		mockCollapse.dispatchEvent(event);

		// Should have initialized after event
		expect(window.keywordChipInput).toBeInstanceOf(window.KeywordChipInput);
	});

	test("should return null if bootstrap not available", () => {
		const originalBootstrap = window.bootstrap;
		window.bootstrap = undefined;

		const result =
			window.KeywordChipInputInitializer.initializeOnCollapseShow(mockCollapse);

		expect(result).toBeNull();

		window.bootstrap = originalBootstrap;
	});
});

describe("autoInitializeKeywordChipInput", () => {
	let mockWrapper;
	let mockInput;
	let mockHiddenInput;

	beforeEach(() => {
		jest.clearAllMocks();

		mockWrapper = document.createElement("div");
		mockWrapper.className = "keyword-chips-wrapper";
		mockInput = document.createElement("input");
		mockInput.type = "text";
		mockWrapper.appendChild(mockInput);

		mockHiddenInput = document.createElement("input");
		mockHiddenInput.type = "hidden";
		mockHiddenInput.id = "keywords-hidden";

		document.getElementById = jest.fn((id) => {
			if (id === "keywords-hidden") return mockHiddenInput;
			return null;
		});
	});

	afterEach(() => {
		if (mockWrapper.parentNode) {
			mockWrapper.parentNode.removeChild(mockWrapper);
		}
		if (mockHiddenInput.parentNode) {
			mockHiddenInput.parentNode.removeChild(mockHiddenInput);
		}
	});

	test("should initialize on DOMContentLoaded if DOM is loading", () => {
		Object.defineProperty(document, "readyState", {
			value: "loading",
			writable: true,
			configurable: true,
		});

		document.body.appendChild(mockWrapper);

		window.KeywordChipInputInitializer.autoInitialize();

		// Simulate DOMContentLoaded
		const event = new Event("DOMContentLoaded");
		document.dispatchEvent(event);

		expect(window.keywordChipInput).toBeInstanceOf(window.KeywordChipInput);
	});

	test("should initialize immediately if DOM is already loaded", () => {
		Object.defineProperty(document, "readyState", {
			value: "complete",
			writable: true,
			configurable: true,
		});

		document.body.appendChild(mockWrapper);

		window.KeywordChipInputInitializer.autoInitialize();

		expect(window.keywordChipInput).toBeInstanceOf(window.KeywordChipInput);
	});
});

describe("KeywordAutocomplete", () => {
	let autocomplete;
	let mockInput;
	let mockApiUrl;

	beforeEach(() => {
		jest.clearAllMocks();
		jest.useFakeTimers();

		mockInput = document.createElement("input");
		mockInput.type = "text";
		document.body.appendChild(mockInput);

		mockApiUrl = "/users/api/keyword-autocomplete/";

		// Mock fetch
		global.fetch = jest.fn().mockResolvedValue({
			json: jest.fn().mockResolvedValue({
				suggestions: ["keyword1", "keyword2", "keyword3"],
			}),
		});
	});

	afterEach(() => {
		jest.useRealTimers();
		if (mockInput.parentNode) {
			mockInput.parentNode.removeChild(mockInput);
		}
		if (autocomplete?.suggestionsContainer?.parentNode) {
			autocomplete.suggestionsContainer.parentNode.removeChild(
				autocomplete.suggestionsContainer,
			);
		}
	});

	test("should initialize with input and API URL", () => {
		autocomplete = new window.KeywordAutocomplete(mockInput, mockApiUrl);

		expect(autocomplete.input).toBe(mockInput);
		expect(autocomplete.apiUrl).toBe(mockApiUrl);
		expect(autocomplete.minChars).toBe(1);
		expect(autocomplete.debounceMs).toBe(300);
	});

	test("should create suggestions container", () => {
		autocomplete = new window.KeywordAutocomplete(mockInput, mockApiUrl);

		expect(autocomplete.suggestionsContainer).toBeTruthy();
		expect(autocomplete.suggestionsContainer.className).toBe(
			"keyword-autocomplete-suggestions",
		);
	});

	test("should fetch suggestions on input", async () => {
		autocomplete = new window.KeywordAutocomplete(mockInput, mockApiUrl);
		mockInput.value = "key";

		mockInput.dispatchEvent(new Event("input"));

		jest.advanceTimersByTime(300);

		expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("q=key"));
	});

	test("should not fetch if input is too short", () => {
		autocomplete = new window.KeywordAutocomplete(mockInput, mockApiUrl);
		mockInput.value = "";

		mockInput.dispatchEvent(new Event("input"));

		jest.advanceTimersByTime(300);

		expect(global.fetch).not.toHaveBeenCalled();
	});

	test("should get current word correctly", () => {
		autocomplete = new window.KeywordAutocomplete(mockInput, mockApiUrl);
		mockInput.value = "keyword1,keyword2,test";
		mockInput.selectionStart = mockInput.value.length;

		const currentWord = autocomplete.getCurrentWord();

		expect(currentWord).toBe("test");
	});

	test("should show suggestions", () => {
		autocomplete = new window.KeywordAutocomplete(mockInput, mockApiUrl);
		const suggestions = ["keyword1", "keyword2"];

		autocomplete.showSuggestions(suggestions);

		const items = autocomplete.suggestionsContainer.querySelectorAll(
			".keyword-autocomplete-item",
		);
		expect(items.length).toBe(2);
		expect(autocomplete.suggestionsContainer.style.display).toBe("block");
	});

	test("should select suggestion on click", () => {
		autocomplete = new window.KeywordAutocomplete(mockInput, mockApiUrl);
		mockInput.value = "key";
		mockInput.selectionStart = mockInput.value.length;

		autocomplete.showSuggestions(["keyword1"]);

		const item = autocomplete.suggestionsContainer.querySelector(
			".keyword-autocomplete-item",
		);
		item.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

		expect(mockInput.value).toContain("keyword1");
	});

	test("should handle arrow key navigation", () => {
		autocomplete = new window.KeywordAutocomplete(mockInput, mockApiUrl);
		autocomplete.showSuggestions(["keyword1", "keyword2"]);

		const arrowDown = new KeyboardEvent("keydown", { key: "ArrowDown" });
		mockInput.dispatchEvent(arrowDown);

		expect(autocomplete.currentFocus).toBe(0);
	});

	test("should close suggestions on Escape", () => {
		autocomplete = new window.KeywordAutocomplete(mockInput, mockApiUrl);
		autocomplete.showSuggestions(["keyword1"]);

		const escape = new KeyboardEvent("keydown", { key: "Escape" });
		mockInput.dispatchEvent(escape);

		expect(autocomplete.suggestionsContainer.style.display).toBe("none");
	});
});
