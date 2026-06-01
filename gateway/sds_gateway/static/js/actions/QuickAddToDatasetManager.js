/**
 * Quick Add to Dataset Manager
 * Handles opening the quick-add modal, loading datasets, and adding a capture to a dataset.
 */
class QuickAddToDatasetManager extends ModalManager {
    constructor() {
        super()
        this.modalId = "quickAddToDatasetModal"
        this.modalEl = document.getElementById(this.modalId)
        this.currentCaptureUuid = null
        this.currentCaptureName = null
        /** @type {string[]|null} When set, call quick-add API once per UUID (e.g. from file list "Add" button) */
        this.currentCaptureUuids = null
        if (!this.modalEl) return
        this.quickAddUrl = this.modalEl.getAttribute("data-quick-add-url")
        this.datasetsUrl = this.modalEl.getAttribute("data-datasets-url")
        this.selectEl = document.getElementById("quick-add-dataset-select")
        this.confirmBtn = document.getElementById("quick-add-confirm-btn")
        this.messageEl = document.getElementById("quick-add-message")
        this.captureNameEl = document.getElementById("quick-add-capture-name")
        this.initializeEventListeners()
    }

    initializeEventListeners() {
        // Delegate click on "Add to dataset" buttons (e.g. in table dropdown)
        document.addEventListener("click", (e) => {
            const btn = e.target.closest(".add-to-dataset-btn")
            if (!btn) return
            e.preventDefault()
            e.stopPropagation()
            const uuid = btn.getAttribute("data-capture-uuid")
            if (!uuid) return
            this.openForSingleCapture(
                uuid,
                btn.getAttribute("data-capture-name") || "This capture",
            )
        })

        if (!this.modalEl) return

        // When modal is shown, load datasets and apply state (single vs multi from file list)
        this.modalEl.addEventListener("show.bs.modal", () => {
            this.resetMessage()
            const rawIds = this.modalEl.dataset.captureUuids
            if (rawIds) {
                try {
                    this.currentCaptureUuids = JSON.parse(rawIds)
                    this.currentCaptureUuid = null
                    this.currentCaptureName = null
                    const n = this.currentCaptureUuids.length
                    if (this.captureNameEl) {
                        this.captureNameEl.textContent =
                            n === 1 ? "1 capture" : `${n} captures`
                    }
                    delete this.modalEl.dataset.captureUuids
                } catch (_) {
                    this.currentCaptureUuids = null
                }
            } else {
                this.currentCaptureUuids = null
                if (this.captureNameEl) {
                    this.captureNameEl.textContent =
                        this.currentCaptureName || "This capture"
                }
            }
            this.loadDatasets()
        })

        // When dataset select changes, enable/disable Add button
        if (this.selectEl) {
            this.selectEl.addEventListener("change", () => {
                if (this.confirmBtn) {
                    this.confirmBtn.disabled = !this.selectEl.value
                }
            })
        }

        // Add button click
        if (this.confirmBtn) {
            this.confirmBtn.addEventListener("click", () => this.handleAdd())
        }
    }

    /** Open modal for one capture (row actions menu). */
    openForSingleCapture(captureUuid, captureName) {
        if (!this.modalEl) return
        delete this.modalEl.dataset.captureUuids
        this.currentCaptureUuids = null
        this.currentCaptureUuid = captureUuid
        this.currentCaptureName = captureName || "This capture"
        this.openModal(this.modalId)
    }

    /** Open modal for multiple selected captures (list bulk action). */
    openForCaptureUuids(captureUuids) {
        if (!this.modalEl || !captureUuids?.length) return
        this.currentCaptureUuid = null
        this.currentCaptureName = null
        this.currentCaptureUuids = captureUuids
        this.modalEl.dataset.captureUuids = JSON.stringify(captureUuids)
        this.openModal(this.modalId)
    }

    resetMessage() {
        if (this.messageEl) {
            this.messageEl.innerHTML = ""
            this.messageEl.classList.add("d-none")
            this.messageEl.classList.remove(
                "alert-success",
                "alert-danger",
                "alert-warning",
            )
        }
        if (this.confirmBtn) {
            this.confirmBtn.disabled = true
        }
        if (this.selectEl) {
            this.selectEl.innerHTML = '<option value="">Loading...</option>'
        }
    }

    /** Inline alert in the quick-add modal via {@link DOMUtils.showMessage}. */
    showInlineMessage(text, type) {
        if (!this.messageEl) return
        this.messageEl.classList.remove("d-none")
        window.DOMUtils?.show?.(this.messageEl)
        const variant =
            type === "danger" || type === "error"
                ? "danger"
                : type === "success" || type === "warning" || type === "info"
                  ? type
                  : "danger"
        void this.showMessageInTarget(text, this.messageEl, {
            variant,
            presentation: "alert",
            templateContext: {
                icon:
                    variant === "warning"
                        ? "exclamation-triangle"
                        : "exclamation-circle",
            },
        })
    }

