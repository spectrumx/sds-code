/**
 * @jest-environment jsdom
 */

const {
	UploadCaptureModalController,
} = require("../UploadCaptureModalController.js");

describe("UploadCaptureModalController — getCSRFToken", () => {
	test("prefers new APIClient().getCSRFToken()", () => {
		const ctrl = new UploadCaptureModalController({});
		expect(ctrl.getCSRFToken()).toBe("mock-csrf-token");
	});

	test("falls back to hidden csrf input when APIClient throws", () => {
		const orig = global.window.APIClient;
		global.window.APIClient = class Bad {
			getCSRFToken() {
				throw new Error("fail");
			}
		};
		document.body.innerHTML =
			'<input type="hidden" name="csrfmiddlewaretoken" value="from-input" />';
		const ctrl = new UploadCaptureModalController({});
		expect(ctrl.getCSRFToken()).toBe("from-input");
		global.window.APIClient = orig;
	});
});
