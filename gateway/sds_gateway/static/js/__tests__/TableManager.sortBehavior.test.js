/**
 * Behavioral contract: table header sort updates the URL the same way
 * deprecated/components.js TableManager did (pushState).
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
});
