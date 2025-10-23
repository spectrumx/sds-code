/**
 * Jest tests for DOMUtils
 * Tests DOM manipulation utilities with API-based template rendering
 */

import { DOMUtils } from "../DOMUtils.js";

describe("DOMUtils", () => {
	let domUtils;
	let mockAPIClient;
	let mockContainer;
	let mockToastContainer;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Create mock elements
		mockContainer = {
			id: "test-container",
			innerHTML: "",
			classList: {
				add: jest.fn(),
				remove: jest.fn(),
				contains: jest.fn(() => false),
			},
			querySelector: jest.fn(),
			querySelectorAll: jest.fn(() => []),
		};

		mockToastContainer = {
			id: "toast-container",
			appendChild: jest.fn(),
		};

		// Mock APIClient
		mockAPIClient = {
			post: jest.fn().mockResolvedValue({ html: "<div>Test HTML</div>" }),
			get: jest.fn(),
		};

		// Set up global mocks
		global.window.APIClient = mockAPIClient;
		global.document.getElementById = jest.fn((id) => {
			if (id === "toast-container") return mockToastContainer;
			if (id === "test-container") return mockContainer;
			return null;
		});
		global.document.querySelector = jest.fn((selector) => {
			if (selector === "#test-container") return mockContainer;
			return null;
		});
		global.document.createElement = jest.fn((tag) => {
			if (tag === "div") {
				return {
					tagName: "div",
					id: "",
					className: "",
					textContent: "",
					innerHTML: "",
					classList: {
						add: jest.fn(),
						remove: jest.fn(),
					},
					setAttribute: jest.fn(),
					getAttribute: jest.fn(),
					appendChild: jest.fn(),
					addEventListener: jest.fn(),
				};
			}
			if (tag === "button") {
				return {
					tagName: "button",
					type: "",
					className: "",
					setAttribute: jest.fn(),
					getAttribute: jest.fn(),
				};
			}
			return null;
		});

		// Mock Bootstrap Toast
		global.bootstrap = {
			Toast: jest.fn().mockImplementation((element) => ({
				show: jest.fn(),
				hide: jest.fn(),
				element: element,
			})),
		};

		// Create DOMUtils instance
		domUtils = new DOMUtils();
	});

	describe("Basic DOM Manipulation", () => {
		describe("show()", () => {
			test("should show element by removing display-none and adding display-block", () => {
				domUtils.show(mockContainer);

				expect(mockContainer.classList.remove).toHaveBeenCalledWith(
					"display-none",
					"d-none",
				);
				expect(mockContainer.classList.add).toHaveBeenCalledWith(
					"display-block",
				);
			});

			test("should show element with custom display class", () => {
				domUtils.show(mockContainer, "d-flex");

				expect(mockContainer.classList.remove).toHaveBeenCalledWith(
					"display-none",
					"d-none",
				);
				expect(mockContainer.classList.add).toHaveBeenCalledWith("d-flex");
			});

			test("should work with selector string", () => {
				domUtils.show("#test-container");

				expect(document.querySelector).toHaveBeenCalledWith("#test-container");
				expect(mockContainer.classList.add).toHaveBeenCalledWith(
					"display-block",
				);
			});

			test("should handle missing element gracefully", () => {
				console.warn = jest.fn();

				domUtils.show("#nonexistent");

				expect(console.warn).toHaveBeenCalledWith(
					"Element not found for show():",
					"#nonexistent",
				);
			});
		});

		describe("hide()", () => {
			test("should hide element by removing display-block and adding display-none", () => {
				domUtils.hide(mockContainer);

				expect(mockContainer.classList.remove).toHaveBeenCalledWith(
					"display-block",
				);
				expect(mockContainer.classList.add).toHaveBeenCalledWith(
					"display-none",
				);
			});

			test("should hide element with custom display class", () => {
				domUtils.hide(mockContainer, "d-flex");

				expect(mockContainer.classList.remove).toHaveBeenCalledWith("d-flex");
				expect(mockContainer.classList.add).toHaveBeenCalledWith(
					"display-none",
				);
			});

			test("should work with selector string", () => {
				domUtils.hide("#test-container");

				expect(document.querySelector).toHaveBeenCalledWith("#test-container");
				expect(mockContainer.classList.add).toHaveBeenCalledWith(
					"display-none",
				);
			});

			test("should handle missing element gracefully", () => {
				console.warn = jest.fn();

				domUtils.hide("#nonexistent");

				expect(console.warn).toHaveBeenCalledWith(
					"Element not found for hide():",
					"#nonexistent",
				);
			});
		});
	});

	describe("showAlert()", () => {
		test("should show success toast notification", () => {
			domUtils.showAlert("Success message", "success");

			expect(mockToastContainer.appendChild).toHaveBeenCalled();
			expect(global.bootstrap.Toast).toHaveBeenCalled();
		});

		test("should show error toast notification", () => {
			domUtils.showAlert("Error message", "error");

			expect(mockToastContainer.appendChild).toHaveBeenCalled();
			expect(global.bootstrap.Toast).toHaveBeenCalled();
		});

		test("should show warning toast notification", () => {
			domUtils.showAlert("Warning message", "warning");

			expect(mockToastContainer.appendChild).toHaveBeenCalled();
			expect(global.bootstrap.Toast).toHaveBeenCalled();
		});

		test("should show info toast notification", () => {
			domUtils.showAlert("Info message", "info");

			expect(mockToastContainer.appendChild).toHaveBeenCalled();
			expect(global.bootstrap.Toast).toHaveBeenCalled();
		});

		test("should handle missing toast container gracefully", () => {
			document.getElementById = jest.fn(() => null);
			console.warn = jest.fn();

			domUtils.showAlert("Test message");

			expect(console.warn).toHaveBeenCalledWith("Toast container not found");
		});

		test("should handle missing Bootstrap gracefully", () => {
			global.bootstrap = null;
			console.error = jest.fn();

			domUtils.showAlert("Test message");

			expect(console.error).toHaveBeenCalledWith("Bootstrap not available");
		});
	});

	describe("API-Based Rendering Methods", () => {
		describe("renderError()", () => {
			test("should render error using Django template", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<span class="text-danger">Error message</span>',
				});

				const result = await domUtils.renderError(
					mockContainer,
					"Error message",
				);

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/error.html",
					context: {
						message: "Error message",
						format: "inline",
					},
				});
				expect(mockContainer.innerHTML).toBe(
					'<span class="text-danger">Error message</span>',
				);
				expect(result).toBe(true);
			});

			test("should render error with table format", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<tr><td colspan="5" class="text-danger">Error</td></tr>',
				});

				await domUtils.renderError(mockContainer, "Error message", {
					format: "table",
					colspan: 5,
				});

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/error.html",
					context: {
						message: "Error message",
						format: "table",
						colspan: 5,
					},
				});
			});

			test("should render error with alert format", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<div class="alert alert-danger">Error message</div>',
				});

				await domUtils.renderError(mockContainer, "Error message", {
					format: "alert",
				});

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/error.html",
					context: {
						message: "Error message",
						format: "alert",
					},
				});
			});

			test("should fallback to inline HTML on API error", async () => {
				mockAPIClient.post.mockRejectedValue(new Error("API error"));
				console.error = jest.fn();

				const result = await domUtils.renderError(
					mockContainer,
					"Error message",
				);

				expect(mockContainer.innerHTML).toBe(
					'<span class="text-danger">Error message</span>',
				);
				expect(result).toBe(false);
			});

			test("should fallback to table HTML on API error with table format", async () => {
				mockAPIClient.post.mockRejectedValue(new Error("API error"));

				await domUtils.renderError(mockContainer, "Error message", {
					format: "table",
					colspan: 5,
				});

				expect(mockContainer.innerHTML).toBe(
					'<tr><td colspan="5" class="text-center text-danger">Error message</td></tr>',
				);
			});

			test("should handle missing container gracefully", async () => {
				console.warn = jest.fn();

				const result = await domUtils.renderError("#nonexistent", "Error");

				expect(console.warn).toHaveBeenCalledWith(
					"Container not found for renderError:",
					"#nonexistent",
				);
				expect(result).toBe(false);
			});

			test("should work with selector string", async () => {
				await domUtils.renderError("#test-container", "Error message");

				expect(document.querySelector).toHaveBeenCalledWith("#test-container");
				expect(mockAPIClient.post).toHaveBeenCalled();
			});
		});

		describe("renderLoading()", () => {
			test("should render loading spinner using Django template", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<span class="spinner-border"></span> Loading...',
				});

				const result = await domUtils.renderLoading(mockContainer);

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/loading.html",
					context: {
						text: "Loading...",
						format: "spinner",
						size: "md",
						color: "primary",
					},
				});
				expect(mockContainer.innerHTML).toBe(
					'<span class="spinner-border"></span> Loading...',
				);
				expect(result).toBe(true);
			});

			test("should render loading with custom text", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<span class="spinner-border"></span> Please wait...',
				});

				await domUtils.renderLoading(mockContainer, "Please wait...");

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/loading.html",
					context: {
						text: "Please wait...",
						format: "spinner",
						size: "md",
						color: "primary",
					},
				});
			});

			test("should render loading with custom options", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<span class="spinner-border spinner-border-sm"></span>',
				});

				await domUtils.renderLoading(mockContainer, "Loading...", {
					size: "sm",
					color: "secondary",
				});

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/loading.html",
					context: {
						text: "Loading...",
						format: "spinner",
						size: "sm",
						color: "secondary",
					},
				});
			});

			test("should fallback to inline HTML on API error", async () => {
				mockAPIClient.post.mockRejectedValue(new Error("API error"));
				console.error = jest.fn();

				const result = await domUtils.renderLoading(
					mockContainer,
					"Loading...",
				);

				expect(mockContainer.innerHTML).toContain("spinner-border");
				expect(mockContainer.innerHTML).toContain("Loading...");
				expect(result).toBe(false);
			});

			test("should handle missing container gracefully", async () => {
				console.warn = jest.fn();

				const result = await domUtils.renderLoading("#nonexistent");

				expect(console.warn).toHaveBeenCalledWith(
					"Container not found for renderLoading:",
					"#nonexistent",
				);
				expect(result).toBe(false);
			});
		});

		describe("renderContent()", () => {
			test("should render icon and text using Django template", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<i class="bi bi-check"></i> Success',
				});

				const result = await domUtils.renderContent(mockContainer, {
					icon: "check",
					text: "Success",
				});

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/content.html",
					context: {
						icon: "check",
						text: "Success",
					},
				});
				expect(mockContainer.innerHTML).toBe(
					'<i class="bi bi-check"></i> Success',
				);
				expect(result).toBe(true);
			});

			test("should render content with color", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<i class="bi bi-exclamation-circle text-warning"></i> Warning',
				});

				await domUtils.renderContent(mockContainer, {
					icon: "exclamation-circle",
					text: "Warning",
					color: "warning",
				});

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/content.html",
					context: {
						icon: "exclamation-circle",
						text: "Warning",
						color: "warning",
					},
				});
			});

			test("should fallback to inline HTML on API error", async () => {
				mockAPIClient.post.mockRejectedValue(new Error("API error"));
				console.error = jest.fn();

				const result = await domUtils.renderContent(mockContainer, {
					icon: "check",
					text: "Success",
				});

				expect(mockContainer.innerHTML).toContain("bi-check");
				expect(mockContainer.innerHTML).toContain("Success");
				expect(result).toBe(false);
			});

			test("should handle missing container gracefully", async () => {
				console.warn = jest.fn();

				const result = await domUtils.renderContent("#nonexistent", {});

				expect(console.warn).toHaveBeenCalledWith(
					"Container not found for renderContent:",
					"#nonexistent",
				);
				expect(result).toBe(false);
			});
		});

		describe("renderTable()", () => {
			test("should render table rows using Django template", async () => {
				const rows = [
					{ cells: [{ content: "Cell 1" }, { content: "Cell 2" }] },
					{ cells: [{ content: "Cell 3" }, { content: "Cell 4" }] },
				];

				mockAPIClient.post.mockResolvedValue({
					html: "<tr><td>Cell 1</td><td>Cell 2</td></tr><tr><td>Cell 3</td><td>Cell 4</td></tr>",
				});

				const result = await domUtils.renderTable(mockContainer, rows);

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/table_rows.html",
					context: {
						rows: rows,
						empty_message: "No items found",
						empty_colspan: 5,
					},
				});
				expect(result).toBe(true);
			});

			test("should render table with empty message", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<tr><td colspan="3" class="text-center">No data</td></tr>',
				});

				await domUtils.renderTable(mockContainer, [], {
					empty_message: "No data",
					colspan: 3,
				});

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/table_rows.html",
					context: {
						rows: [],
						empty_message: "No data",
						empty_colspan: 3,
						colspan: 3,
					},
				});
			});

			test("should fallback to empty message on API error", async () => {
				mockAPIClient.post.mockRejectedValue(new Error("API error"));
				console.error = jest.fn();

				const result = await domUtils.renderTable(mockContainer, []);

				expect(mockContainer.innerHTML).toContain("No items found");
				expect(result).toBe(false);
			});

			test("should handle missing container gracefully", async () => {
				console.warn = jest.fn();

				const result = await domUtils.renderTable("#nonexistent", []);

				expect(console.warn).toHaveBeenCalledWith(
					"Container not found for renderTable:",
					"#nonexistent",
				);
				expect(result).toBe(false);
			});
		});

		describe("renderSelectOptions()", () => {
			test("should render select options using Django template with tuple format", async () => {
				const choices = [
					["value1", "Label 1"],
					["value2", "Label 2"],
				];

				mockAPIClient.post.mockResolvedValue({
					html: '<option value="value1">Label 1</option><option value="value2">Label 2</option>',
				});

				const result = await domUtils.renderSelectOptions(
					mockContainer,
					choices,
				);

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/select_options.html",
					context: {
						choices: [
							{ value: "value1", label: "Label 1", selected: false },
							{ value: "value2", label: "Label 2", selected: false },
						],
					},
				});
				expect(result).toBe(true);
			});

			test("should render select options with object format", async () => {
				const choices = [
					{ value: "value1", label: "Label 1" },
					{ value: "value2", label: "Label 2" },
				];

				mockAPIClient.post.mockResolvedValue({
					html: '<option value="value1">Label 1</option><option value="value2">Label 2</option>',
				});

				await domUtils.renderSelectOptions(mockContainer, choices);

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/select_options.html",
					context: {
						choices: [
							{ value: "value1", label: "Label 1", selected: false },
							{ value: "value2", label: "Label 2", selected: false },
						],
					},
				});
			});

			test("should mark current value as selected", async () => {
				const choices = [
					["value1", "Label 1"],
					["value2", "Label 2"],
				];

				mockAPIClient.post.mockResolvedValue({
					html: '<option value="value1">Label 1</option><option value="value2" selected>Label 2</option>',
				});

				await domUtils.renderSelectOptions(mockContainer, choices, "value2");

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/select_options.html",
					context: {
						choices: [
							{ value: "value1", label: "Label 1", selected: false },
							{ value: "value2", label: "Label 2", selected: true },
						],
					},
				});
			});

			test("should fallback to inline HTML on API error", async () => {
				const choices = [
					["value1", "Label 1"],
					["value2", "Label 2"],
				];

				mockAPIClient.post.mockRejectedValue(new Error("API error"));
				console.error = jest.fn();

				const result = await domUtils.renderSelectOptions(
					mockContainer,
					choices,
				);

				expect(mockContainer.innerHTML).toContain("value1");
				expect(mockContainer.innerHTML).toContain("Label 1");
				expect(result).toBe(false);
			});

			test("should handle missing select element gracefully", async () => {
				console.warn = jest.fn();

				const result = await domUtils.renderSelectOptions("#nonexistent", []);

				expect(console.warn).toHaveBeenCalledWith(
					"Select element not found for renderSelectOptions:",
					"#nonexistent",
				);
				expect(result).toBe(false);
			});
		});

		describe("renderPagination()", () => {
			test("should render pagination using Django template", async () => {
				const pagination = {
					number: 2,
					num_pages: 5,
					has_previous: true,
					has_next: true,
				};

				mockAPIClient.post.mockResolvedValue({
					html: '<nav><ul class="pagination">...</ul></nav>',
				});

				const result = await domUtils.renderPagination(
					mockContainer,
					pagination,
				);

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/pagination.html",
					context: {
						show: true,
						has_previous: true,
						previous_page: 1,
						has_next: true,
						next_page: 3,
						pages: expect.arrayContaining([
							{ number: 1, is_current: false },
							{ number: 2, is_current: true },
							{ number: 3, is_current: false },
							{ number: 4, is_current: false },
						]),
					},
				});
				expect(result).toBe(true);
			});

			test("should not render pagination for single page", async () => {
				const pagination = {
					number: 1,
					num_pages: 1,
					has_previous: false,
					has_next: false,
				};

				const result = await domUtils.renderPagination(
					mockContainer,
					pagination,
				);

				expect(mockContainer.innerHTML).toBe("");
				expect(mockAPIClient.post).not.toHaveBeenCalled();
				expect(result).toBe(true);
			});

			test("should not render pagination for no pages", async () => {
				const result = await domUtils.renderPagination(mockContainer, null);

				expect(mockContainer.innerHTML).toBe("");
				expect(mockAPIClient.post).not.toHaveBeenCalled();
				expect(result).toBe(true);
			});

			test("should handle API error gracefully", async () => {
				const pagination = {
					number: 1,
					num_pages: 3,
					has_previous: false,
					has_next: true,
				};

				mockAPIClient.post.mockRejectedValue(new Error("API error"));
				console.error = jest.fn();

				const result = await domUtils.renderPagination(
					mockContainer,
					pagination,
				);

				expect(mockContainer.innerHTML).toBe("");
				expect(result).toBe(false);
			});

			test("should handle missing container gracefully", async () => {
				console.warn = jest.fn();

				const result = await domUtils.renderPagination("#nonexistent", {
					number: 1,
					num_pages: 2,
				});

				expect(console.warn).toHaveBeenCalledWith(
					"Container not found for renderPagination:",
					"#nonexistent",
				);
				expect(result).toBe(false);
			});
		});

		describe("renderDropdown()", () => {
			test("should render dropdown using Django template", async () => {
				const options = {
					button_icon: "three-dots",
					button_class: "btn-sm btn-light",
					button_label: "Actions",
					items: [
						{ label: "Edit", icon: "pencil" },
						{ label: "Delete", icon: "trash" },
					],
				};

				mockAPIClient.post.mockResolvedValue({
					html: '<div class="dropdown">...</div>',
				});

				const result = await domUtils.renderDropdown(options);

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/dropdown_menu.html",
					context: options,
				});
				expect(result).toBe('<div class="dropdown">...</div>');
			});

			test("should use default options", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<div class="dropdown">...</div>',
				});

				await domUtils.renderDropdown();

				expect(mockAPIClient.post).toHaveBeenCalledWith("/users/render-html/", {
					template: "users/components/dropdown_menu.html",
					context: {
						button_icon: "three-dots-vertical",
						button_class: "btn-sm btn-light",
						button_label: "Actions",
						items: [],
					},
				});
			});

			test("should fallback to inline HTML on API error", async () => {
				const options = {
					items: [{ label: "Edit", icon: "pencil" }],
				};

				mockAPIClient.post.mockRejectedValue(new Error("API error"));
				console.error = jest.fn();

				const result = await domUtils.renderDropdown(options);

				expect(result).toContain("dropdown");
				expect(result).toContain("Edit");
			});

			test("should return null on complete failure", async () => {
				mockAPIClient.post.mockResolvedValue({});

				const result = await domUtils.renderDropdown();

				expect(result).toBeNull();
			});
		});
	});

	describe("Global Instance and Exports", () => {
		test("should create global DOMUtils instance", () => {
			// Re-import to trigger global assignment
			global.window.DOMUtils = new DOMUtils();

			expect(global.window.DOMUtils).toBeDefined();
			expect(global.window.DOMUtils).toBeInstanceOf(DOMUtils);
		});

		test("should expose showAlert as global function", () => {
			const domUtilsInstance = new DOMUtils();
			global.window.showAlert =
				domUtilsInstance.showAlert.bind(domUtilsInstance);

			expect(typeof global.window.showAlert).toBe("function");
		});
	});

	describe("Integration Tests", () => {
		test("should chain multiple operations", async () => {
			mockAPIClient.post.mockResolvedValue({
				html: "<div>Loading complete</div>",
			});

			// Show loading
			await domUtils.renderLoading(mockContainer, "Loading...");
			expect(mockContainer.innerHTML).toContain("Loading");

			// Show content
			await domUtils.renderContent(mockContainer, {
				icon: "check",
				text: "Complete",
			});
			expect(mockAPIClient.post).toHaveBeenCalledTimes(2);
		});

		test("should handle rapid consecutive calls", async () => {
			mockAPIClient.post.mockResolvedValue({ html: "<div>Test</div>" });

			const promises = [
				domUtils.renderError(mockContainer, "Error 1"),
				domUtils.renderError(mockContainer, "Error 2"),
				domUtils.renderError(mockContainer, "Error 3"),
			];

			await Promise.all(promises);

			expect(mockAPIClient.post).toHaveBeenCalledTimes(3);
		});

		test("should work with different container types", async () => {
			mockAPIClient.post.mockResolvedValue({ html: "<div>Test</div>" });

			// With element
			await domUtils.renderError(mockContainer, "Error");
			expect(mockAPIClient.post).toHaveBeenCalledTimes(1);

			// With selector
			await domUtils.renderError("#test-container", "Error");
			expect(mockAPIClient.post).toHaveBeenCalledTimes(2);
		});
	});
});
