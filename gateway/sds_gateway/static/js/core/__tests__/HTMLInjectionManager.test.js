/**
 * Jest tests for HTMLInjectionManager
 * Tests safe DOM manipulation with XSS protection
 */

// Import the HTMLInjectionManager class
import { HTMLInjectionManager } from "../HTMLInjectionManager.js";

describe("HTMLInjectionManager", () => {
	let htmlManager;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Create HTMLInjectionManager instance
		htmlManager = new HTMLInjectionManager();
	});

	describe("HTML Escaping", () => {
		test("should escape HTML characters", () => {
			const result = htmlManager.escapeHtml('<script>alert("xss")</script>');

			expect(result).toBe('&lt;script&gt;alert("xss")&lt;/script&gt;');
		});

		test("should handle empty string", () => {
			const result = htmlManager.escapeHtml("");

			expect(result).toBe("");
		});

		test("should handle null and undefined", () => {
			expect(htmlManager.escapeHtml(null)).toBe("");
			expect(htmlManager.escapeHtml(undefined)).toBe("");
		});

		test("should escape special characters", () => {
			const result = htmlManager.escapeHtml('Test & "quotes" and <tags>');

			expect(result).toBe('Test &amp; "quotes" and &lt;tags&gt;');
		});

		test("should handle already escaped content", () => {
			const result = htmlManager.escapeHtml("&lt;div&gt;content&lt;/div&gt;");

			expect(result).toBe("&amp;lt;div&amp;gt;content&amp;lt;/div&amp;gt;");
		});
	});

	describe("HTML Injection", () => {
		test("should inject HTML with innerHTML method", () => {
			const container = { innerHTML: "" };
			const htmlString = "<div>Test content</div>";

			htmlManager.injectHTML(container, htmlString, { method: "innerHTML" });

			expect(container.innerHTML).toBe("&lt;div&gt;Test content&lt;/div&gt;");
		});

		test("should inject HTML with append method", () => {
			const container = { insertAdjacentHTML: jest.fn() };
			const htmlString = "<div>Test content</div>";

			htmlManager.injectHTML(container, htmlString, { method: "append" });

			expect(container.insertAdjacentHTML).toHaveBeenCalledWith(
				"beforeend",
				"&lt;div&gt;Test content&lt;/div&gt;",
			);
		});

		test("should inject HTML with prepend method", () => {
			const container = { insertAdjacentHTML: jest.fn() };
			const htmlString = "<div>Test content</div>";

			htmlManager.injectHTML(container, htmlString, { method: "prepend" });

			expect(container.insertAdjacentHTML).toHaveBeenCalledWith(
				"afterbegin",
				"&lt;div&gt;Test content&lt;/div&gt;",
			);
		});

		test("should inject unescaped HTML when escape is false", () => {
			const container = { innerHTML: "" };
			const htmlString = "<div>Test content</div>";

			htmlManager.injectHTML(container, htmlString, { escape: false });

			expect(container.innerHTML).toBe("<div>Test content</div>");
		});

		test("should use container selector string", () => {
			const mockElement = { innerHTML: "" };
			document.querySelector = jest.fn(() => mockElement);

			htmlManager.injectHTML("#test-container", "<div>Test</div>");

			expect(document.querySelector).toHaveBeenCalledWith("#test-container");
			expect(mockElement.innerHTML).toBe("&lt;div&gt;Test&lt;/div&gt;");
		});

		test("should handle missing container element", () => {
			document.querySelector = jest.fn(() => null);

			expect(() => {
				htmlManager.injectHTML("#missing", "<div>Test</div>");
			}).not.toThrow();
		});

		test("should handle unknown injection method", () => {
			const container = { innerHTML: "" };
			const htmlString = "<div>Test content</div>";

			htmlManager.injectHTML(container, htmlString, { method: "unknown" });

			expect(container.innerHTML).toBe("");
		});
	});

	describe("Table Row Creation", () => {
		test("should create table row with safe data", () => {
			const data = { name: "Test", value: "123" };
			const template = "<tr><td>{{name}}</td><td>{{value}}</td></tr>";

			const result = htmlManager.createTableRow(data, template);

			expect(result).toBe("<tr><td>Test</td><td>123</td></tr>");
		});

		test("should escape HTML in data", () => {
			const data = { name: '<script>alert("xss")</script>', value: "123" };
			const template = "<tr><td>{{name}}</td><td>{{value}}</td></tr>";

			const result = htmlManager.createTableRow(data, template);

			expect(result).toBe(
				'<tr><td>&lt;script&gt;alert("xss")&lt;/script&gt;</td><td>123</td></tr>',
			);
		});

		test("should handle null and undefined values", () => {
			const data = { name: null, value: undefined };
			const template = "<tr><td>{{name}}</td><td>{{value}}</td></tr>";

			const result = htmlManager.createTableRow(data, template);

			expect(result).toBe("<tr><td>-</td><td>-</td></tr>");
		});

		test("should format dates correctly", () => {
			const date = new Date("2023-01-01T12:00:00Z");
			const data = { date: date };
			const template = "<tr><td>{{date}}</td></tr>";

			const result = htmlManager.createTableRow(data, template);

			expect(result).toContain("2023");
		});

		test("should handle multiple occurrences of same placeholder", () => {
			const data = { name: "Test" };
			const template = "<tr><td>{{name}}</td><td>{{name}}</td></tr>";

			const result = htmlManager.createTableRow(data, template);

			expect(result).toBe("<tr><td>Test</td><td>Test</td></tr>");
		});
	});

	describe("Modal Content Creation", () => {
		test("should create modal content with safe data", () => {
			const data = { title: "Test Modal", content: "Modal content" };
			const template =
				'<div class="modal"><h3>{{title}}</h3><p>{{content}}</p></div>';

			const result = htmlManager.createModalContent(data, template);

			expect(result).toBe(
				'<div class="modal"><h3>Test Modal</h3><p>Modal content</p></div>',
			);
		});

		test("should escape HTML in modal content", () => {
			const data = {
				title: '<script>alert("xss")</script>',
				content: "Safe content",
			};
			const template =
				'<div class="modal"><h3>{{title}}</h3><p>{{content}}</p></div>';

			const result = htmlManager.createModalContent(data, template);

			expect(result).toBe(
				'<div class="modal"><h3>&lt;script&gt;alert("xss")&lt;/script&gt;</h3><p>Safe content</p></div>',
			);
		});
	});

	describe("Loading Spinner Creation", () => {
		test("should create loading spinner with text", () => {
			const result = htmlManager.createLoadingSpinner("Loading...");

			expect(result).toContain("Loading...");
			expect(result).toContain("spinner");
		});

		test("should create loading spinner without text", () => {
			const result = htmlManager.createLoadingSpinner();

			expect(result).toContain("spinner");
		});
	});

	describe("Badge Creation", () => {
		test("should create badge with text", () => {
			const result = htmlManager.createBadge("Test Badge");

			expect(result).toContain("Test Badge");
			expect(result).toContain("badge");
		});

		test("should create badge with different types", () => {
			const result = htmlManager.createBadge("Success", "success");

			expect(result).toContain("Success");
			expect(result).toContain("bg-success");
		});
	});

	describe("Button Creation", () => {
		test("should create button with text", () => {
			const result = htmlManager.createButton("Click Me");

			expect(result).toContain("Click Me");
			expect(result).toContain("btn");
		});

		test("should create button with different types", () => {
			const result = htmlManager.createButton("Danger", { type: "danger" });

			expect(result).toContain("Danger");
			expect(result).toContain("btn-primary");
		});
	});

	describe("Notification Creation", () => {
		test("should create notification with message", () => {
			const result = htmlManager.createNotification("Test message");

			expect(result).toContain("Test message");
			expect(result).toContain("alert");
		});

		test("should create notification with different types", () => {
			const result = htmlManager.createNotification("Error message", "error");

			expect(result).toContain("Error message");
			expect(result).toContain("alert-error");
		});
	});

	describe("Error Handling", () => {
		test("should handle missing template placeholders gracefully", () => {
			const data = { name: "Test" };
			const template = "<div>{{missing}}</div>";

			const result = htmlManager.createTableRow(data, template);

			expect(result).toBe("<div>{{missing}}</div>");
		});

		test("should handle empty data object", () => {
			const data = {};
			const template = "<div>{{name}}</div>";

			const result = htmlManager.createTableRow(data, template);

			expect(result).toBe("<div>{{name}}</div>");
		});

		test("should handle null template", () => {
			const data = { name: "Test" };

			expect(() => {
				htmlManager.createTableRow(data, null);
			}).toThrow();
		});
	});
});
