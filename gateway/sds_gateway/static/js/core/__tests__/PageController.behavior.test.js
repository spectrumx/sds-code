/**
 * PageController: tracked listeners are removed after destroy (no double-fires).
 */
const { JSDOM } = require("jsdom");
const { PageController } = require("../PageController.js");

class RecordingPage extends PageController {
	constructor(el) {
		super();
		this.el = el;
		this.hits = 0;
	}

	initializeEventHandlers() {
		this.bind(this.el, "click", () => {
			this.hits += 1;
		});
	}
}

describe("PageController behavior", () => {
	let initialWindow;
	let initialDocument;

	beforeAll(() => {
		initialWindow = global.window;
		initialDocument = global.document;
		const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>");
		global.window = dom.window;
		global.document = dom.window.document;
	});

	afterAll(() => {
		global.window = initialWindow;
		global.document = initialDocument;
	});

	test("init wires handler once; destroy removes it", () => {
		const el = document.createElement("button");
		document.body.appendChild(el);

		const page = new RecordingPage(el);
		page.init();
		el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
		expect(page.hits).toBe(1);

		page.destroy();
		el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
		expect(page.hits).toBe(1);
	});

	test("init is idempotent — second init does not stack duplicate handlers", () => {
		const el = document.createElement("button");
		document.body.appendChild(el);

		const page = new RecordingPage(el);
		page.init();
		page.init();
		el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
		expect(page.hits).toBe(1);
	});
});
