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

describe("captures/CapturesTableManager.js — getCSRFToken (same contract)", () => {
	let savedAPIClient;

	beforeAll(() => {
		savedAPIClient = window.APIClient;
	});

	beforeEach(() => {
		window.APIClient = savedAPIClient;
		mountCaptureTablePage();
		jest.resetModules();
		// eslint-disable-next-line global-require
		require("../../core/TableManager.js");
		// eslint-disable-next-line global-require
		require("../../core/ComponentUtils.js");
	});

	afterEach(() => {
		window.APIClient = savedAPIClient;
		document.body.innerHTML = "";
	});

	test("returns token from new APIClient().getCSRFToken()", () => {
		// eslint-disable-next-line global-require
		const { CapturesTableManager } = require("../CapturesTableManager.js");
		const mgr = new CapturesTableManager(baseConfig());
		expect(mgr.getCSRFToken()).toBe("mock-csrf-token");
	});

	test("falls back to csrfmiddlewaretoken input when APIClient is absent", () => {
		window.APIClient = undefined;
		const input = document.createElement("input");
		input.setAttribute("name", "csrfmiddlewaretoken");
		input.value = "from-input-core";
		document.body.appendChild(input);
		// eslint-disable-next-line global-require
		const { CapturesTableManager } = require("../CapturesTableManager.js");
		const mgr = new CapturesTableManager(baseConfig());
		expect(mgr.getCSRFToken()).toBe("from-input-core");
	});
});
