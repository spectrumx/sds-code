/**
 * Jest tests for ListRefreshManager (AJAX list + modals refresh)
 */

import { ListRefreshManager } from "../APIClient.js";
const {
	createListRefreshResponseHtml,
	installListRefreshDomContainers,
	LIST_REFRESH_SEP,
} = require("../../__tests__/helpers/actionTestMocks.js");

describe("ListRefreshManager", () => {
	let tableEl;
	let modalsEl;
	let loadTable;
	let refreshMock;

	beforeEach(() => {
		jest.clearAllMocks();
		const dom = installListRefreshDomContainers();
		tableEl = dom.table;
		modalsEl = dom.modals;

		global.window.APIClient = {
			get: jest.fn(),
		};
		global.window.DOMUtils = {
			renderLoading: jest.fn().mockResolvedValue(undefined),
			showMessage: jest.fn().mockResolvedValue(true),
			initIconDropdowns: jest.fn(),
		};
		global.window.ModalManager = {
			initializeModal: jest.fn(),
		};
		refreshMock = jest.fn().mockResolvedValue(undefined);
		global.window.pageLifecycleManager = { refresh: refreshMock };

		global.bootstrap = {
			Dropdown: {},
			Tooltip: jest.fn(),
		};
		global.bootstrap.Tooltip.getInstance = jest.fn(() => null);

		loadTable = new ListRefreshManager({
			containerSelector: dom.tableSelector,
			modalsContainerSelector: dom.modalsSelector,
			url: "/users/dataset-list/",
			itemType: "dataset",
		});
	});

	test("loadTable splits response and updates table and modals containers", async () => {
		const sharedEmail = "newshare@example.com";
		const modalsHtml = `<div id="shareModal-ds-1" data-item-uuid="ds-1">
			<div id="users-with-access-section-ds-1">
				<table><tbody><tr><td><small class="text-muted">${sharedEmail}</small></td></tr></tbody></table>
			</div>
			<div id="versioningModal-new-version-uuid"></div>
			<div id="publish-dataset-modal-new-version-uuid"></div>
		</div>`;
		const tableHtml =
			'<div data-dataset-uuid="new-version-uuid"><i class="bi bi-people-fill text-success"></i></div>';
		global.window.APIClient.get.mockResolvedValue(
			createListRefreshResponseHtml({ tableHtml, modalsHtml }),
		);

		await loadTable.loadTable({}, { showLoading: false });

		expect(tableEl.innerHTML).toBe(tableHtml);
		expect(modalsEl.innerHTML).toBe(modalsHtml);
		expect(modalsEl.innerHTML).toContain(sharedEmail);
		expect(modalsEl.querySelector("#versioningModal-new-version-uuid")).not.toBeNull();
		expect(
			modalsEl.querySelector("#publish-dataset-modal-new-version-uuid"),
		).not.toBeNull();
		expect(refreshMock).toHaveBeenCalled();
		expect(global.window.ModalManager.initializeModal).toHaveBeenCalledWith(
			expect.objectContaining({ bootstrap: true, root: document }),
		);
	});

	test("loadTable calls pageLifecycleManager.refresh after DOM update", async () => {
		global.window.APIClient.get.mockResolvedValue(
			createListRefreshResponseHtml({
				tableHtml: "<div>rows</div>",
				modalsHtml: "<div id='shareModal-x'></div>",
			}),
		);

		await loadTable.loadTable({}, { showLoading: false });

		expect(refreshMock).toHaveBeenCalledTimes(1);
	});

	test("uses LIST_REFRESH_SEP constant in split logic", () => {
		expect(LIST_REFRESH_SEP).toBe("<!-- LIST_REFRESH_SEP -->");
	});
});
