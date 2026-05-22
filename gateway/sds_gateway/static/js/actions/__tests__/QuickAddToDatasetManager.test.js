/**
 * Jest tests for QuickAddToDatasetManager
 */

import { QuickAddToDatasetManager } from "../QuickAddToDatasetManager.js";

function installQuickAddModalDom() {
	document.body.innerHTML = `
		<div id="quickAddToDatasetModal"
			data-quick-add-url="/users/quick-add/"
			data-datasets-url="/users/datasets-for-quick-add/">
			<select id="quick-add-dataset-select"></select>
			<button id="quick-add-confirm-btn"></button>
			<div id="quick-add-message" class="d-none"></div>
			<span id="quick-add-capture-name"></span>
		</div>
	`;
}

describe("QuickAddToDatasetManager", () => {
	beforeEach(() => {
		jest.clearAllMocks();
		installQuickAddModalDom();
		window.DOMUtils = {
			show: jest.fn(),
			showMessage: jest.fn().mockResolvedValue(true),
		};
		window.APIClient = {
			get: jest.fn(),
			post: jest.fn(),
		};
		window.QuickAddApi = {
			formatQuickAddSummary: jest.fn(() => "2 added."),
			postQuickAddCapture: jest.fn(),
			postQuickAddCaptures: jest.fn(),
		};
	});

	test("loadDatasets populates select from API", async () => {
		window.APIClient.get.mockResolvedValue({
			datasets: [
				{ uuid: "ds-1", name: "Dataset One" },
				{ uuid: "ds-2", name: "Dataset Two" },
			],
		});

		const mgr = new QuickAddToDatasetManager();
		await mgr.loadDatasets();

		const select = document.getElementById("quick-add-dataset-select");
		expect(select.options.length).toBe(3);
		expect(select.options[1].value).toBe("ds-1");
		expect(mgr.confirmBtn.disabled).toBe(true);
	});

	test("handleSingleAdd closes with toast on success", async () => {
		window.QuickAddApi.postQuickAddCapture.mockResolvedValue({
			success: true,
			added: 1,
			skipped: 0,
			errors: [],
		});

		const mgr = new QuickAddToDatasetManager();
		mgr.currentCaptureUuid = "cap-1";
		mgr.selectEl.value = "ds-1";
		mgr.showToast = jest.fn();
		mgr.closeModal = jest.fn();
		mgr.modalEl = document.getElementById("quickAddToDatasetModal");

		await mgr.handleSingleAdd("ds-1");

		expect(window.QuickAddApi.postQuickAddCapture).toHaveBeenCalledWith(
			"/users/quick-add/",
			"ds-1",
			"cap-1",
		);
		expect(mgr.closeModal).toHaveBeenCalled();
	});

	test("handleAdd shows warning when no capture selected", async () => {
		const mgr = new QuickAddToDatasetManager();
		const opt = document.createElement("option");
		opt.value = "ds-1";
		mgr.selectEl.appendChild(opt);
		mgr.selectEl.value = "ds-1";
		mgr.showInlineMessage = jest.fn();

		await mgr.handleAdd();

		expect(mgr.showInlineMessage).toHaveBeenCalledWith(
			expect.stringContaining("Select at least one capture"),
			"warning",
		);
	});
});
