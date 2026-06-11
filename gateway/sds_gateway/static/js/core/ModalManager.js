/**
 * Bootstrap modal lifecycle: init, open/close, list-modal wiring.
 *
 * Available methods:
 * - constructor(config) - Optional shell ids for legacy coordinator
 * - openModal(idOrElement) - Show modal
 * - closeModal(idOrElement) - Hide modal
 * - static initializeModal(config) - Page-level modal setup; returns cleanup
 * - static getOrCreateBootstrapModal(element, options)
 * - static showModalLoading(modalId, text) - Spinner in modal body
 * - static prepareBootstrapModalInstances(root) - Used by initializeModal
 */

class ModalManager extends BaseManager {
    constructor(config = {}) {
        super()
        this.modalId = config.modalId
        if (config.modalId) {
            this.modal = document.getElementById(this.modalId)
            this.modalTitle = config.modalTitleId
                ? document.getElementById(config.modalTitleId)
                : this.modal?.querySelector(".modal-title")
            this.modalBody = config.modalBodyId
                ? document.getElementById(config.modalBodyId)
                : this.modal?.querySelector(".modal-body")
        }
    }

    /**
     * @param {string | HTMLElement} idOrElement
     */
    /**
     * @param {string} modalId
     * @param {{ trigger?: HTMLElement|null }} [options]
     */
    openModal(modalId, options = {}) {
        const element = document.getElementById(modalId)
        if (!element) return null
        const onShown = () => {
            ModalManager._onModalShown(element, options)
        }
        element.addEventListener("shown.bs.modal", onShown, { once: true })
        const inst = ModalManager.getOrCreateBootstrapModal(element, {
            backdrop: true,
            keyboard: true,
            focus: true,
        })
        if (inst) inst.show()
        return inst
    }

    /**
     * @param {HTMLElement} modal
     * @param {{ trigger?: HTMLElement|null }} [options]
     */
    static _onModalShown(modal, options = {}) {
        const downloadManager =
            options.downloadActionManager ?? window.downloadActionManager
        if (
            modal?.id?.startsWith("webDownloadModal-") &&
            downloadManager?.prepareWebDownloadModal
        ) {
            downloadManager.prepareWebDownloadModal(
                modal,
                options.trigger ?? null,
            )
        }
    }

    /**
     * @param {string | HTMLElement} idOrElement
     */
    closeModal(modalId) {
        const element = document.getElementById(modalId)
        if (!element || !window.bootstrap?.Modal) return
        const inst = bootstrap.Modal.getInstance(element)
        if (!inst) return
        try {
            inst.hide()
        } catch (err) {
            console.warn("Modal hide failed, forcing cleanup:", err)
            element.classList.remove("show")
            element.setAttribute("aria-hidden", "true")
            element.removeAttribute("aria-modal")
            element.style.display = "none"
            document.body.classList.remove("modal-open")
            document.body.style.removeProperty("overflow")
            document.body.style.removeProperty("padding-right")
            for (const backdrop of document.querySelectorAll(
                ".modal-backdrop",
            )) {
                backdrop.remove()
            }
            try {
                inst.dispose()
            } catch (_) {
                /* ignore */
            }
        }
    }

    /** Reload list table using current URL query params (capture/dataset list pages). */
    static refreshListTableFromQueryString() {
        if (!window.listRefreshManager?.loadTable) return
        const params = Object.fromEntries(
            new URLSearchParams(window.location.search),
        )
        void window.listRefreshManager.loadTable(params, {
            showLoading: false,
        })
    }

    closeModalWithToast(msg, alertType, onAfterClose) {
        const modalEl = document.getElementById(this.modalId)
        if (modalEl) {
            this.modalEl = modalEl
        }
        const afterClose = () => {
            this.showToast(msg, alertType)
            onAfterClose?.()
        }
        if (modalEl) {
            modalEl.addEventListener("hidden.bs.modal", afterClose, {
                once: true,
            })
            this.closeModal(this.modalId)
        } else {
            afterClose()
        }
    }

