/**
 * Jest tests for ModalManager
 */

import { ModalManager } from "../ModalManager.js"
const { createMockDOMUtils } = require("../../tests-config/testHelpers.js")
const {
    installBootstrapModalMocks,
} = require("../../__tests__/helpers/actionTestMocks.js")

describe("ModalManager", () => {
    beforeEach(() => {
        jest.clearAllMocks()
        document.body.innerHTML = ""
        installBootstrapModalMocks()
        window.DOMUtils = createMockDOMUtils({
            renderLoading: jest.fn().mockResolvedValue(undefined),
        })
    })

    test("getOrCreateBootstrapModal creates instance when missing", () => {
        const el = document.createElement("div")
        document.body.appendChild(el)
        global.bootstrap.Modal.getInstance = jest.fn(() => null)

        const inst = ModalManager.getOrCreateBootstrapModal(el)

        expect(global.bootstrap.Modal).toHaveBeenCalledWith(el, {})
        expect(inst.show).toEqual(expect.any(Function))
    })

    test("showModalLoading renders loading into modal body", async () => {
        document.body.innerHTML = `
			<div id="test-modal"><div class="modal-body"></div></div>
		`

        await ModalManager.showModalLoading("test-modal", "Please wait")

        expect(window.DOMUtils.renderLoading).toHaveBeenCalledWith(
            document.querySelector("#test-modal .modal-body"),
            "Please wait",
            { format: "modal" },
        )
    })

    test("closeModal hides bootstrap instance", () => {
        const hide = jest.fn()
        const el = document.createElement("div")
        el.id = "m1"
        document.body.appendChild(el)
        global.bootstrap.Modal.getInstance = jest.fn(() => ({ hide }))

        new ModalManager().closeModal("m1")

        expect(global.bootstrap.Modal.getInstance).toHaveBeenCalledWith(el)
        expect(hide).toHaveBeenCalled()
    })

    test("openModal shows bootstrap modal and runs download prepare on shown", () => {
        const prepareWebDownloadModal = jest.fn()
        window.downloadActionManager = { prepareWebDownloadModal }
        const modal = document.createElement("div")
        modal.id = "webDownloadModal-abc"
        document.body.appendChild(modal)
        const trigger = document.createElement("button")
        const show = jest.fn()
        global.bootstrap.Modal.getInstance = jest.fn(() => ({ show }))

        new ModalManager().openModal("webDownloadModal-abc", { trigger })

        expect(show).toHaveBeenCalled()
        modal.dispatchEvent(new Event("shown.bs.modal"))
        expect(prepareWebDownloadModal).toHaveBeenCalledWith(modal, trigger)
    })

    test("showModalLoading no-ops when modal missing", async () => {
        await ModalManager.showModalLoading("missing-modal")
        expect(window.DOMUtils.renderLoading).not.toHaveBeenCalled()
    })

    test("initializeModal registers details click delegation cleanup", () => {
        const detach = jest.fn()
        window.AssetDetailsModalLoader = {
            ensureDetailsClickDelegation: jest.fn(() => detach),
        }
        const cleanup = ModalManager.initializeModal({
            bootstrap: false,
            detailsClickDelegation: true,
        })
        cleanup()
        expect(detach).toHaveBeenCalled()
    })

    test("initializeModal attaches share and versioning managers to dataset list modals", () => {
        const managersOut = []
        const datasetUuid = "11111111-1111-4111-8111-111111111111"
        document.body.innerHTML = `
			<div class="modal" data-item-type="dataset" data-item-uuid="${datasetUuid}"></div>
		`
        const modalEl = document.querySelector(".modal")
        window.PermissionsManager = jest.fn().mockImplementation(() => ({}))
        const shareInstance = { itemUuid: datasetUuid }
        const versionInstance = { datasetUuid }
        window.ShareActionManager = jest.fn(() => shareInstance)
        window.VersioningActionManager = jest.fn(() => versionInstance)

        ModalManager.initializeModal({
            bootstrap: false,
            wireListModals: "dataset",
            permissions: {},
            managersOut,
        })

        expect(modalEl.shareActionManager).toBe(shareInstance)
        expect(modalEl.versioningActionManager).toBe(versionInstance)
        expect(window.ShareActionManager).toHaveBeenCalledWith({
            itemUuid: datasetUuid,
            itemType: "dataset",
            permissions: expect.any(Object),
        })
    })

    test("_wireWebDownloadModalTriggers prevents default on matching toggle", () => {
        const openWebDownloadFromToggle = jest.fn()
        const root = document.createElement("div")
        const toggle = document.createElement("a")
        toggle.setAttribute("data-bs-toggle", "modal")
        toggle.setAttribute("data-bs-target", "#webDownloadModal-x")
        root.appendChild(toggle)
        document.body.appendChild(root)

        const cleanup = ModalManager._wireWebDownloadModalTriggers(root, {
            openWebDownloadFromToggle,
        })
        const event = new MouseEvent("click", {
            bubbles: true,
            cancelable: true,
        })
        toggle.dispatchEvent(event)

        expect(event.defaultPrevented).toBe(true)
        expect(openWebDownloadFromToggle).toHaveBeenCalledWith(toggle)
        cleanup()
    })
})