    async loadDatasets() {
        if (!this.selectEl || !this.datasetsUrl) return
        this.selectEl.innerHTML = '<option value="">Loading...</option>'
        if (this.confirmBtn) this.confirmBtn.disabled = true
        try {
            const response = await window.APIClient.get(this.datasetsUrl)
            const datasets = response.datasets || []
            this.selectEl.innerHTML =
                '<option value="">Select dataset...</option>'
            for (const d of datasets) {
                const opt = document.createElement("option")
                opt.value = d.uuid
                opt.textContent = d.name
                this.selectEl.appendChild(opt)
            }
            if (datasets.length === 0) {
                this.showInlineMessage(
                    "You have no datasets you can add captures to.",
                    "warning",
                )
            }
        } catch (err) {
            this.selectEl.innerHTML = '<option value="">Failed to load</option>'
            const reason = err?.data?.error || err?.message || "Try again."
            this.showInlineMessage(
                `Failed to load datasets. ${reason}`,
                "danger",
            )
        }
    }

    async handleAdd() {
        const datasetUuid = this.selectEl?.value
        if (!datasetUuid) return
        const isMulti =
            Array.isArray(this.currentCaptureUuids) &&
            this.currentCaptureUuids.length > 0
        const isSingle = this.currentCaptureUuid && this.quickAddUrl
        if (!isMulti && !isSingle) {
            this.showInlineMessage(
                "Select at least one capture, or use “Add to dataset” from a row’s actions menu.",
                "warning",
            )
            return
        }
        if (this.confirmBtn) this.confirmBtn.disabled = true
        this.resetMessage()
        if (isMulti) {
            await this.handleMultiAdd(datasetUuid)
        } else {
            await this.handleSingleAdd(datasetUuid)
        }
    }

    formatQuickAddSummary(added, skipped, failedCount, firstErrorMessage) {
        return (
            window.QuickAddApi?.formatQuickAddSummary?.(
                added,
                skipped,
                failedCount,
                firstErrorMessage,
            ) ?? "Done."
        )
    }

    _notifyGlobalToast(msg, alertType) {
        this.showToast(msg, alertType)
    }

    /**
     * Close the modal and fire a toast notification after it finishes hiding.
     * This avoids showing the same message twice (once inside the closing modal
     * and once as a toast outside it).
     */
    _closeWithToast(msg, alertType) {
        const afterClose = () => {
            this.modalEl.removeEventListener("hidden.bs.modal", afterClose)
            window.captureListSelectionManager?.clearSelection?.()
            this._notifyGlobalToast(msg, alertType)
        }
        if (this.modalEl) {
            this.modalEl.addEventListener("hidden.bs.modal", afterClose)
            this.closeModal(this.modalEl)
        } else {
            window.captureListSelectionManager?.clearSelection?.()
            this._notifyGlobalToast(msg, alertType)
        }
    }

    /**
     * Call quick-add API once per selected capture UUID. Backend handles
     * multi-channel grouping per UUID; we aggregate counts and show one message.
     */
    async handleMultiAdd(datasetUuid) {
        if (!this.quickAddUrl) {
            this.showInlineMessage("Quick-add URL not configured.", "danger")
            if (this.confirmBtn) this.confirmBtn.disabled = false
            return
        }
        const { totalAdded, totalSkipped, errorMessages } =
            await window.QuickAddApi.postQuickAddCaptures(
                this.quickAddUrl,
                datasetUuid,
                this.currentCaptureUuids,
            )
        const errorCount = errorMessages.length
        const hasErrors = errorCount > 0
        const hasSuccess = totalAdded > 0 || totalSkipped > 0
        const msg = this.formatQuickAddSummary(
            totalAdded,
            totalSkipped,
            errorCount,
            errorMessages[0],
        )
        if (hasSuccess || !hasErrors) {
            this._closeWithToast(msg, hasErrors ? "warning" : "success")
        } else {
            // All requests failed — keep modal open so the user can try again
            this.showInlineMessage(msg, "warning")
            if (this.confirmBtn) this.confirmBtn.disabled = false
        }
    }

    async handleSingleAdd(datasetUuid) {
        try {
            const result = await window.QuickAddApi.postQuickAddCapture(
                this.quickAddUrl,
                datasetUuid,
                this.currentCaptureUuid,
            )
            if (result.success) {
                const msg = this.formatQuickAddSummary(
                    result.added,
                    result.skipped,
                    result.errors.length,
                    result.errors[0],
                )
                this._closeWithToast(
                    msg,
                    result.errors.length > 0 ? "warning" : "success",
                )
            } else {
                this.showInlineMessage(
                    result.errors[0] || "Request failed.",
                    "danger",
                )
                if (this.confirmBtn) this.confirmBtn.disabled = false
            }
        } catch (err) {
            const msg =
                err?.data?.error ||
                err?.message ||
                "Failed to add capture to dataset."
            this.showInlineMessage(msg, "danger")
            if (this.confirmBtn) this.confirmBtn.disabled = false
        }
    }
}

window.QuickAddToDatasetManager = QuickAddToDatasetManager

if (typeof module !== "undefined" && module.exports) {
    module.exports = { QuickAddToDatasetManager }
}
