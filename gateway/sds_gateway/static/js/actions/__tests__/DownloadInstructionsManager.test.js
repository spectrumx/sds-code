/**
 * Jest tests for DownloadInstructionsManager
 */

import { DownloadInstructionsManager } from "../DownloadInstructionsManager.js"

describe("DownloadInstructionsManager", () => {
    beforeEach(() => {
        jest.clearAllMocks()
        jest.useFakeTimers()
        global.window.UserInputController = {
            execCommandCopyFallback: jest.fn(),
        }
    })

    afterEach(() => {
        jest.useRealTimers()
    })

    test("copy button uses clipboard API and shows success state", async () => {
        document.body.innerHTML = `
			<button class="copy-btn" data-clipboard-target="#code-block"></button>
			<pre id="code-block">curl example</pre>
		`
        const btn = document.querySelector(".copy-btn")
        Object.assign(navigator, {
            clipboard: { writeText: jest.fn().mockResolvedValue(undefined) },
        })
        Object.defineProperty(window, "isSecureContext", {
            value: true,
            configurable: true,
        })

        new DownloadInstructionsManager()
        btn.click()

        await Promise.resolve()

        expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
            "curl example",
        )
        expect(btn.classList.contains("copied")).toBe(true)
        expect(btn.innerHTML).toContain("Copied")

        jest.advanceTimersByTime(2000)
        expect(btn.classList.contains("copied")).toBe(false)
    })

    test("falls back when clipboard write fails", async () => {
        document.body.innerHTML = `
			<button class="copy-btn" data-clipboard-target="#code-block"></button>
			<pre id="code-block">text</pre>
		`
        const btn = document.querySelector(".copy-btn")
        Object.assign(navigator, {
            clipboard: {
                writeText: jest.fn().mockRejectedValue(new Error("denied")),
            },
        })
        Object.defineProperty(window, "isSecureContext", {
            value: true,
            configurable: true,
        })

        new DownloadInstructionsManager()
        btn.click()
        await Promise.resolve()
        await Promise.resolve()

        expect(
            window.UserInputController.execCommandCopyFallback,
        ).toHaveBeenCalledWith("text")
    })
})
