/**
 * @jest-environment jsdom
 */

const { CaptureUploadController } = require("../CaptureUploadController.js")

describe("CaptureUploadController", () => {
    let controller

    beforeEach(() => {
        window.APIClient = { getCSRFToken: () => "csrf-test" }
        controller = new CaptureUploadController()
        controller.filesToSkip = new Set()
    })

    test("setSelectedFiles and getSelectedFiles round-trip", () => {
        const file = new File(["a"], "a.txt", { type: "text/plain" })
        controller.setSelectedFiles([file])
        expect(controller.getSelectedFiles()).toHaveLength(1)
        expect(controller.getSelectedFiles()[0].name).toBe("a.txt")
    })

    test("resetSession clears selection and duplicate-check state", () => {
        controller.setSelectedFiles([new File(["a"], "a.txt")])
        controller.filesToSkip = new Set(["/x"])
        controller.fileCheckResults = new Map([["k", {}]])
        controller.resetSession()
        expect(controller.getSelectedFiles()).toHaveLength(0)
        expect(controller.filesToSkip).toBeNull()
        expect(controller.fileCheckResults).toBeNull()
    })

    test("partitionFilesForUpload skips entries in filesToSkip", () => {
        const file = new File(["data"], "nested.txt", { type: "text/plain" })
        Object.defineProperty(file, "webkitRelativePath", {
            value: "mydir/nested.txt",
            configurable: true,
        })
        controller.filesToSkip = new Set(["/mydir/nested.txt"])
        const result = controller.partitionFilesForUpload([file])
        expect(result.filesToUpload).toHaveLength(0)
        expect(result.skippedFilesCount).toBe(1)
        expect(result.allRelativePaths).toEqual(["mydir/nested.txt"])
    })

    test("checkForLargeFiles blocks when file exceeds threshold", () => {
        global.alert = jest.fn()
        const huge = new File(["x"], "big.bin")
        Object.defineProperty(huge, "size", {
            value: 600 * 1024 * 1024,
            configurable: true,
        })
        const blocked = controller.checkForLargeFiles([huge], null, null)
        expect(blocked).toBe(true)
        expect(global.alert).toHaveBeenCalled()
    })

    test("checkForLargeFiles allows small files", () => {
        global.alert = jest.fn()
        const small = new File(["x"], "small.bin")
        Object.defineProperty(small, "size", {
            value: 1024,
            configurable: true,
        })
        expect(controller.checkForLargeFiles([small], null, null)).toBe(false)
        expect(global.alert).not.toHaveBeenCalled()
    })
})
