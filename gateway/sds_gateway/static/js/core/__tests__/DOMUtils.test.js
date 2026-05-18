/**
 * Jest tests for DOMUtils
 * Tests DOM manipulation utilities with API-based template rendering
 */

import { DOMUtils } from "../DOMUtils.js";

/** Approximate Element.textContent from innerHTML for mock nodes (strip tags, decode entities). */
function mockTextContentFromHtml(html) {
	if (html == null || html === "") return "";
	const noTags = String(html).replace(/<[^>]*>/g, "");
	return noTags
		.replace(/&lt;/g, "<")
		.replace(/&gt;/g, ">")
		.replace(/&amp;/g, "&");
}

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
			appendChild: jest.fn(),
			classList: {
				add: jest.fn(),
				remove: jest.fn(),
				contains: jest.fn(() => false),
			},
			querySelector: jest.fn(),
			querySelectorAll: jest.fn(() => []),
		};
		Object.defineProperty(mockContainer, "textContent", {
			get() {
				return mockTextContentFromHtml(this.innerHTML);
			},
			configurable: true,
		});

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
				const child = {
					id: "",
					remove: jest.fn(),
					addEventListener: jest.fn(),
				};
				const el = {
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
					get firstElementChild() {
						const html = String(this.innerHTML || "").trim();
						return html ? child : null;
					},
				};
				return el;
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
		window.bootstrap = global.bootstrap;

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

	describe("showMessage() toasts", () => {
		let mockToastDiv;
		let mockTempDiv;

		beforeEach(() => {
			mockToastDiv = {
				id: "",
				addEventListener: jest.fn(),
			};

			mockTempDiv = {
				innerHTML: "",
				firstElementChild: mockToastDiv,
			};

			global.document.createElement = jest.fn((tag) => {
				if (tag === "div") {
					return mockTempDiv;
				}
				return {
					tagName: tag,
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
			});

			mockAPIClient.post.mockResolvedValue({
				html: '<div class="toast">Toast content</div>',
			});
		});

		test("showMessage posts message.html and shows toast", async () => {
			await domUtils.showMessage("Test message", {
				variant: "success",
				placement: "toast",
				presentation: "toast",
			});

			expect(mockAPIClient.post).toHaveBeenCalledWith(
				"/users/render-html/",
				{
					template: "users/components/message.html",
					context: {
						message: "Test message",
						type: "success",
						presentation: "toast",
					},
				},
				null,
				true,
			);
			expect(mockToastContainer.appendChild).toHaveBeenCalledWith(mockToastDiv);
			expect(global.bootstrap.Toast).toHaveBeenCalledWith(mockToastDiv);
		});

		test("showMessage maps variants to template type", async () => {
			const cases = [
				["success", "success"],
				["danger", "error"],
				["warning", "warning"],
				["info", "info"],
			];

			for (const [variant, expectedType] of cases) {
				jest.clearAllMocks();
				await domUtils.showMessage("Hello", {
					variant,
					placement: "toast",
					presentation: "toast",
				});

				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					{
						template: "users/components/message.html",
						context: {
							message: "Hello",
							type: expectedType,
							presentation: "toast",
						},
					},
					null,
					true,
				);
			}
		});

		test("should handle missing toast container after render", async () => {
			document.getElementById = jest.fn((id) => {
				if (id === "toast-container") return null;
				if (id === "test-container") return mockContainer;
				return null;
			});
			console.error = jest.fn();

			const ok = await domUtils.showMessage("Test message", {
				variant: "success",
				placement: "toast",
				presentation: "toast",
			});

			expect(ok).toBe(false);
			expect(mockAPIClient.post).toHaveBeenCalled();
			expect(console.error).toHaveBeenCalled();
			expect(mockToastContainer.appendChild).not.toHaveBeenCalled();
		});

		test("should handle missing HTML in API response", async () => {
			mockAPIClient.post.mockResolvedValue({});
			console.error = jest.fn();

			const ok = await domUtils.showMessage("Test message", {
				variant: "success",
				placement: "toast",
				presentation: "toast",
			});

			expect(ok).toBe(false);
			expect(console.error).toHaveBeenCalledWith(
				"showMessage: no HTML from render-html",
			);
			expect(mockToastContainer.appendChild).not.toHaveBeenCalled();
		});

		test("should handle failed HTML parsing", async () => {
			mockTempDiv.firstElementChild = null;
			console.error = jest.fn();

			const ok = await domUtils.showMessage("Test message", {
				variant: "success",
				placement: "toast",
				presentation: "toast",
			});

			expect(ok).toBe(false);
			expect(console.error).toHaveBeenCalledWith(
				"showMessage: failed to parse message HTML",
			);
			expect(mockToastContainer.appendChild).not.toHaveBeenCalled();
		});

		test("should handle missing Bootstrap Toast", async () => {
			global.bootstrap = null;
			window.bootstrap = null;
			console.error = jest.fn();

			const ok = await domUtils.showMessage("Test message", {
				variant: "success",
				placement: "toast",
				presentation: "toast",
			});

			expect(ok).toBe(false);
			expect(console.error).toHaveBeenCalled();
			expect(mockToastContainer.appendChild).not.toHaveBeenCalled();
		});

		test("should handle API errors gracefully", async () => {
			mockAPIClient.post.mockRejectedValue(new Error("API error"));
			console.error = jest.fn();

			const ok = await domUtils.showMessage("Test message", {
				variant: "success",
				placement: "toast",
				presentation: "toast",
			});

			expect(ok).toBe(false);
			expect(console.error).toHaveBeenCalledWith(
				"showMessage failed:",
				expect.any(Error),
			);
			expect(mockToastContainer.appendChild).not.toHaveBeenCalled();
		});
	});

	describe("API-Based Rendering Methods", () => {
		describe("showMessage() replace placement", () => {
			let mockResultNode;
			let mockWrapDiv;

			beforeEach(() => {
				mockResultNode = {
					id: "",
					remove: jest.fn(),
					addEventListener: jest.fn(),
				};
				mockWrapDiv = {
					innerHTML: "",
					get firstElementChild() {
						return mockResultNode;
					},
				};
				global.document.createElement = jest.fn((tag) => {
					if (tag === "div") return mockWrapDiv;
					return null;
				});
			});

			test("posts message.html and replaces target content", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<span class="text-danger">Error message</span>',
				});

				const result = await domUtils.showMessage("Error message", {
					variant: "danger",
					placement: "replace",
					target: mockContainer,
					presentation: "inline",
				});

				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					{
						template: "users/components/message.html",
						context: {
							message: "Error message",
							type: "error",
							presentation: "inline",
						},
					},
					null,
					true,
				);
				expect(mockContainer.appendChild).toHaveBeenCalledWith(mockResultNode);
				expect(result).toBe(true);
			});

			test.each([
				[
					"table",
					"table",
					'<tr><td colspan="5" class="text-center text-danger">Error</td></tr>',
					{
						message: "Error message",
						type: "error",
						presentation: "table",
						colspan: 5,
					},
				],
				[
					"alert",
					"alert",
					'<div class="alert alert-danger">Error message</div>',
					{
						message: "Error message",
						type: "error",
						presentation: "alert",
					},
				],
			])(
				"posts message.html with presentation %s",
				async (_label, presentation, html, expectedContext) => {
					mockAPIClient.post.mockResolvedValue({ html });

					await domUtils.showMessage("Error message", {
						variant: "danger",
						placement: "replace",
						target: mockContainer,
						presentation,
						templateContext:
							presentation === "table" ? { colspan: 5 } : {},
					});

					expect(mockAPIClient.post).toHaveBeenCalledWith(
						"/users/render-html/",
						{
							template: "users/components/message.html",
							context: expectedContext,
						},
						null,
						true,
					);
				},
			);

			test("returns false on API error without mutating container", async () => {
				mockContainer.innerHTML = "<p>prior</p>";
				mockAPIClient.post.mockRejectedValue(new Error("API error"));
				console.error = jest.fn();

				const result = await domUtils.showMessage("Error message", {
					variant: "danger",
					placement: "replace",
					target: mockContainer,
					presentation: "table",
					templateContext: { colspan: 5 },
				});

				expect(mockContainer.innerHTML).toBe("<p>prior</p>");
				expect(result).toBe(false);
			});

			test("resolves target via selector string", async () => {
				mockAPIClient.post.mockResolvedValue({
					html: '<span class="text-danger">x</span>',
				});

				await domUtils.showMessage("Error message", {
					variant: "danger",
					placement: "replace",
					target: "#test-container",
					presentation: "inline",
				});

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
			test("should post text cells (kind text) to Django table_rows template", async () => {
				const rows = [
					{
						cells: [
							{ kind: "text", value: "Cell 1" },
							{ kind: "text", value: "Cell 2" },
						],
					},
					{
						cells: [
							{ kind: "text", value: "Cell 3" },
							{ kind: "text", value: "Cell 4" },
						],
					},
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

			test("text cells: server escapes markup in value (mocked Django response)", async () => {
				const rows = [
					{
						cells: [
							{ kind: "text", value: "Plain" },
							{ kind: "text", value: "<script>alert(1)</script>" },
						],
					},
				];
				mockAPIClient.post.mockResolvedValue({
					html: "<tr><td>Plain</td><td>&lt;script&gt;alert(1)&lt;/script&gt;</td></tr>",
				});

				await domUtils.renderTable(mockContainer, rows);

				expect(mockContainer.innerHTML).not.toMatch(/<script/i);
				expect(mockContainer.textContent).toContain("alert(1)");
			});

			test("html kind: posts structured cell for render_cell_node (simple)", async () => {
				const rows = [
					{
						cells: [
							{
								kind: "html",
								tag: "span",
								class: "badge bg-success",
								text: "OK",
							},
						],
					},
				];
				mockAPIClient.post.mockResolvedValue({
					html: '<tr><td><span class="badge bg-success">OK</span></td></tr>',
				});

				await domUtils.renderTable(mockContainer, rows);

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
				expect(mockContainer.innerHTML).toContain("badge");
			});

			test("html kind: posts nested nodes for render_cell_node", async () => {
				const rows = [
					{
						cells: [
							{
								kind: "html",
								tag: "div",
								class: "row",
								nested: [
									{
										tag: "span",
										class: "text-muted",
										text: "nested text",
									},
								],
							},
						],
					},
				];
				mockAPIClient.post.mockResolvedValue({
					html: '<tr><td><div class="row"><span class="text-muted">nested text</span></div></td></tr>',
				});

				await domUtils.renderTable(mockContainer, rows);

				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					expect.objectContaining({
						template: "users/components/table_rows.html",
						context: expect.objectContaining({
							rows: rows,
						}),
					}),
					null,
					true,
				);
				expect(mockContainer.textContent).toContain("nested text");
			});

			test("html kind: disallowed tags stripped server-side (mock simulates Django allowlist)", async () => {
				const rows = [
					{
						cells: [
							{
								kind: "html",
								tag: "div",
								nested: [
									{ tag: "script", text: "alert(1)" },
									{ tag: "span", text: "safe" },
								],
							},
						],
					},
				];
				mockAPIClient.post.mockResolvedValue({
					html: "<tr><td><div><span>safe</span></div></td></tr>",
				});

				await domUtils.renderTable(mockContainer, rows);

				expect(mockContainer.innerHTML).not.toMatch(/<script/i);
				expect(mockContainer.textContent).toContain("safe");
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
						},
					},
					null,
					true,
				);
			});

			test("should honor options.template", async () => {
				mockAPIClient.post.mockResolvedValue({ html: "<tr></tr>" });
				await domUtils.renderTable(mockContainer, [], {
					template: "users/components/other_rows.html",
				});
				expect(mockAPIClient.post).toHaveBeenCalledWith(
					"/users/render-html/",
					expect.objectContaining({
						template: "users/components/other_rows.html",
					}),
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
					"showMessage (replace)",
					async (container) =>
						await domUtils.showMessage("Error message", {
							variant: "danger",
							placement: "replace",
							target: container,
							presentation: "inline",
						}),
					"showMessage: target not found:",
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
					"showMessage",
					async (container) =>
						await domUtils.showMessage("Error message", {
							variant: "danger",
							placement: "replace",
							target: container,
							presentation: "inline",
						}),
				],
				[
					"renderLoading",
					async (container) => await domUtils.renderLoading(container),
				],
				[
					"renderContent",
					async (container) =>
						await domUtils.renderContent(container, {
							icon: "check",
							text: "Success",
						}),
				],
				[
					"renderTable",
					async (container) => await domUtils.renderTable(container, []),
				],
				[
					"renderSelectOptions",
					async (container) =>
						await domUtils.renderSelectOptions(container, [
							["value1", "Label 1"],
						]),
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
				],
			])(
				"returns false on API error for %s without mutating container",
				async (methodName, renderFn) => {
					mockContainer.innerHTML = "<p>prior</p>";
					mockAPIClient.post.mockRejectedValue(new Error("API error"));
					console.error = jest.fn();

					const result = await renderFn(mockContainer);

					expect(mockContainer.innerHTML).toBe("<p>prior</p>");
					expect(result).toBe(false);
				},
			);
		});
	});

	describe("initializeListDropdowns()", () => {
		let mockToggle;
		let mockDropdownMenu;

		beforeEach(() => {
			mockDropdownMenu = {
				classList: { contains: jest.fn((cls) => cls === "dropdown-menu") },
			};

			mockToggle = {
				nextElementSibling: mockDropdownMenu,
				dataset: {},
				closest: jest.fn((sel) =>
					sel === ".btn-icon-dropdown" ? mockToggle : null,
				),
			};

			global.document.querySelectorAll = jest.fn((selector) => {
				if (selector === ".btn-icon-dropdown") return [mockToggle];
				return [];
			});

			global.document.bodyAppendChildSpy = jest
				.spyOn(global.document.body, "appendChild")
				.mockImplementation(() => {});

			global.bootstrap = {
				...global.bootstrap,
				Toast: global.bootstrap?.Toast,
				Modal: global.bootstrap?.Modal,
				Dropdown: jest.fn().mockImplementation(() => ({
					dispose: jest.fn(),
				})),
			};
			global.bootstrap.Dropdown.getInstance = jest.fn(() => null);
			window.bootstrap = global.bootstrap;
			global.document.addEventListener = jest.fn();
		});

		afterEach(() => {
			if (global.document.bodyAppendChildSpy?.mockRestore) {
				global.document.bodyAppendChildSpy.mockRestore();
			}
		});

		test("should initialize dropdowns for all toggle buttons", () => {
			domUtils.initializeListDropdowns();

			expect(document.querySelectorAll).toHaveBeenCalledWith(
				".btn-icon-dropdown",
			);
			expect(global.bootstrap.Dropdown).toHaveBeenCalledWith(mockToggle, {
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
		});

		test("should dispose existing dropdown instances", () => {
			const existingInstance = {
				dispose: jest.fn(),
			};
			global.bootstrap.Dropdown.getInstance = jest.fn(() => existingInstance);

			domUtils.initializeListDropdowns();

			expect(existingInstance.dispose).toHaveBeenCalled();
		});

		test("should move dropdown menu to body on show", () => {
			domUtils.initializeListDropdowns();

			const showHandler = global.document.addEventListener.mock.calls.find(
				(call) => call[0] === "show.bs.dropdown",
			)?.[1];

			if (showHandler) {
				showHandler({ target: mockToggle });
				expect(global.document.bodyAppendChildSpy).toHaveBeenCalledWith(
					mockDropdownMenu,
				);
			}
		});

		test("should prevent row click when clicking dropdown elements", () => {
			const mockEvent = {
				target: {
					closest: jest.fn((selector) => {
						if (selector === ".dropdown") return { classList: {} };
						return null;
					}),
				},
				stopPropagation: jest.fn(),
			};

			domUtils.initializeListDropdowns();

			const clickHandler = global.document.addEventListener.mock.calls.find(
				(call) => call[0] === "click",
			)?.[1];

			if (clickHandler) {
				clickHandler(mockEvent);
				expect(mockEvent.stopPropagation).toHaveBeenCalled();
			}
		});

		test("should handle missing dropdown menu gracefully", () => {
			mockToggle.nextElementSibling = null;

			expect(() => {
				domUtils.initializeListDropdowns();
			}).not.toThrow();
		});
	});
});
