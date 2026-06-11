/**
 * Capture reindex: preview pending files under top_level_dir, confirm via PUT update.
 */
class CaptureReindexingManager extends ModalManager {
    constructor() {
        super()
        this.modalId = "reindexCaptureModal"
        this.modalEl = document.getElementById(this.modalId)
        if (!this.modalEl) return

        this.previewUrlTemplate = this.modalEl.getAttribute(
            "data-preview-url-template",
        )
        this.currentCaptureUuid = null
        this.currentCaptureName = null
        this.currentTopLevelDir = null

        this.nameEl = document.getElementById("reindex-capture-name")
        this.pathEl = document.getElementById("reindex-top-level-dir")
        this.loadingEl = document.getElementById("reindex-loading")
        this.emptyHintEl = document.getElementById("reindex-empty-hint")
        this.pendingSectionEl = document.getElementById(
            "reindex-pending-section",
        )
        this.pendingTbody = document.getElementById("reindex-pending-tbody")
        this.progressEl = document.getElementById("reindex-progress")
        this.messageEl = document.getElementById("reindex-message")
        this.confirmBtn = document.getElementById("reindex-confirm-btn")

        this.initializeEventListeners()
    }

    initializeEventListeners() {
        document.addEventListener("click", (e) => {
            const btn = e.target.closest(".reindex-capture-btn")
            if (!btn) return
            e.preventDefault()
            e.stopPropagation()
            const uuid = btn.getAttribute("data-capture-uuid")
            if (!uuid) return
            this.openForCapture(
                uuid,
                btn.getAttribute("data-capture-name") || "Capture",
                btn.getAttribute("data-top-level-dir") || "",
            )
        })

        if (!this.modalEl) return

        this.modalEl.addEventListener("show.bs.modal", () => {
            this.resetUi()
            if (this.nameEl) {
                this.nameEl.textContent = this.currentCaptureName || "Capture"
            }
            if (this.pathEl) {
                this.pathEl.textContent = this.currentTopLevelDir || "—"
            }
            void this.loadPendingChanges()
        })

        if (this.confirmBtn) {
            this.confirmBtn.addEventListener(
                "click",
                () => void this.confirmReindex(),
            )
        }
    }

    openForCapture(uuid, name, topLevelDir) {
        this.currentCaptureUuid = uuid
        this.currentCaptureName = name
        this.currentTopLevelDir = topLevelDir
        this.openModal(this.modalId)
    }

    resetUi() {
        this.clearInlineMessage()
        this.setPreviewLoading(false)
        this.setReindexProgress(false)
        window.DOMUtils?.toggleHidden(this.emptyHintEl, true)
        window.DOMUtils?.toggleHidden(this.pendingSectionEl, true)
        if (this.pendingTbody) this.pendingTbody.innerHTML = ""
        if (this.confirmBtn) {
            this.confirmBtn.disabled = false
            this.confirmBtn.textContent = "Reindex capture"
        }
    }

    clearInlineMessage() {
        window.DOMUtils?.toggleHidden(this.messageEl, true)
        if (this.messageEl) this.messageEl.textContent = ""
    }

    showInlineMessage(text, variant = "danger") {
        if (!this.messageEl) return
        const alertType =
            variant === "error" || variant === "danger" ? "danger" : variant
        this.messageEl.className = `alert alert-${alertType} mt-3`
        this.messageEl.textContent = text
        window.DOMUtils?.toggleHidden(this.messageEl, false)
    }

    async setPreviewLoading(visible) {
        if (!this.loadingEl || !window.DOMUtils) return
        window.DOMUtils.toggleHidden(this.loadingEl, !visible)
        if (!visible) {
            this.loadingEl.innerHTML = ""
            return
        }
        await window.DOMUtils.renderLoading(
            this.loadingEl,
            "Checking for new or updated files…",
            {
                format: "block",
                size: "sm",
            },
        )
    }

    async setReindexProgress(visible, text = "Reindexing capture…") {
        if (!this.progressEl || !window.DOMUtils) return
        window.DOMUtils.toggleHidden(this.progressEl, !visible)
        if (!visible) {
            this.progressEl.innerHTML = ""
            return
        }
        await window.DOMUtils.renderProgress(this.progressEl, text)
    }

    buildPreviewUrl(captureUuid) {
        if (!this.previewUrlTemplate) return null
        return this.previewUrlTemplate.replace(
            "00000000-0000-0000-0000-000000000000",
            captureUuid,
        )
    }

    async loadPendingChanges() {
        const uuid = this.currentCaptureUuid
        const url = uuid ? this.buildPreviewUrl(uuid) : null
        if (!url) {
            this.showInlineMessage("Preview URL is not configured.", "danger")
            return
        }

        await this.setPreviewLoading(true)
        try {
            const data = await window.APIClient.get(url)
            this.renderPendingList(data?.pending_files || [])
        } catch (err) {
            console.error(err)
            const detail =
                err?.data?.detail ||
                err?.message ||
                "Could not load pending file changes."
            this.showInlineMessage(detail, "danger")
        } finally {
            await this.setPreviewLoading(false)
        }
    }

    renderPendingList(pendingFiles) {
        const hasPending = pendingFiles.length > 0
        window.DOMUtils?.toggleHidden(this.emptyHintEl, hasPending)
        window.DOMUtils?.toggleHidden(this.pendingSectionEl, !hasPending)
        if (!this.pendingTbody || !hasPending) return

        this.pendingTbody.innerHTML = ""
        const formatSize = window.DOMUtils?.formatFileSize?.bind(
            window.DOMUtils,
        )
        for (const row of pendingFiles) {
            const tr = document.createElement("tr")
            const pathTd = document.createElement("td")
            pathTd.className = "small font-monospace text-break"
            const dir = String(row.directory || "").replace(/\/$/, "")
            pathTd.textContent = dir ? `${dir}/${row.name}` : row.name

            const statusTd = document.createElement("td")
            statusTd.className = `small ${row.status === "updated" ? "text-warning" : "text-primary"}`
            statusTd.textContent =
                row.status === "updated" ? "Updated" : "Not linked"

            const sizeTd = document.createElement("td")
            sizeTd.className = "small text-end"
            const size = Number(row.size)
            sizeTd.textContent =
                formatSize && Number.isFinite(size) && size > 0
                    ? formatSize(size)
                    : "—"

            tr.append(pathTd, statusTd, sizeTd)
            this.pendingTbody.appendChild(tr)
        }
    }

    async confirmReindex() {
        const uuid = this.currentCaptureUuid
        if (!uuid) return

        if (this.confirmBtn) this.confirmBtn.disabled = true
        this.clearInlineMessage()
        await this.setReindexProgress(true)

        try {
            await window.APIClient.put(`/api/v1/assets/captures/${uuid}/`, {})

            await this.setReindexProgress(false)
            this.closeModalWithToast(
                "Capture reindexed successfully. Visualizations will update in the background.",
                "success",
                ModalManager.refreshListTableFromQueryString,
            )
        } catch (err) {
            console.error(err)
            await this.setReindexProgress(false)
            const detail =
                err?.data?.detail || err?.message || "Reindex failed."
            this.showInlineMessage(detail, "danger")
            if (this.confirmBtn) this.confirmBtn.disabled = false
        }
    }
}

window.CaptureReindexingManager = CaptureReindexingManager

if (typeof module !== "undefined" && module.exports) {
    module.exports = { CaptureReindexingManager }
}
