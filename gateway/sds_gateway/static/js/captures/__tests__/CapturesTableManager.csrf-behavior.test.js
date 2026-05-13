/**
 * getCSRFToken: prefers APIClient instance, then hidden input (deprecated vs core parity).
 */
const TABLE_BODY = `
  <table id="ctm-table"><tbody></tbody></table>
  <div id="ctm-load"></div><div id="ctm-pag"></div>
`;

function mountCaptureTablePage() {
	document.body.innerHTML = TABLE_BODY;
}

function baseConfig() {
	return {
		tableId: "ctm-table",
		loadingIndicatorId: "ctm-load",
		paginationContainerId: "ctm-pag",
		modalHandler: { openCaptureModal: jest.fn() },
	};
}

describe("deprecated components.js CapturesTableManager — getCSRFToken", () => {
	let DeprecatedCapturesTableManager;
	let savedAPIClient;

	beforeAll(() => {
		savedAPIClient = window.APIClient;
		// eslint-disable-next-line global-require
		({ CapturesTableManager: DeprecatedCapturesTableManager } = require("../../deprecated/components.js"));
	});

	beforeEach(() => {
		window.APIClient = savedAPIClient;
		mountCaptureTablePage();
	});

	afterEach(() => {
		window.APIClient = savedAPIClient;
		document.body.innerHTML = "";
	});

	test("returns empty string when no csrfmiddlewaretoken input (legacy path)", () => {
		const mgr = new DeprecatedCapturesTableManager(baseConfig());
		expect(mgr.getCSRFToken()).toBe("");
	});

	test("reads csrfmiddlewaretoken hidden input when present", () => {
		const input = document.createElement("input");
		input.setAttribute("name", "csrfmiddlewaretoken");
		input.value = "from-input";
		document.body.appendChild(input);
		const mgr = new DeprecatedCapturesTableManager(baseConfig());
		expect(mgr.getCSRFToken()).toBe("from-input");
	});
});
