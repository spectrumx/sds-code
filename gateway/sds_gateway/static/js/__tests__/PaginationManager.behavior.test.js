/**
 * Pagination: deprecated client-rendered PaginationManager vs
 * PageLifecycleManager.wireServerRenderedPagination (server HTML links).
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

describe("PageLifecycleManager.wireServerRenderedPagination", () => {
	const { PageLifecycleManager } = require("../core/PageLifecycleManager.js");

	beforeEach(() => {
		mountPaginationPage("http://localhost/captures/?page=1");
		const host = document.createElement("div");
		host.id = "pag-host-core";
		host.innerHTML =
			'<nav class="pagination"><a href="#" class="page-link" data-page="4">4</a></nav>';
		document.body.appendChild(host);
	});

	afterEach(() => {
		document.body.innerHTML = "";
	});

	test("clicking a server-rendered page link calls onPageChange with that page number", () => {
		const onPageChange = jest.fn();
		PageLifecycleManager.wireServerRenderedPagination("pag-host-core", onPageChange);
		const linkTo4 = document.querySelector("#pag-host-core a.page-link");
		expect(linkTo4).toBeTruthy();
		linkTo4.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
		expect(onPageChange).toHaveBeenCalledWith(4);
	});
});
