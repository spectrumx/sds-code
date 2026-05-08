/**
 * Pagination: deprecated/components.js vs core/PaginationManager.js
 * (click on rendered link invokes onPageChange with the page number).
 */
const paginationPayload = {
	num_pages: 5,
	number: 2,
	has_previous: true,
	has_next: true,
};

function mountPaginationPage(url) {
	document.body.innerHTML = "";
	window.history.replaceState({}, "", url);
}

describe("deprecated components.js PaginationManager — click invokes onPageChange", () => {
	let DeprecatedPaginationManager;

	beforeAll(() => {
		// eslint-disable-next-line global-require
		({ PaginationManager: DeprecatedPaginationManager } = require("../deprecated/components.js"));
	});

	beforeEach(() => {
		mountPaginationPage("http://localhost/captures/?page=1");
		const host = document.createElement("div");
		host.id = "pag-host";
		document.body.appendChild(host);
	});

	afterEach(() => {
		document.body.innerHTML = "";
	});

	test("clicking a rendered page link calls onPageChange with that page number", () => {
		const onPageChange = jest.fn();
		const mgr = new DeprecatedPaginationManager({
			containerId: "pag-host",
			onPageChange,
		});
		mgr.update(paginationPayload);
		const linkTo4 = Array.from(
			document.querySelectorAll("a.page-link"),
		).find((a) => a.getAttribute("data-page") === "4");
		expect(linkTo4).toBeTruthy();
		linkTo4.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
		expect(onPageChange).toHaveBeenCalledWith(4);
	});
});

describe("core/PaginationManager.js — same click → onPageChange behavior", () => {
	let CorePaginationManager;

	beforeEach(() => {
		mountPaginationPage("http://localhost/captures/?page=1");
		jest.resetModules();
		// eslint-disable-next-line global-require
		({ PaginationManager: CorePaginationManager } = require("../core/PaginationManager.js"));
		const host = document.createElement("div");
		host.id = "pag-host-core";
		document.body.appendChild(host);
	});

	afterEach(() => {
		document.body.innerHTML = "";
	});

	test("clicking a rendered page link calls onPageChange with that page number", () => {
		const onPageChange = jest.fn();
		const mgr = new CorePaginationManager({
			containerId: "pag-host-core",
			onPageChange,
		});
		mgr.update(paginationPayload);
		const linkTo4 = Array.from(
			document.querySelectorAll("a.page-link"),
		).find((a) => a.getAttribute("data-page") === "4");
		expect(linkTo4).toBeTruthy();
		linkTo4.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
		expect(onPageChange).toHaveBeenCalledWith(4);
	});
});
