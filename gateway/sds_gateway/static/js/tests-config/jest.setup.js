// Jest setup file for global test configuration

const { TextDecoder, TextEncoder } = require("node:util");
if (typeof globalThis.TextEncoder === "undefined") {
	globalThis.TextEncoder = TextEncoder;
}
if (typeof globalThis.TextDecoder === "undefined") {
	globalThis.TextDecoder = TextDecoder;
}

// Mock DOM environment
const mockDOM = {
	createElement: (tag) => ({
		tagName: tag,
		textContent: "",
		innerHTML: "",
		classList: {
			add: jest.fn(),
			remove: jest.fn(),
			contains: jest.fn(() => false),
			toggle: jest.fn(),
			addEventListener: jest.fn(),
			removeEventListener: jest.fn(),
		},
		querySelector: jest.fn(() => null),
		querySelectorAll: jest.fn(() => []),
		appendChild: jest.fn(),
		removeChild: jest.fn(),
		setAttribute: jest.fn(),
		getAttribute: jest.fn(),
		addEventListener: jest.fn(),
		removeEventListener: jest.fn(),
		dispatchEvent: jest.fn(),
	}),
	querySelector: jest.fn(() => null),
	querySelectorAll: jest.fn(() => []),
	getElementById: jest.fn(() => null),
	head: { appendChild: jest.fn() },
	createTextNode: jest.fn((text) => ({ textContent: text })),
	addEventListener: jest.fn(),
	removeEventListener: jest.fn(),
};

// Mock window object
const mockWindow = {
	location: {
		href: "http://localhost:8000",
		origin: "http://localhost:8000",
		pathname: "/",
		search: "",
		hash: "",
	},
	history: {
		pushState: jest.fn(),
		replaceState: jest.fn(),
		back: jest.fn(),
		forward: jest.fn(),
	},
	localStorage: {
		getItem: jest.fn(),
		setItem: jest.fn(),
		removeItem: jest.fn(),
		clear: jest.fn(),
	},
	sessionStorage: {
		getItem: jest.fn(),
		setItem: jest.fn(),
		removeItem: jest.fn(),
		clear: jest.fn(),
	},
	fetch: jest.fn(),
	alert: jest.fn(),
	confirm: jest.fn(),
	prompt: jest.fn(),
	setTimeout: jest.fn((fn) => fn()),
	clearTimeout: jest.fn(),
	setInterval: jest.fn(),
	clearInterval: jest.fn(),
};

// Make location.href settable without triggering navigation
Object.defineProperty(mockWindow.location, "href", {
	get() {
		return this._href || "http://localhost:8000";
	},
	set(value) {
		this._href = value;
		// Don't actually navigate - just store the value
		// Tests can check this value if needed
	},
	configurable: true,
});

// Set up global mocks
global.document = mockDOM;
global.window = mockWindow;

require("../search/ConfiguredSearchElements.js");
require("../actions/quickAdd/quickAddApi.js");
require("../actions/download/captureDownloadSlider.js");
require("../dataset/datasetFormSnapshot.js");
// Classes referenced by `extends` / static calls in browser bundles
const { BaseManager } = require("../core/BaseManager.js");
global.BaseManager = BaseManager;
const { ModalManager } = require("../core/ModalManager.js");
global.ModalManager = ModalManager;
global.window.ModalManager = ModalManager;

require("../upload/UploadUtils.js");
require("../upload/CaptureTypeSelector.js");
require("../upload/CaptureUploadController.js");
require("../upload/FileUploadHandler.js");
require("../upload/FilesBrowserManager.js");
const { UserInputController } = require("../core/UserInputController.js");
global.UserInputController = UserInputController;

// Mock console methods to reduce noise in tests
global.console = {
	...console,
	// Uncomment to suppress console.log in tests
	// log: jest.fn(),
	// debug: jest.fn(),
	// info: jest.fn(),
	warn: jest.fn(),
	error: jest.fn(),
};

// Mock fetch globally
global.fetch = jest.fn();

// Mock ResizeObserver
global.ResizeObserver = jest.fn().mockImplementation(() => ({
	observe: jest.fn(),
	unobserve: jest.fn(),
	disconnect: jest.fn(),
}));

// Mock IntersectionObserver
global.IntersectionObserver = jest.fn().mockImplementation(() => ({
	observe: jest.fn(),
	unobserve: jest.fn(),
	disconnect: jest.fn(),
}));

