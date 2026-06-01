/**
 * Download Action Manager
 * Handles all download-related actions
 * Temporal slider: {@link initializeCaptureDownloadSlider} in download/captureDownloadSlider.js
 */

class DownloadActionManager extends ModalManager {
    /**
     * Initialize download action manager
     * @param {Object} config - Configuration object
     */
    constructor(config) {
        super()
        this.permissions = config.permissions
        this.initializeEventListeners()
    }

    /**
     * Initialize event listeners
     */
    initializeEventListeners() {
        // Initialize web download modal buttons
        this.initializeWebDownloadButtons()

        // Initialize SDK download modal buttons
        this.initializeSDKDownloadButtons()
    }

    /**
     * List dropdown download (wired by ModalManager._wireWebDownloadModalTriggers).
     * @param {HTMLElement} toggle
     */
    openWebDownloadFromToggle(toggle) {
        const target =
            toggle.getAttribute("data-bs-target") ||
            toggle.getAttribute("href") ||
            ""
        const modalId = target.startsWith("#") ? target.slice(1) : target
        if (!modalId.startsWith("webDownloadModal-")) {
            return
        }
        const itemUuid = modalId.replace("webDownloadModal-", "")
        const modal = document.getElementById(modalId)
        const itemType = modal?.getAttribute("data-item-type") || "dataset"

        if (!this.permissions.canDownload()) {
            this.showToast(
                `You don't have permission to download this ${itemType}`,
                "warning",
            )
            return
        }

        this.openModal(modalId, {
            trigger: toggle,
            downloadActionManager: this,
        })
    }

    /**
     * After ModalManager opens a web download modal (shown.bs.modal).
     * @param {HTMLElement} modal
     * @param {HTMLElement|null} triggerButton
     */
    prepareWebDownloadModal(modal, triggerButton) {
        const itemUuid = modal.id.replace("webDownloadModal-", "")
        const itemType = modal.getAttribute("data-item-type") || "dataset"
        if (itemType === "capture") {
            this.setTemporalSliderAttrs(modal.id, modal, itemUuid)
        }
        this.wireWebDownloadConfirm(modal.id, itemUuid, itemType, triggerButton)
    }

    /**
     * Initialize web download buttons on the table rows
     */
    initializeWebDownloadButtons() {
        const downloadButtons = document.querySelectorAll(".web-download-btn")

        for (const button of downloadButtons) {
            // Prevent duplicate event listener attachment
            if (button.dataset.downloadSetup === "true") {
                continue
            }
            button.dataset.downloadSetup = "true"

            button.addEventListener("click", (e) => {
                e.preventDefault()
                e.stopPropagation()

                const itemUuid = button.getAttribute("data-item-uuid")
                const itemType = button.getAttribute("data-item-type")

                if (!this.permissions.canDownload()) {
                    this.showToast(
                        `You don't have permission to download this ${itemType}`,
                        "warning",
                    )
                    return
                }

                this.initializeWebDownloadModal(itemUuid, itemType, button)
            })
        }
    }

    /**
     * Initialize or update the capture download temporal slider. Call before
     * showing the modal when opening for a capture with known bounds.
     * @param {number} durationMs - Total capture duration in milliseconds
     * @param {number} fileCadenceMs - File cadence in milliseconds (step)
     * @param {Object} opts - Optional: { perDataFileSize, totalSize, dataFilesCount, totalFilesCount, dataFilesTotalSize, captureUuid, captureStartEpochSec }
     */
    initializeCaptureDownloadSlider(modalId, durationMs, fileCadenceMs, opts) {
        const init = window.initializeCaptureDownloadSlider
        if (typeof init !== "function") {
            console.error(
                "initializeCaptureDownloadSlider not loaded; include captureDownloadSlider.js",
            )
            return
        }
        init(modalId, durationMs, fileCadenceMs, opts)
    }