    /**
     * @param {object} config
     * @param {ParentNode} [config.root]
     * @param {boolean} [config.bootstrap=true]
     * @param {'dataset'|'capture'|'both'} [config.wireListModals]
     * @param {object} [config.permissions] - raw perm config for PermissionsManager
     * @param {unknown[]} [config.managersOut]
     * @param {boolean} [config.detailsClickDelegation]
     * @param {boolean} [config.wireAllDataItemModalsShare]
     * @param {boolean} [config.registerFilesCaptureCoordinator]
     * @param {object} [config.downloadActionManager]
     * @returns {() => void} cleanup
     */
    static initializeModal(config = {}) {
        const cleanups = []
        const root = config.root ?? document

        if (config.bootstrap !== false) {
            ModalManager.prepareBootstrapModalInstances(root)
        }

        if (config.registerFilesCaptureCoordinator) {
            window.filesCaptureModalManager = new ModalManager({
                modalId: "asset-details-modal",
                modalBodyId: "asset-details-modal-body",
                modalTitleId: "asset-details-modal-label",
            })
        }

        if (config.detailsClickDelegation) {
            const detach =
                window.AssetDetailsModalLoader?.ensureDetailsClickDelegation?.() ??
                (() => {})
            cleanups.push(detach)
        }

        const managersOut = config.managersOut
        const permissions = config.permissions
        if (permissions && managersOut && window.PermissionsManager) {
            const permMgr =
                permissions instanceof window.PermissionsManager
                    ? permissions
                    : new window.PermissionsManager(permissions)
            const wire = config.wireListModals
            if (wire === "dataset" || wire === "both") {
                ModalManager._wireDatasetListModalsInternal(
                    permMgr,
                    managersOut,
                )
            }
            if (wire === "capture" || wire === "both") {
                ModalManager._wireCaptureListModalsInternal(
                    permMgr,
                    managersOut,
                )
            }
        }

        if (
            config.wireAllDataItemModalsShare &&
            permissions &&
            window.PermissionsManager &&
            window.ShareActionManager
        ) {
            const permissionsManager = new window.PermissionsManager(
                permissions,
            )
            const uuidRegex =
                /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
            const validTypes = new Set(["capture", "dataset", "file"])
            const bound = []

            for (const modal of document.querySelectorAll(
                ".modal[data-item-uuid]",
            )) {
                const itemUuid = modal.getAttribute("data-item-uuid")
                const itemType = modal.getAttribute("data-item-type")
                if (
                    !itemUuid ||
                    !itemType ||
                    !uuidRegex.test(itemUuid) ||
                    !validTypes.has(itemType)
                ) {
                    continue
                }

                const shareManager = new window.ShareActionManager({
                    itemUuid,
                    itemType,
                    permissions: permissionsManager,
                })
                modal.shareActionManager = shareManager

                const onHidden = () => {
                    modal.shareActionManager?.clearSelections?.()
                }
                modal.addEventListener("hidden.bs.modal", onHidden)
                bound.push({ modal, onHidden })
            }

            cleanups.push(() => {
                for (const { modal, onHidden } of bound) {
                    modal.removeEventListener("hidden.bs.modal", onHidden)
                }
            })
        }

        if (config.downloadActionManager) {
            cleanups.push(
                ModalManager._wireWebDownloadModalTriggers(
                    root,
                    config.downloadActionManager,
                ),
            )
        }

        return () => {
            for (const fn of cleanups) {
                fn?.()
            }
        }
    }

    /**
     * @param {string} modalId
     * @param {string} [text]
     */
    static async showModalLoading(modalId, text = "Loading...") {
        const modal = document.getElementById(modalId)
        if (!modal) return
        const modalBody = modal.querySelector(".modal-body")
        if (modalBody && window.DOMUtils?.renderLoading) {
            await window.DOMUtils.renderLoading(modalBody, text, {
                format: "modal",
            })
        }
    }

    static prepareBootstrapModalInstances(root = document) {
        if (!window.bootstrap) return
        for (const modal of root.querySelectorAll(".modal")) {
            const existingInstance = bootstrap.Modal.getInstance(modal)
            if (existingInstance) {
                try {
                    existingInstance.dispose()
                } catch (e) {
                    console.warn("Failed to dispose modal instance:", e)
                }
            }
            new bootstrap.Modal(modal, {
                backdrop: true,
                keyboard: true,
                focus: true,
            })
        }
    }

    static getOrCreateBootstrapModal(element, options = {}) {
        if (!element || !window.bootstrap?.Modal) return null
        let inst = bootstrap.Modal.getInstance(element)
        if (!inst) inst = new bootstrap.Modal(element, options)
        return inst
    }

    static _wireShareManagerForListModal(
        modal,
        permissions,
        managersOut,
        contextLabel,
    ) {
        const itemUuid = modal.getAttribute("data-item-uuid")
        const itemType = modal.getAttribute("data-item-type")

        if (!itemUuid || !permissions) {
            console.warn(
                `No item UUID or permissions found for ${contextLabel}: ${modal}`,
            )
            return null
        }

        if (window.ShareActionManager) {
            const shareManager = new window.ShareActionManager({
                permissions,
                itemUuid: itemUuid,
                itemType: itemType,
            })
            managersOut.push(shareManager)
            modal.shareActionManager = shareManager
        }
        return itemUuid
    }

    static _wireDatasetListModalsInternal(permissions, managersOut) {
        const datasetModals = document.querySelectorAll(
            ".modal[data-item-type='dataset']",
        )

        for (const modal of datasetModals) {
            const itemUuid = ModalManager._wireShareManagerForListModal(
                modal,
                permissions,
                managersOut,
                "dataset modal",
            )
            if (!itemUuid) continue

            if (
                window.VersioningActionManager &&
                !modal.versioningActionManager
            ) {
                const versioningManager = new window.VersioningActionManager({
                    permissions,
                    datasetUuid: itemUuid,
                })
                managersOut.push(versioningManager)
                modal.versioningActionManager = versioningManager
            }
        }
    }

    static _wireCaptureListModalsInternal(permissions, managersOut) {
        const captureModals = document.querySelectorAll(
            ".modal[data-item-type='capture']",
        )

        for (const modal of captureModals) {
            ModalManager._wireShareManagerForListModal(
                modal,
                permissions,
                managersOut,
                "capture modal",
            )
        }
    }

    /**
     * Route list-page download menu items through openModal (not raw data-bs-toggle).
     * @param {ParentNode} root
     * @param {object} downloadActionManager
     * @returns {() => void}
     */
    static _wireWebDownloadModalTriggers(root, downloadActionManager) {
        const handler = (event) => {
            const toggle = event.target.closest(
                '[data-bs-toggle="modal"][data-bs-target^="#webDownloadModal"],' +
                    '[data-bs-toggle="modal"][href^="#webDownloadModal"]',
            )
            if (!toggle || !root.contains(toggle)) {
                return
            }
            event.preventDefault()
            event.stopPropagation()
            downloadActionManager.openWebDownloadFromToggle(toggle)
        }
        root.addEventListener("click", handler, true)
        return () => root.removeEventListener("click", handler, true)
    }
}

if (typeof window !== "undefined") {
    window.ModalManager = ModalManager
}
if (typeof module !== "undefined" && module.exports) {
    module.exports = { ModalManager }
}
