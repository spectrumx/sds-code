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
		test.each([
			["success", "Success message"],
			["error", "Error message"],
			["warning", "Warning message"],
			["info", "Info message"],
		])("should show %s toast notification", (type, message) => {
			domUtils.showAlert(message, type);

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

				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					{
						template: "users/components/error.html",
						context: {
							message: "Error message",
							format: "inline",
						},
					},
					null,
					true,
				);
				expect(mockContainer.innerHTML).toBe(
					'<span class="text-danger">Error message</span>',
				);
				expect(result).toBe(true);
			});

			test.each([
				[
					"table",
					{ format: "table", colspan: 5 },
					'<tr><td colspan="5" class="text-danger">Error</td></tr>',
					{ message: "Error message", format: "table", colspan: 5 },
				],
				[
					"alert",
					{ format: "alert" },
					'<div class="alert alert-danger">Error message</div>',
					{ message: "Error message", format: "alert" },
				],
			])(
				"should render error with %s format",
				async (formatName, options, html, expectedContext) => {
					mockAPIClient.post.mockResolvedValue({ html });

					await domUtils.renderError(mockContainer, "Error message", options);

					expect(mockAPIClient.post).toHaveBeenCalledWith(
						"/users/render-html/",
						{
							template: "users/components/error.html",
							context: expectedContext,
						},
						null,
						true,
					);
				},
			);

			test.each([
				["inline", {}, '<span class="text-danger">Error message</span>'],
				[
					"table",
					{ format: "table", colspan: 5 },
					'<tr><td colspan="5" class="text-center text-danger">Error message</td></tr>',
				],
			])(
				"should fallback to %s HTML on API error",
				async (formatName, options, expectedHtml) => {
					mockAPIClient.post.mockRejectedValue(new Error("API error"));
					console.error = jest.fn();

					const result = await domUtils.renderError(
						mockContainer,
						"Error message",
						options,
					);

					expect(mockContainer.innerHTML).toBe(expectedHtml);
					expect(result).toBe(false);
				},
			);

			test("should work with selector string", async () => {
				await domUtils.renderError("#test-container", "Error message");

				expect(document.querySelector).toHaveBeenCalledWith("#test-container");
				expect(mockAPIClient.post).toHaveBeenCalled();
			});
		});

		describe("renderLoading()", () => {
			test.each([
				[
					"default options",
					undefined,
					undefined,
					'<span class="spinner-border"></span> Loading...',
					{
						text: "Loading...",
						format: "spinner",
						size: "md",
						color: "primary",
					},
				],
				[
					"custom text",
					"Please wait...",
					undefined,
					'<span class="spinner-border"></span> Please wait...',
					{
						text: "Please wait...",
						format: "spinner",
						size: "md",
						color: "primary",
					},
				],
				[
					"custom options",
					"Loading...",
					{ size: "sm", color: "secondary" },
					'<span class="spinner-border spinner-border-sm"></span>',
					{
						text: "Loading...",
						format: "spinner",
						size: "sm",
						color: "secondary",
					},
				],
			])(
				"should render loading with %s",
				async (description, text, options, expectedHtml, expectedContext) => {
					mockAPIClient.post.mockResolvedValue({ html: expectedHtml });

					const result = await domUtils.renderLoading(
						mockContainer,
						text,
						options,
					);

					expect(mockAPIClient.post).toHaveBeenCalledWith(
						"/users/render-html/",
						{
							template: "users/components/loading.html",
							context: expectedContext,
						},
						null,
						true,
					);
					expect(mockContainer.innerHTML).toBe(expectedHtml);
					expect(result).toBe(true);
				},
			);
		});

		describe("renderContent()", () => {
			test.each([
				[
					{ icon: "check", text: "Success" },
					'<i class="bi bi-check"></i> Success',
					{ icon: "check", text: "Success" },
				],
				[
					{ icon: "exclamation-circle", text: "Warning", color: "warning" },
					'<i class="bi bi-exclamation-circle text-warning"></i> Warning',
					{ icon: "exclamation-circle", text: "Warning", color: "warning" },
				],
			])(
				"should render content with options",
				async (options, expectedHtml, expectedContext) => {
					mockAPIClient.post.mockResolvedValue({ html: expectedHtml });

					const result = await domUtils.renderContent(mockContainer, options);

					expect(mockAPIClient.post).toHaveBeenCalledWith(
						"/users/render-html/",
						{
							template: "users/components/content.html",
							context: expectedContext,
						},
						null,
						true,
					);
					expect(mockContainer.innerHTML).toBe(expectedHtml);
					expect(result).toBe(true);
				},
			);
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

				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					{
						template: "users/components/table_rows.html",
						context: {
							rows: rows,
							empty_message: "No items found",
							empty_colspan: 5,
						},
					},
					null,
					true,
				);
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

				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					{
						template: "users/components/table_rows.html",
						context: {
							rows: [],
							empty_message: "No data",
							empty_colspan: 3,
							colspan: 3,
						},
					},
					null,
					true,
				);
			});
		});

		describe("renderSelectOptions()", () => {
			test.each([
				[
					"tuple format",
					[
						["value1", "Label 1"],
						["value2", "Label 2"],
					],
					[
						{ value: "value1", label: "Label 1", selected: false },
						{ value: "value2", label: "Label 2", selected: false },
					],
				],
				[
					"object format",
					[
						{ value: "value1", label: "Label 1" },
						{ value: "value2", label: "Label 2" },
					],
					[
						{ value: "value1", label: "Label 1", selected: false },
						{ value: "value2", label: "Label 2", selected: false },
					],
				],
			])(
				"should render select options with %s",
				async (formatName, choices, expectedChoices) => {
					mockAPIClient.post.mockResolvedValue({
						html: '<option value="value1">Label 1</option><option value="value2">Label 2</option>',
					});

					await domUtils.renderSelectOptions(mockContainer, choices);

					expect(mockAPIClient.post).toHaveBeenCalledWith(
						"/users/render-html/",
						{
							template: "users/components/select_options.html",
							context: {
								choices: expectedChoices,
							},
						},
						null,
						true,
					);
				},
			);

			test("should mark current value as selected", async () => {
				const choices = [
					["value1", "Label 1"],
					["value2", "Label 2"],
				];

				mockAPIClient.post.mockResolvedValue({
					html: '<option value="value1">Label 1</option><option value="value2" selected>Label 2</option>',
				});

				await domUtils.renderSelectOptions(mockContainer, choices, "value2");

				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					{
						template: "users/components/select_options.html",
						context: {
							choices: [
								{ value: "value1", label: "Label 1", selected: false },
								{ value: "value2", label: "Label 2", selected: true },
							],
						},
					},
					null,
					true,
				);
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

				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					{
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
					},
					null,
					true,
				);
				expect(result).toBe(true);
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

				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					{
						template: "users/components/dropdown_menu.html",
						context: options,
					},
					null,
					true,
				);
				expect(result).toBe('<div class="dropdown">...</div>');
			});

			test("should use default options", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<div class="dropdown">...</div>',
				});

				await domUtils.renderDropdown();

				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					{
						template: "users/components/dropdown_menu.html",
						context: {
							button_icon: "three-dots-vertical",
							button_class: "btn-sm btn-light",
							button_label: "Actions",
							items: [],
						},
					},
					null,
					true,
				);
			});

			test("should return null on complete failure", async () => {
				mockAPIClient.post.mockResolvedValue({});

				const result = await domUtils.renderDropdown();

				expect(result).toBeNull();
			});
		});

		describe("Common Error Handling", () => {
			test.each([
				[
					"renderError",
					async (container) =>
						await domUtils.renderError(container, "Error message"),
					"Container not found for renderError:",
				],
				[
					"renderLoading",
					async (container) => await domUtils.renderLoading(container),
					"Container not found for renderLoading:",
				],
				[
					"renderContent",
					async (container) =>
						await domUtils.renderContent(container, {
							icon: "check",
							text: "Success",
						}),
					"Container not found for renderContent:",
				],
				[
					"renderTable",
					async (container) => await domUtils.renderTable(container, []),
					"Container not found for renderTable:",
				],
				[
					"renderSelectOptions",
					async (container) =>
						await domUtils.renderSelectOptions(container, []),
					"Select element not found for renderSelectOptions:",
				],
				[
					"renderPagination",
					async (container) =>
						await domUtils.renderPagination(container, {
							number: 1,
							num_pages: 2,
						}),
					"Container not found for renderPagination:",
				],
			])(
				"should handle missing container gracefully for %s",
				async (methodName, renderFn, expectedWarning) => {
					console.warn = jest.fn();

					const result = await renderFn("#nonexistent");

					expect(console.warn).toHaveBeenCalledWith(
						expectedWarning,
						"#nonexistent",
					);
					expect(result).toBe(false);
				},
			);

			test.each([
				[
					"renderError",
					async (container) =>
						await domUtils.renderError(container, "Error message"),
					'<span class="text-danger">Error message</span>',
					true, // use toBe
				],
				[
					"renderLoading",
					async (container) => await domUtils.renderLoading(container),
					"spinner-border",
					false, // use toContain
				],
				[
					"renderContent",
					async (container) =>
						await domUtils.renderContent(container, {
							icon: "check",
							text: "Success",
						}),
					"bi-check",
					false, // use toContain
				],
				[
					"renderTable",
					async (container) => await domUtils.renderTable(container, []),
					"No items found",
					false, // use toContain
				],
				[
					"renderSelectOptions",
					async (container) =>
						await domUtils.renderSelectOptions(container, [
							["value1", "Label 1"],
						]),
					"value1",
					false, // use toContain
				],
				[
					"renderPagination",
					async (container) =>
						await domUtils.renderPagination(container, {
							number: 1,
							num_pages: 3,
							has_previous: false,
							has_next: true,
						}),
					"",
					true, // use toBe
				],
			])(
				"should fallback on API error for %s",
				async (methodName, renderFn, expectedContent, useExactMatch) => {
					mockAPIClient.post.mockRejectedValue(new Error("API error"));
					console.error = jest.fn();

					const result = await renderFn(mockContainer);

					if (useExactMatch) {
						expect(mockContainer.innerHTML).toBe(expectedContent);
					} else {
						expect(mockContainer.innerHTML).toContain(expectedContent);
					}
					expect(result).toBe(false);
				},
			);
		});
	});
});
