// Jest setup file for global test configuration

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

// Set up global mocks
global.document = mockDOM;
global.window = mockWindow;

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

		// Simple parsing (original approach)
		this.pathname = this.href.split("?")[0];
		this.search = this.href.includes("?") ? `?${this.href.split("?")[1]}` : "";
		this.hash = this.href.includes("#") ? `#${this.href.split("#")[1]}` : "";

		// Add missing properties
		this.origin = base || this.href.match(/^(https?:\/\/[^\/]+)/)?.[1] || "";
		this.searchParams = new global.URLSearchParams(this.search.substring(1));
	}

	toString() {
		return this.href;
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
			.map(([key, value]) => `${key}=${value}`)
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

// Mock APIClient for template rendering
global.window.APIClient = {
	get: jest.fn().mockResolvedValue({ success: true }),
	post: jest.fn().mockResolvedValue({ html: "<div>Mock HTML</div>" }),
	put: jest.fn().mockResolvedValue({ success: true }),
	patch: jest.fn().mockResolvedValue({ success: true }),
	delete: jest.fn().mockResolvedValue({ success: true }),
	request: jest.fn().mockResolvedValue({ success: true }),
	getCSRFToken: jest.fn().mockReturnValue("mock-csrf-token"),
	getCookie: jest.fn().mockReturnValue(null),
};

// Mock DOMUtils
global.window.DOMUtils = {
	show: jest.fn(),
	hide: jest.fn(),
	showAlert: jest.fn(),
	renderError: jest.fn().mockResolvedValue(true),
	renderLoading: jest.fn().mockResolvedValue(true),
	renderContent: jest.fn().mockResolvedValue(true),
	renderTable: jest.fn().mockResolvedValue(true),
	renderSelectOptions: jest.fn().mockResolvedValue(true),
	renderPagination: jest.fn().mockResolvedValue(true),
	renderDropdown: jest.fn().mockResolvedValue("<div>Mock Dropdown</div>"),
};

// Mock global showAlert function
global.window.showAlert = jest.fn();
global.window.showToast = jest.fn();
global.window.hideToast = jest.fn();
