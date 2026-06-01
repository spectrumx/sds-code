/**
 * Jest tests for CaptureDetailsModalBehavior (capture name edit propagation)
 */

import { CaptureDetailsModalBehavior } from "../CaptureDetailsModalBehavior.js"
const { createMockDOMUtils } = require("../../../tests-config/testHelpers.js")

describe("CaptureDetailsModalBehavior", () => {
    beforeEach(() => {
        jest.clearAllMocks()
        document.body.innerHTML = ""
        window.DOMUtils = createMockDOMUtils()
        global.APIClient = jest.fn().mockImplementation(() => ({
            getCSRFToken: () => "csrf-test",
        }))
        global.fetch = jest.fn()
    })

    test("updateCaptureName PATCHes capture with CSRF", async () => {
        global.fetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ name: "Renamed" }),
        })

        const result = await CaptureDetailsModalBehavior.updateCaptureName(
            "cap-uuid-1",
            "Renamed",
        )

        expect(global.fetch).toHaveBeenCalledWith(
            "/api/v1/assets/captures/cap-uuid-1/",
            expect.objectContaining({
                method: "PATCH",
                headers: expect.objectContaining({
                    "X-CSRFToken": "csrf-test",
                }),
                body: JSON.stringify({ name: "Renamed" }),
            }),
        )
        expect(result.name).toBe("Renamed")
    })

    test("updateTableNameDisplay updates capture-link row text", () => {
        document.body.innerHTML = `
			<a class="capture-link" data-uuid="cap-uuid-1" data-name="Old">Old</a>
		`

        CaptureDetailsModalBehavior.updateTableNameDisplay(
            "cap-uuid-1",
            "New Name",
        )

        const link = document.querySelector(
            ".capture-link[data-uuid='cap-uuid-1']",
        )
        expect(link.textContent).toBe("New Name")
        expect(link.dataset.name).toBe("New Name")
        expect(link.getAttribute("aria-label")).toContain("New Name")
    })

    test("setupVisualizeFromMeta wires visualize button when enabled", () => {
        document.body.innerHTML =
            '<button id="visualize-btn" class="d-none"></button>'
        const openWithCaptureData = jest.fn()
        window.visualizationModalInstance = { openWithCaptureData }

        CaptureDetailsModalBehavior.setupVisualizeFromMeta({
            visualize_enabled: true,
            uuid: "cap-2",
            capture_type: "drf",
        })

        const btn = document.getElementById("visualize-btn")
        expect(btn.classList.contains("d-none")).toBe(false)
        expect(btn.dataset.captureUuid).toBe("cap-2")
        btn.onclick()
        expect(openWithCaptureData).toHaveBeenCalledWith("cap-2", "drf")
    })

    test("afterInject enables visualize button when meta allows DRF", () => {
        document.body.innerHTML = `
			<div id="asset-details-modal"><input id="capture-name-input" /></div>
			<button id="visualize-btn" class="d-none"></button>
		`
        window.visualizationModalInstance = {
            openWithCaptureData: jest.fn(),
        }

        CaptureDetailsModalBehavior.afterInject({
            modal: document.getElementById("asset-details-modal"),
            meta: { visualize_enabled: true, uuid: "c1", capture_type: "drf" },
        })

        const btn = document.getElementById("visualize-btn")
        expect(btn.classList.contains("d-none")).toBe(false)
        expect(btn.dataset.captureUuid).toBe("c1")
    })

    test("updateCaptureName throws when response not ok", async () => {
        global.fetch.mockResolvedValue({
            ok: false,
            json: () => Promise.resolve({ detail: "Forbidden" }),
        })

        await expect(
            CaptureDetailsModalBehavior.updateCaptureName("cap-uuid-1", "X"),
        ).rejects.toThrow("Forbidden")
    })
})
