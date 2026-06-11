/**
 * Confirm and delete captures or datasets via the assets API.
 */
class AssetDeletionManager extends ModalManager {
    constructor() {
        super()
        this.modalId = "deleteAssetModal"
        this.modalEl = document.getElementById(this.modalId)
        if (!this.modalEl) return

        this.typeLabelEl = document.getElementById("delete-asset-type-label")
        this.typeLabelSharedEl = document.getElementById(
            "delete-asset-type-label-shared",
        )
        this.titleDeletableEl = document.getElementById(
            "delete-asset-title-deletable",
        )
        this.titleSharedEl = document.getElementById(
            "delete-asset-title-shared",
        )
        this.nameEl = document.getElementById("delete-asset-name")
        this.nameSharedEl = document.getElementById("delete-asset-name-shared")
        this.deletableBodyEl = document.getElementById(
            "delete-asset-body-deletable",
        )
        this.sharedBodyEl = document.getElementById("delete-asset-body-shared")
        this.messageEl = document.getElementById("delete-asset-message")
        this.confirmBtn = document.getElementById("delete-asset-confirm-btn")

        this.assetType = null
        this.assetUuid = null
        this.assetName = null
        this.assetIsShared = false

        this.initializeEventListeners()
    }

    initializeEventListeners() {
        document.addEventListener("click", (e) => {
            const btn = e.target.closest(".delete-asset-btn")
            if (!btn) return
            e.preventDefault()
            e.stopPropagation()
            const assetType = btn.getAttribute("data-asset-type")
            const assetUuid = btn.getAttribute("data-asset-uuid")
            if (!assetType || !assetUuid) return
            this.openForAsset(
                assetType,
                assetUuid,
                btn.getAttribute("data-asset-name") || "",
                btn.getAttribute("data-asset-shared") === "true",
            )
        })

        if (!this.modalEl) return

        this.modalEl.addEventListener("show.bs.modal", () => {
            this.clearInlineMessage()
            this.applySharedState()
        })

        if (this.confirmBtn) {
            this.confirmBtn.addEventListener(
                "click",
                () => void this.confirmDeletion(),
            )
        }
    }

    openForAsset(assetType, assetUuid, assetName, assetIsShared = false) {
        this.assetType = assetType
        this.assetUuid = assetUuid
        this.assetName = assetName || "this asset"
        this.assetIsShared = Boolean(assetIsShared)

        const typeLabel =
            assetType === "dataset"
                ? "dataset"
                : assetType === "capture"
                  ? "capture"
                  : "asset"
        if (this.typeLabelEl) {
            this.typeLabelEl.textContent = typeLabel
        }
        if (this.typeLabelSharedEl) {
            this.typeLabelSharedEl.textContent = typeLabel
        }
        const displayName = this.assetName
        if (this.nameEl) {
            this.nameEl.textContent = displayName
        }
        if (this.nameSharedEl) {
            this.nameSharedEl.textContent = displayName
        }

        this.applySharedState()
        this.openModal(this.modalId)
    }

    applySharedState() {
        const isShared = this.assetIsShared
        window.DOMUtils?.toggleHidden(this.deletableBodyEl, isShared)
        window.DOMUtils?.toggleHidden(this.sharedBodyEl, !isShared)
        window.DOMUtils?.toggleHidden(this.confirmBtn, isShared)
        window.DOMUtils?.toggleHidden(this.titleDeletableEl, isShared)
        window.DOMUtils?.toggleHidden(this.titleSharedEl, !isShared)

        if (this.confirmBtn) {
            this.confirmBtn.disabled = isShared
        }
    }

    buildDeleteUrl(assetType, assetUuid) {
        const plural =
            assetType === "dataset"
                ? "datasets"
                : assetType === "capture"
                  ? "captures"
                  : `${assetType}s`
        return `/api/v1/assets/${plural}/${assetUuid}/`
    }

    clearInlineMessage() {
        window.DOMUtils?.toggleHidden(this.messageEl, true)
        if (this.messageEl) this.messageEl.textContent = ""
    }

    showInlineMessage(text) {
        if (!this.messageEl) return
        this.messageEl.textContent = text
        window.DOMUtils?.toggleHidden(this.messageEl, false)
    }

    async confirmDeletion() {
        if (this.assetIsShared) return

        const { assetType, assetUuid } = this
        if (!assetType || !assetUuid) return

        if (this.confirmBtn) this.confirmBtn.disabled = true
        this.clearInlineMessage()

        try {
            await window.APIClient.delete(
                this.buildDeleteUrl(assetType, assetUuid),
            )

            const label =
                assetType === "dataset"
                    ? "Dataset"
                    : assetType === "capture"
                      ? "Capture"
                      : "Asset"
            this.closeModalWithToast(
                `${label} deleted successfully.`,
                "success",
                ModalManager.refreshListTableFromQueryString,
            )
        } catch (err) {
            console.error(err)
            const detail =
                err?.data?.detail ||
                err?.message ||
                "Could not delete this asset."
            this.showInlineMessage(
                typeof detail === "string"
                    ? detail
                    : "Could not delete this asset.",
            )
            if (this.confirmBtn) this.confirmBtn.disabled = false
        }
    }
}

window.AssetDeletionManager = AssetDeletionManager

if (typeof module !== "undefined" && module.exports) {
    module.exports = { AssetDeletionManager }
}
