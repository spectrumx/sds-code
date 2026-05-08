/**
 * PageLifecycleManager.initializePagination: server-rendered pagination links
 * update the page query (same behavior users rely on post-refactor).
 */
const { PaginationManager } = require("../PaginationManager.js");
const { PageLifecycleManager } = require("../PageLifecycleManager.js");

describe("PageLifecycleManager.initializePagination", () => {
	beforeAll(() => {
		window.PaginationManager = PaginationManager;
	});

	beforeEach(() => {
		document.body.innerHTML = "";
		window.history.replaceState({}, "", "http://localhost/files/?page=1&q=stay");
		Object.defineProperty(document, "readyState", {
			value: "loading",
			configurable: true,
		});
		const wrap = document.createElement("div");
		wrap.id = "files-pagination";
		wrap.innerHTML =
			'<nav class="pagination"><a href="#" class="page-link" data-page="3">3</a></nav>';
		document.body.appendChild(wrap);
	});

	afterEach(() => {
		document.body.innerHTML = "";
		delete window.location;
	});

	test("clicking a page link sets page in the query string and keeps other params", () => {
		let query = "page=1&q=stay";
		Object.defineProperty(window, "location", {
			configurable: true,
			value: {
				pathname: "/files/",
				get search() {
					return query ? `?${query}` : "";
				},
				set search(v) {
					query = String(v).replace(/^\?/, "");
				},
			},
		});

		const mgr = new PageLifecycleManager({
			pageType: "capture-list",
			permissions: {},
		});
		mgr.initializePagination();
		document
			.querySelector("#files-pagination a.page-link")
			.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
		expect(query).toMatch(/page=3/);
		expect(query).toMatch(/q=stay/);
	});
});
