/**
 * Jest tests for AssetDeletionManager
 */

import { AssetDeletionManager } from "../AssetDeletionManager.js";

function installDeleteModalDom() {
	document.body.innerHTML = `
		<div id="deleteAssetModal">
			<span id="delete-asset-type-label"></span>
			<strong id="delete-asset-name"></strong>
			<div id="delete-asset-message" class="d-none"></div>
			<button id="delete-asset-confirm-btn"></button>
		</div>
	`;
}

describe("AssetDeletionManager", () => {
	beforeEach(() => {
		installDeleteModalDom();
		window.DOMUtils = { toggleHidden: jest.fn() };
		window.APIClient = { delete: jest.fn().mockResolvedValue("") };
		window.bootstrap = {
			Modal: jest.fn(() => ({ show: jest.fn(), hide: jest.fn() })),
		};
	});

	test("buildDeleteUrl for capture and dataset", () => {
		const mgr = new AssetDeletionManager();
		expect(mgr.buildDeleteUrl("capture", "abc")).toBe(
			"/api/v1/assets/captures/abc/",
		);
		expect(mgr.buildDeleteUrl("dataset", "def")).toBe(
			"/api/v1/assets/datasets/def/",
		);
	});

	test("confirmDeletion calls APIClient.delete", async () => {
		const mgr = new AssetDeletionManager();
		mgr.assetType = "capture";
		mgr.assetUuid = "uuid-1";
		mgr.showToast = jest.fn();
		mgr.closeModal = jest.fn();

		await mgr.confirmDeletion();

		expect(window.APIClient.delete).toHaveBeenCalledWith(
			"/api/v1/assets/captures/uuid-1/",
		);
	});
});
