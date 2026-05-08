/**
 * Behavioral contract: table header sort updates the URL the same way
 * deprecated/components.js TableManager did; core/TableManager preserves
 * that for sortBehavior "pushState" and adds "reload" / "callback".
 *
 * Uses the default Jest jsdom document/window. Swaps in the real URL /
 * URLSearchParams implementations because jest.setup.js provides a minimal
 * URLSearchParams that mishandles `window.location.search` (leading `?`).
 */
const TABLE_BODY = `
  <table id="tm-table"><thead><tr>
    <th class="sortable" data-sort="name"><i class="bi sort-icon"></i></th>
    <th class="sortable" data-sort="created_at"><i class="bi sort-icon"></i></th>
  </tr></thead><tbody></tbody></table>
  <div id="tm-loading"></div><div id="tm-pag"></div>
`;

function mountSortPage(searchParamsObj) {
	document.body.innerHTML = TABLE_BODY;
	const u = new URL("http://localhost/captures/");
	for (const [k, v] of Object.entries(searchParamsObj)) {
		u.searchParams.set(k, v);
	}
	// Relative URL so jsdom updates location.search reliably (absolute href can leave search empty).
	window.history.replaceState({}, "", `${u.pathname}${u.search}`);
}

describe("table sort URL behavior", () => {
	let savedURLSearchParams;
	let savedURL;

	beforeAll(() => {
		savedURLSearchParams = global.URLSearchParams;
		savedURL = global.URL;
		global.URLSearchParams = window.URLSearchParams;
		global.URL = window.URL;
	});

	afterAll(() => {
		global.URLSearchParams = savedURLSearchParams;
		global.URL = savedURL;
	});

	describe("deprecated components.js TableManager — sort updates URL (pushState)", () => {
		let DeprecatedTableManager;

		beforeAll(() => {
			// eslint-disable-next-line global-require
			({ TableManager: DeprecatedTableManager } = require("../deprecated/components.js"));
		});

		afterEach(() => {
			jest.restoreAllMocks();
			document.body.innerHTML = "";
		});

		beforeEach(() => {
			mountSortPage({ sort_by: "created_at", sort_order: "desc" });
			jest.spyOn(window.history, "pushState");
		});

		test("clicking another column sets sort_by, first order asc, page 1 in pushed URL", () => {
			// eslint-disable-next-line no-new
			new DeprecatedTableManager({
				tableId: "tm-table",
				loadingIndicatorId: "tm-loading",
				paginationContainerId: "tm-pag",
			});
			const [nameHeader] = document.querySelectorAll("th.sortable");
			nameHeader.click();

			expect(window.history.pushState).toHaveBeenCalled();
			const pushed = window.history.pushState.mock.calls.at(-1)[2];
			expect(pushed).toMatch(/sort_by=name/);
			expect(pushed).toMatch(/sort_order=asc/);
			expect(pushed).toMatch(/page=1/);
		});
	});

	describe("core/TableManager.js — pushState + callback", () => {
		let CoreTableManager;

		beforeAll(() => {
			// eslint-disable-next-line global-require
			const { ComponentUtils } = require("../core/ComponentUtils.js");
			window.ComponentUtils = ComponentUtils;
		});

		beforeEach(() => {
			mountSortPage({ sort_by: "created_at", sort_order: "desc" });
			jest.resetModules();
			// eslint-disable-next-line global-require
			({ TableManager: CoreTableManager } = require("../core/TableManager.js"));
			jest.spyOn(window.history, "pushState");
		});

		afterEach(() => {
			jest.restoreAllMocks();
			document.body.innerHTML = "";
		});

		test("default sortBehavior matches deprecated (pushState)", () => {
			// eslint-disable-next-line no-new
			new CoreTableManager({
				tableId: "tm-table",
				loadingIndicatorId: "tm-loading",
				paginationContainerId: "tm-pag",
			});
			document.querySelector("th.sortable").click();
			const pushed = window.history.pushState.mock.calls.at(-1)[2];
			expect(pushed).toMatch(/sort_by=name/);
			expect(pushed).toMatch(/sort_order=asc/);
			expect(pushed).toMatch(/page=1/);
		});

		test("sortBehavior callback invokes onSortChange instead of history or location", () => {
			const onSortChange = jest.fn();
			// eslint-disable-next-line no-new
			new CoreTableManager({
				tableId: "tm-table",
				loadingIndicatorId: "tm-loading",
				paginationContainerId: "tm-pag",
				sortBehavior: "callback",
				onSortChange,
			});
			document.querySelector("th.sortable").click();
			expect(onSortChange).toHaveBeenCalledWith({
				sort_by: "name",
				sort_order: "asc",
				page: "1",
			});
			expect(window.history.pushState).not.toHaveBeenCalled();
		});
	});

	describe("core/TableManager.js — sortBehavior reload (isolated)", () => {
		beforeAll(() => {
			// eslint-disable-next-line global-require
			const { ComponentUtils } = require("../core/ComponentUtils.js");
			window.ComponentUtils = ComponentUtils;
		});

		afterEach(() => {
			jest.restoreAllMocks();
			document.body.innerHTML = "";
			try {
				delete window.location;
			} catch (_) {
				/* jsdom */
			}
		});

		test("sortBehavior reload assigns location.search with encoded params", () => {
			mountSortPage({ sort_by: "created_at", sort_order: "desc" });
			let query = "sort_by=created_at&sort_order=desc";
			Object.defineProperty(window, "location", {
				configurable: true,
				value: {
					pathname: "/captures/",
					get search() {
						return query ? `?${query}` : "";
					},
					set search(v) {
						query = String(v).replace(/^\?/, "");
					},
				},
			});
			jest.resetModules();
			// eslint-disable-next-line global-require
			const { TableManager: ReloadTableManager } = require("../core/TableManager.js");
			// eslint-disable-next-line no-new
			new ReloadTableManager({
				tableId: "tm-table",
				loadingIndicatorId: "tm-loading",
				paginationContainerId: "tm-pag",
				sortBehavior: "reload",
			});
			document.querySelector("th.sortable").click();
			expect(query).toMatch(/sort_by=name/);
			expect(query).toMatch(/sort_order=asc/);
			expect(query).toMatch(/page=1/);
		});
	});
});