    setTemporalSliderAttrs(modalId, sourceEl, itemUuid) {
        // Initialize temporal slider from data attributes on trigger button or modal
        const durationMs = Number.parseInt(
            sourceEl.getAttribute("data-length-of-capture-ms"),
            10,
        )
        const fileCadenceMs = Number.parseInt(
            sourceEl.getAttribute("data-file-cadence-ms"),
            10,
        )
        const perDataFileSize = Number.parseFloat(
            sourceEl.getAttribute("data-per-data-file-size"),
        )
        const dataFilesCount = Number.parseInt(
            sourceEl.getAttribute("data-data-files-count"),
            10,
        )
        const dataFilesTotalSize = Number.parseInt(
            sourceEl.getAttribute("data-total-data-file-size"),
            10,
        )
        const totalSize = Number.parseInt(
            sourceEl.getAttribute("data-total-size"),
            10,
        )
        const totalFilesCount = Number.parseInt(
            sourceEl.getAttribute("data-total-files-count"),
            10,
        )
        const captureStartEpochSec = Number.parseInt(
            sourceEl.getAttribute("data-capture-start-epoch-sec"),
            10,
        )
        this.initializeCaptureDownloadSlider(
            modalId,
            Number.isNaN(durationMs) ? 0 : durationMs,
            Number.isNaN(fileCadenceMs) ? 1000 : fileCadenceMs,
            {
                perDataFileSize: Number.isNaN(perDataFileSize)
                    ? 0
                    : perDataFileSize,
                totalSize: Number.isNaN(totalSize) ? 0 : totalSize,
                dataFilesCount: Number.isNaN(dataFilesCount)
                    ? 0
                    : dataFilesCount,
                totalFilesCount: Number.isNaN(totalFilesCount)
                    ? 0
                    : totalFilesCount,
                dataFilesTotalSize: Number.isNaN(dataFilesTotalSize)
                    ? undefined
                    : dataFilesTotalSize,
                captureUuid: itemUuid || undefined,
                captureStartEpochSec: Number.isNaN(captureStartEpochSec)
                    ? undefined
                    : captureStartEpochSec,
            },
        )
    }

    addTimeFilteringToFetchRequest(modalId) {
        const modalEl = document.getElementById(modalId)
        if (!modalEl) {
            return { body: {}, isJson: false }
        }
        const startTimeInput = modalEl.querySelector("#startTime")
        const endTimeInput = modalEl.querySelector("#endTime")
        const startEntry = modalEl.querySelector("#startTimeEntry")
        const endEntry = modalEl.querySelector("#endTimeEntry")

        if (startEntry && endEntry && modalEl && modalEl.dataset.durationMs) {
            const entryStart = startEntry.value.trim()
            const entryEnd = endEntry.value.trim()
            if (entryStart !== "" || entryEnd !== "") {
                const durationMs = Number.parseInt(
                    modalEl.dataset.durationMs,
                    10,
                )
                const startMs =
                    entryStart === "" ? 0 : Number.parseInt(entryStart, 10)
                const endMs =
                    entryEnd === "" ? durationMs : Number.parseInt(entryEnd, 10)
                if (
                    !Number.isFinite(startMs) ||
                    !Number.isFinite(endMs) ||
                    startMs < 0 ||
                    endMs > durationMs ||
                    startMs >= endMs
                ) {
                    this.showToast(
                        `Please enter valid start/end times (0 ≤ start < end ≤ ${durationMs} ms).`,
                        "warning",
                    )
                    return
                }
                if (startTimeInput) startTimeInput.value = String(startMs)
                if (endTimeInput) endTimeInput.value = String(endMs)
            }
        }

        const body = {}
        let isJson = true
        if (
            startTimeInput &&
            endTimeInput &&
            startTimeInput.value &&
            endTimeInput.value
        ) {
            body.start_time = startTimeInput.value
            body.end_time = endTimeInput.value
            isJson = false
        }

        return { body, isJson }
    }

    /**
     * Initialize web download modal for assets
     * @param {Element} button - Download button element
     */
    async initializeWebDownloadModal(itemUuid, itemType, button) {
        const modalId = `webDownloadModal-${itemUuid}`
        this.openModal(modalId, {
            trigger: button,
            downloadActionManager: this,
        })
    }

    /**
     * @param {string} modalId
     * @param {string} itemUuid
     * @param {string} itemType
     * @param {HTMLElement|null} triggerButton - row/menu button; null when opened via data-bs-toggle
     */
    wireWebDownloadConfirm(modalId, itemUuid, itemType, triggerButton) {
        const confirmBtn = document.getElementById(
            `confirmWebDownloadBtn-${itemUuid}`,
        )
        if (!confirmBtn) return

        const newConfirmBtn = confirmBtn.cloneNode(true)
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn)

        const statusEl = triggerButton ?? newConfirmBtn

