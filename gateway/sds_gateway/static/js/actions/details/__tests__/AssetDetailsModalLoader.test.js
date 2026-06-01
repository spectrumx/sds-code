/**
 * Jest tests for AssetDetailsModalLoader
 */

import { AssetDetailsModalLoader } from "../AssetDetailsModalLoader.js"
const {
    createMockFetchResponse,
} = require("../../../tests-config/testHelpers.js")

describe("AssetDetailsModalLoader", () => {
    beforeEach(() => {
        jest.clearAllMocks()
        document.body.innerHTML = ""
        window.DetailsModalAssetRegistry = undefined
    })

    describe("findDelegateTarget", () => {
        test("returns element when it matches selector", () => {
            const el = document.createElement("button")
            el.className = "details-trigger"
            expect(
                AssetDetailsModalLoader.findDelegateTarget(el, [
                    ".details-trigger",
                ]),
            ).toBe(el)
        })

        test("returns closest ancestor match", () => {
            const parent = document.createElement("a")
            parent.className = "capture-link"
            const child = document.createElement("span")
            parent.appendChild(child)
            expect(
                AssetDetailsModalLoader.findDelegateTarget(child, [
                    ".capture-link",
                ]),
            ).toBe(parent)
        })

        test("returns null when no match", () => {
            const el = document.createElement("div")
            expect(
                AssetDetailsModalLoader.findDelegateTarget(el, [".missing"]),
            ).toBeNull()
        })
    })

    describe("resolveDetailsModalFromTrigger", () => {
        test("returns cfg and target from registry", () => {
            const trigger = document.createElement("button")
            trigger.dataset.uuid = "cap-1"
            trigger.className = "open-capture-details"
            window.DetailsModalAssetRegistry = {
                capture: {
                    delegateClickSelectors: [".open-capture-details"],
                    resolveUuidFromTrigger: (t) => t.dataset.uuid,
                },
            }

            const resolved =
                AssetDetailsModalLoader.resolveDetailsModalFromTrigger(trigger)

            expect(resolved?.target).toBe(trigger)
            expect(resolved?.cfg.delegateClickSelectors).toContain(
                ".open-capture-details",
            )
        })
    })

    describe("openDetailsFromTrigger", () => {
        test("fetches details and calls afterInject on success", async () => {
            const modal = document.createElement("div")
            const bodyEl = document.createElement("div")
            const titleEl = document.createElement("h5")
            const trigger = document.createElement("button")
            trigger.dataset.uuid = "cap-1"
            trigger.className = "open-details"

            const afterInject = jest.fn()
            const show = jest.fn()
            window.ModalManager = {
                getOrCreateBootstrapModal: () => ({ show }),
            }
            window.DetailsModalAssetRegistry = {
                capture: {
                    assetType: "capture",
                    delegateClickSelectors: [".open-details"],
                    resolveUuidFromTrigger: (t) => t.dataset.uuid,
                    resolveShell: () => ({ modal, bodyEl, titleEl }),
                    buildDetailsUrl: (uuid) => `/details/${uuid}/`,
                    afterInject,
                },
            }

            global.fetch = jest.fn().mockResolvedValue(
                createMockFetchResponse({
                    jsonData: {
                        title: "Capture A",
                        html: "<p>body</p>",
                        meta: { uuid: "cap-1" },
                    },
                }),
            )

            await AssetDetailsModalLoader.openDetailsFromTrigger(trigger)

            expect(fetch).toHaveBeenCalledWith(
                "/details/cap-1/",
                expect.objectContaining({
                    credentials: "same-origin",
                    headers: { Accept: "application/json" },
                }),
            )
            expect(titleEl.textContent).toBe("Capture A")
            expect(bodyEl.innerHTML).toBe("<p>body</p>")
            expect(show).toHaveBeenCalled()
            expect(afterInject).toHaveBeenCalledWith(
                expect.objectContaining({ uuid: "cap-1" }),
            )
        })

        test("shows error body when fetch fails", async () => {
            const modal = document.createElement("div")
            const bodyEl = document.createElement("div")
            const titleEl = document.createElement("h5")
            const trigger = document.createElement("button")
            trigger.dataset.uuid = "ds-1"
            trigger.className = "open-details"

            window.ModalManager = {
                getOrCreateBootstrapModal: () => ({ show: jest.fn() }),
            }
            window.DetailsModalAssetRegistry = {
                dataset: {
                    assetType: "dataset",
                    delegateClickSelectors: [".open-details"],
                    resolveUuidFromTrigger: (t) => t.dataset.uuid,
                    resolveShell: () => ({ modal, bodyEl, titleEl }),
                    buildDetailsUrl: () => "/details/",
                },
            }

            global.fetch = jest
                .fn()
                .mockResolvedValue({ ok: false, status: 500 })

            await AssetDetailsModalLoader.openDetailsFromTrigger(trigger)

            expect(bodyEl.innerHTML).toContain("dataset details")
            expect(titleEl.textContent).toBe("Error")
        })
    })

    describe("ensureDetailsClickDelegation", () => {
        test("wires click once and cleanup removes listener", () => {
            document.body.innerHTML = "<div></div>"
            const cleanup =
                AssetDetailsModalLoader.ensureDetailsClickDelegation()
            expect(document.body.dataset.detailsAssetClickWired).toBe("1")

            const cleanup2 =
                AssetDetailsModalLoader.ensureDetailsClickDelegation()
            expect(cleanup2).toEqual(expect.any(Function))

            cleanup()
            expect(document.body.dataset.detailsAssetClickWired).toBe("")
        })

        test("ignores clicks inside dropdown toggles", () => {
            document.body.innerHTML = `
				<button class="open-details" data-uuid="x" data-bs-toggle="dropdown"></button>
			`
            const openSpy = jest
                .spyOn(AssetDetailsModalLoader, "openDetailsFromTrigger")
                .mockResolvedValue(undefined)
            window.DetailsModalAssetRegistry = {
                capture: {
                    delegateClickSelectors: [".open-details"],
                    resolveUuidFromTrigger: () => "x",
                },
            }
            const cleanup =
                AssetDetailsModalLoader.attachDocumentDetailsClickDelegation()
            document.querySelector(".open-details").click()
            expect(openSpy).not.toHaveBeenCalled()
            cleanup()
            openSpy.mockRestore()
        })

        test("delegated capture click prevents default and opens details", async () => {
            const link = document.createElement("a")
            link.className = "capture-link open-details"
            link.setAttribute("data-item-uuid", "cap-delegated")
            link.textContent = "Link"
            document.body.appendChild(link)
            const openSpy = jest
                .spyOn(AssetDetailsModalLoader, "openDetailsFromTrigger")
                .mockResolvedValue(undefined)
            window.DetailsModalAssetRegistry = {
                capture: {
                    delegateClickSelectors: [".capture-link", ".open-details"],
                    resolveUuidFromTrigger: (el) =>
                        el.getAttribute("data-item-uuid"),
                },
            }
            const cleanup =
                AssetDetailsModalLoader.attachDocumentDetailsClickDelegation()
            const event = new MouseEvent("click", {
                bubbles: true,
                cancelable: true,
            })
            link.dispatchEvent(event)
            expect(event.defaultPrevented).toBe(true)
            expect(openSpy).toHaveBeenCalledWith(link)
            cleanup()
            openSpy.mockRestore()
        })
    })

    describe("openDetailsFromTrigger edge cases", () => {
        test("skips fetch when uuid is invalid", async () => {
            global.fetch = jest.fn()
            const trigger = document.createElement("button")
            trigger.className = "open-details"
            trigger.dataset.uuid = "null"
            window.DetailsModalAssetRegistry = {
                capture: {
                    assetType: "capture",
                    delegateClickSelectors: [".open-details"],
                    resolveUuidFromTrigger: (t) => t.dataset.uuid,
                    resolveShell: () => ({
                        modal: document.createElement("div"),
                        bodyEl: document.createElement("div"),
                        titleEl: document.createElement("h5"),
                    }),
                    buildDetailsUrl: () => "/x/",
                },
            }
            await AssetDetailsModalLoader.openDetailsFromTrigger(trigger)
            expect(fetch).not.toHaveBeenCalled()
        })

        test("skips fetch when shell is missing", async () => {
            global.fetch = jest.fn()
            const trigger = document.createElement("button")
            trigger.className = "open-details"
            window.DetailsModalAssetRegistry = {
                capture: {
                    assetType: "capture",
                    delegateClickSelectors: [".open-details"],
                    resolveUuidFromTrigger: () => "valid-uuid",
                    resolveShell: () => null,
                    buildDetailsUrl: () => "/x/",
                },
            }
            await AssetDetailsModalLoader.openDetailsFromTrigger(trigger)
            expect(fetch).not.toHaveBeenCalled()
        })

        test("hides visualize button while loading capture", async () => {
            document.body.innerHTML = '<button id="visualize-btn"></button>'
            const visualizeBtn = document.getElementById("visualize-btn")
            const modal = document.createElement("div")
            const bodyEl = document.createElement("div")
            const titleEl = document.createElement("h5")
            const trigger = document.createElement("button")
            trigger.className = "open-details"
            window.ModalManager = {
                getOrCreateBootstrapModal: () => ({ show: jest.fn() }),
            }
            window.DetailsModalAssetRegistry = {
                capture: {
                    assetType: "capture",
                    delegateClickSelectors: [".open-details"],
                    resolveUuidFromTrigger: () => "cap-1",
                    resolveShell: () => ({ modal, bodyEl, titleEl }),
                    buildDetailsUrl: () => "/details/",
                },
            }
            let resolveFetch
            global.fetch = jest.fn(
                () =>
                    new Promise((resolve) => {
                        resolveFetch = () =>
                            resolve({
                                ok: true,
                                json: () =>
                                    Promise.resolve({
                                        title: "T",
                                        html: "",
                                        meta: {},
                                    }),
                            })
                    }),
            )
            const pending =
                AssetDetailsModalLoader.openDetailsFromTrigger(trigger)
            expect(visualizeBtn.classList.contains("d-none")).toBe(true)
            resolveFetch()
            await pending
        })
    })
})
