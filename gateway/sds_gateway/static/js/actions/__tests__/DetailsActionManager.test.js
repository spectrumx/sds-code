/**
 * Jest tests for DetailsActionManager
 */

import { DetailsActionManager } from "../DetailsActionManager.js"

describe("DetailsActionManager", () => {
    beforeEach(() => {
        jest.clearAllMocks()
        global.window.DOMUtils = {
            renderContent: jest.fn().mockResolvedValue(true),
        }
        global.window.bootstrap = {
            Tooltip: jest.fn(function MockTooltip() {
                this.dispose = jest.fn()
            }),
        }
        global.window.bootstrap.Tooltip.getInstance = jest.fn(() => null)
        global.navigator.clipboard = {
            writeText: jest.fn().mockResolvedValue(undefined),
        }
    })

    test("attachUuidCopyButton wires click handler", () => {
        const btn = document.createElement("button")
        btn.className = "copy-uuid-btn"
        const modal = document.createElement("div")
        modal.appendChild(btn)
        document.body.appendChild(modal)

        DetailsActionManager.attachUuidCopyButton(modal, "u1")
        modal.querySelector(".copy-uuid-btn").click()
        expect(global.navigator.clipboard.writeText).toHaveBeenCalledWith("u1")

        document.body.removeChild(modal)
    })
})
