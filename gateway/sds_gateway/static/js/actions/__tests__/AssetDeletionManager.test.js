/**
 * Jest tests for AssetDeletionManager
 */

import { AssetDeletionManager } from "../AssetDeletionManager.js"

function installDeleteModalDom() {
    document.body.innerHTML = `
		<div id="deleteAssetModal">
			<span id="delete-asset-title-deletable"></span>
			<span id="delete-asset-title-shared" class="d-none"></span>
			<span id="delete-asset-type-label"></span>
			<span id="delete-asset-type-label-shared"></span>
			<div id="delete-asset-body-deletable">
				<strong id="delete-asset-name"></strong>
				<div id="delete-asset-message" class="d-none"></div>
			</div>
			<div id="delete-asset-body-shared" class="d-none">
				<strong id="delete-asset-name-shared"></strong>
			</div>
			<button id="delete-asset-confirm-btn"></button>
		</div>
	`
}

describe("AssetDeletionManager", () => {
    beforeEach(() => {
        installDeleteModalDom()
        window.DOMUtils = { toggleHidden: jest.fn() }
        window.APIClient = { delete: jest.fn().mockResolvedValue("") }
        window.bootstrap = {
            Modal: jest.fn(() => ({ show: jest.fn(), hide: jest.fn() })),
        }
    })

    test("buildDeleteUrl for capture and dataset", () => {
        const mgr = new AssetDeletionManager()
        expect(mgr.buildDeleteUrl("capture", "abc")).toBe(
            "/api/v1/assets/captures/abc/",
        )
        expect(mgr.buildDeleteUrl("dataset", "def")).toBe(
            "/api/v1/assets/datasets/def/",
        )
    })

    test("confirmDeletion calls APIClient.delete", async () => {
        const mgr = new AssetDeletionManager()
        mgr.assetType = "capture"
        mgr.assetUuid = "uuid-1"
        mgr.showToast = jest.fn()
        mgr.closeModal = jest.fn()

        await mgr.confirmDeletion()

        expect(window.APIClient.delete).toHaveBeenCalledWith(
            "/api/v1/assets/captures/uuid-1/",
        )
    })

    test("shared capture shows warning and skips delete API", async () => {
        window.bootstrap = {
            Modal: Object.assign(
                jest.fn(() => ({ show: jest.fn(), hide: jest.fn() })),
                {
                    getInstance: jest.fn(() => null),
                },
            ),
        }
        const mgr = new AssetDeletionManager()
        mgr.assetType = "capture"
        mgr.assetUuid = "uuid-2"
        mgr.assetName = "My Capture"
        mgr.assetIsShared = true
        mgr.applySharedState()

        expect(mgr.assetIsShared).toBe(true)
        expect(window.DOMUtils.toggleHidden).toHaveBeenCalledWith(
            mgr.confirmBtn,
            true,
        )

        await mgr.confirmDeletion()
        expect(window.APIClient.delete).not.toHaveBeenCalled()
    })
})