        newConfirmBtn.onclick = async () => {
            const originalContent = statusEl.innerHTML
            await window.DOMUtils.renderLoading(statusEl, "Processing...", {
                format: "spinner",
                size: "sm",
            })
            statusEl.disabled = true

            this.closeModal(modalId)

            let body = {}
            let isJson = false
            try {
                if (itemType === "capture") {
                    const result = this.addTimeFilteringToFetchRequest(modalId)
                    if (!result) {
                        statusEl.innerHTML = originalContent
                        statusEl.disabled = false
                        return
                    }
                    body = result.body
                    isJson = result.isJson
                }
                const response = await window.APIClient.post(
                    `/users/download-item/${itemType}/${itemUuid}/`,
                    body,
                    null,
                    isJson,
                )

                if (response.success === true) {
                    await window.DOMUtils.renderContent(statusEl, {
                        icon: "check-circle",
                        color: "success",
                        text: "Download Requested",
                    })
                    this.showToast(
                        response.message ||
                            "Download request submitted successfully! You will receive an email when ready.",
                        "success",
                    )
                } else {
                    await window.DOMUtils.renderContent(statusEl, {
                        icon: "exclamation-triangle",
                        color: "danger",
                        text: "Request Failed",
                    })
                    this.showToast(
                        response.message ||
                            "Download request failed. Please try again.",
                        "danger",
                    )
                }
            } catch (error) {
                console.error("Download error:", error)
                await window.DOMUtils.renderContent(statusEl, {
                    icon: "exclamation-triangle",
                    color: "danger",
                    text: "Request Failed",
                })
                this.showToast(
                    error.message ||
                        "An error occurred while processing your request.",
                    "danger",
                )
            } finally {
                setTimeout(() => {
                    statusEl.innerHTML = originalContent
                    statusEl.disabled = false
                }, 3000)
            }
        }
    }

    /**
     * Initialize SDK download modal buttons
     */
    initializeSDKDownloadButtons() {
        // Find all SDK download buttons (by data attribute or class)
        const sdkDownloadButtons = document.querySelectorAll(
            '[data-action="sdk-download"], .sdk-download-btn',
        )

        for (const button of sdkDownloadButtons) {
            // Prevent duplicate event listener attachment
            if (button.dataset.downloadSetup === "true") {
                continue
            }
            button.dataset.downloadSetup = "true"

            button.addEventListener("click", (e) => {
                e.preventDefault()
                e.stopPropagation()

                const datasetUuid = button.getAttribute("data-dataset-uuid")

                if (!datasetUuid) {
                    console.warn(
                        "SDK download button missing dataset-uuid attribute",
                    )
                    return
                }

                this.openSDKDownloadModal(datasetUuid)
            })
        }
    }

    /**
     * Open SDK download modal for a specific dataset
     * @param {string} datasetUuid - Dataset UUID
     */
    openSDKDownloadModal(datasetUuid) {
        const modalId = `sdkDownloadModal-${datasetUuid}`
        const modal = document.getElementById(modalId)
        if (!modal) {
            console.warn(
                `SDK download modal not found for dataset ${datasetUuid}`,
            )
            return
        }

        // Re-initialize Prism syntax highlighting when modal is shown
        modal.addEventListener(
            "shown.bs.modal",
            () => {
                if (typeof Prism !== "undefined") {
                    // Highlight only within this modal
                    Prism.highlightAllUnder(modal)
                }
            },
            { once: true },
        )

        // Use centralized openModal method
        this.openModal(modalId)
    }

    /**
     * Check if user can download specific item
     * @param {Object} item - Item object
     * @returns {boolean} Whether user can download
     */
    canDownloadItem(_item) {
        // Check basic download permission
        if (!this.permissions.canDownload()) {
            return false
        }

        // Additional item-specific checks can be added here
        // For example, checking if item is public, if user owns it, etc.

        return true
    }

    /**
     * Cleanup resources
     */
    cleanup() {
        // Remove event listeners and clean up any resources
        const downloadButtons = document.querySelectorAll(".web-download-btn")
        for (const button of downloadButtons) {
            button.removeEventListener(
                "click",
                this.initializeWebDownloadButtons,
            )
        }
    }
}

// Make class available globally
window.DownloadActionManager = DownloadActionManager

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
    module.exports = { DownloadActionManager }
}
