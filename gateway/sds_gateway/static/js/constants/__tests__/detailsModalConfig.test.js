/**
 * Jest tests for detailsModalConfig registry
 */

require("../detailsModalConfig.js")

describe("detailsModalConfig", () => {
    beforeEach(() => {
        jest.clearAllMocks()
        document.body.innerHTML = `
			<div id="asset-details-modal">
				<h5 id="asset-details-modal-label"></h5>
				<div id="asset-details-modal-body"></div>
			</div>
		`
    })

    const registry = () => window.DetailsModalAssetRegistry

    test("capture buildDetailsUrl uses users details-modal path", () => {
        expect(registry().capture.buildDetailsUrl("abc-def")).toBe(
            "/users/details-modal/capture/abc-def/",
        )
    })

    test("dataset buildDetailsUrl uses users details-modal path", () => {
        expect(registry().dataset.buildDetailsUrl("ds-1")).toBe(
            "/users/details-modal/dataset/ds-1/",
        )
    })

    test("capture resolveUuidFromTrigger prefers data-item-uuid", () => {
        const el = document.createElement("button")
        el.setAttribute("data-item-uuid", "item")
        el.setAttribute("data-capture-uuid", "cap")
        el.setAttribute("data-uuid", "plain")
        expect(registry().capture.resolveUuidFromTrigger(el)).toBe("item")
    })

    test("dataset resolveUuidFromTrigger reads row data-dataset-uuid", () => {
        document.body.innerHTML = `
			<div id="asset-details-modal">
				<div id="asset-details-modal-body"></div>
			</div>
			<div class="dataset-details-open" data-dataset-uuid="row-uuid">
				<button class="inner"></button>
			</div>
		`
        const btn = document.querySelector(".inner")
        expect(registry().dataset.resolveUuidFromTrigger(btn)).toBe("row-uuid")
    })

    test("capture resolveShell returns modal body and title elements", () => {
        const shell = registry().capture.resolveShell()
        expect(shell.modal.id).toBe("asset-details-modal")
        expect(shell.bodyEl.id).toBe("asset-details-modal-body")
        expect(shell.titleEl.id).toBe("asset-details-modal-label")
    })

    test("capture afterInject calls CaptureDetailsModalBehavior when present", () => {
        const afterInject = jest.fn()
        window.CaptureDetailsModalBehavior = { afterInject }
        const modal = document.getElementById("asset-details-modal")
        registry().capture.afterInject({ modal, meta: { uuid: "c1" } })
        expect(afterInject).toHaveBeenCalledWith(
            expect.objectContaining({ modal, meta: { uuid: "c1" } }),
        )
    })

    test("dataset afterInject wires uuid copy on modal", () => {
        const attachUuidCopyButton = jest.fn()
        window.DetailsActionManager = { attachUuidCopyButton }
        const modal = document.getElementById("asset-details-modal")
        registry().dataset.afterInject({
            modal,
            meta: { uuid: "d-99" },
        })
        expect(attachUuidCopyButton).toHaveBeenCalledWith(modal, "d-99")
    })
})