// Mock matchMedia
Object.defineProperty(window, "matchMedia", {
	writable: true,
	value: jest.fn().mockImplementation((query) => ({
		matches: false,
		media: query,
		onchange: null,
		addListener: jest.fn(),
		removeListener: jest.fn(),
		addEventListener: jest.fn(),
		removeEventListener: jest.fn(),
		dispatchEvent: jest.fn(),
	})),
});

// Mock URL and URLSearchParams
global.URL = class URL {
	constructor(url, base) {
		// Handle base URL for relative URLs
		// e.g. URL("api/test", "http://localhost:8000") -> "http://localhost:8000/api/test"
		if (base) {
			this.href = base + (url.startsWith("/") ? url : `/${url}`);
		} else {
			this.href = url;
		}

		const urlMatch = this.href.match(
			/^(https?:\/\/[^\/]+)?(\/[^?#]*)?(\?[^#]*)?(#.*)?$/,
		);
		this.pathname = urlMatch?.[2] ? urlMatch[2] : "/";
		this.search = urlMatch?.[3] ? urlMatch[3] : "";
		this.hash = urlMatch?.[4] ? urlMatch[4] : "";

		this.origin = base || this.href.match(/^(https?:\/\/[^\/]+)/)?.[1] || "";
		this.searchParams = new global.URLSearchParams(this.search.substring(1));
	}

	toString() {
		// Build href from current state including searchParams
		const searchString = this.searchParams.toString();
		const search = searchString ? `?${searchString}` : "";
		return `${this.origin}${this.pathname}${search}${this.hash}`;
	}
};

global.URLSearchParams = class URLSearchParams {
	constructor(search) {
		this.params = new Map();
		if (search) {
			for (const param of search.split("&")) {
				const [key, value] = param.split("=");
				this.params.set(key, value);
			}
		}
	}

	get(name) {
		return this.params.get(name);
	}

	set(name, value) {
		this.params.set(name, value);
	}

	has(name) {
		return this.params.has(name);
	}

	delete(name) {
		this.params.delete(name);
	}

	append(name, value) {
		const existing = this.params.get(name);
		if (existing) {
			this.params.set(name, `${existing},${value}`);
		} else {
			this.params.set(name, value);
		}
	}

	toString() {
		return Array.from(this.params.entries())
			.map(
				([key, value]) =>
					`${encodeURIComponent(key)}=${encodeURIComponent(value)}`,
			)
			.join("&");
	}
};

// Mock Bootstrap
global.bootstrap = {
	Modal: jest.fn().mockImplementation((element) => ({
		show: jest.fn(),
		hide: jest.fn(),
		element: element,
	})),
	Toast: jest.fn().mockImplementation((element) => ({
		show: jest.fn(),
		hide: jest.fn(),
		element: element,
	})),
};

// Mock window.bootstrap (some code uses window.bootstrap)
global.window.bootstrap = global.bootstrap;

// Mock APIClient as a real class (production uses `new window.APIClient()`; jest.fn is not a reliable constructor)
global.window.APIClient = class MockAPIClient {
	get() {
		return Promise.resolve({ success: true });
	}
	post() {
		return Promise.resolve({ html: "<div>Mock HTML</div>" });
	}
	put() {
		return Promise.resolve({ success: true });
	}
	patch() {
		return Promise.resolve({ success: true });
	}
	delete() {
		return Promise.resolve({ success: true });
	}
	request() {
		return Promise.resolve({ success: true });
	}
	getCSRFToken() {
		return "mock-csrf-token";
	}
	getCookie() {
		return null;
	}
};

// Mock DOMUtils (shared shape; tests may override fields)
const { createMockDOMUtils } = require("./testHelpers.js");
global.window.DOMUtils = createMockDOMUtils();

global.window.showMessage = jest.fn().mockResolvedValue(true);
global.window.showToast = jest.fn();
global.window.hideToast = jest.fn();

const { AuthorsManager } = require("../dataset/AuthorsManager.js");
const { DatasetAuthorsUI } = require("../dataset/DatasetAuthorsUI.js");
const { DatasetPendingChanges } = require("../dataset/DatasetPendingChanges.js");
const { UserSearchDropdown } = require("../share/UserSearchDropdown.js");
const { UploadUtils } = require("../upload/UploadUtils.js");
global.window.AuthorsManager = AuthorsManager;
global.window.DatasetAuthorsUI = DatasetAuthorsUI;
global.window.DatasetPendingChanges = DatasetPendingChanges;
global.window.UserSearchDropdown = UserSearchDropdown;
global.window.UploadUtils = UploadUtils;
global.window.ChunkUploadPipeline = UploadUtils;
