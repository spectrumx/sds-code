/**
 * Registry-driven asset details modal (fetch HTML + inject).
 */
class AssetDetailsModalLoader {
    /**
     * @param {HTMLElement} startEl
     * @param {string[]} selectors
     * @returns {HTMLElement | null}
     */
    static findDelegateTarget(startEl, selectors) {
        if (!startEl || !selectors?.length) return null
        for (const sel of selectors) {
            if (startEl.matches?.(sel)) return startEl
            const closest = startEl.closest?.(sel)
            if (closest) return closest
        }
        return null
    }

    /**
     * @param {HTMLElement} startEl
     * @returns {{ cfg: object, target: HTMLElement } | null}
     */
    static resolveDetailsModalFromTrigger(startEl) {
        const registry = window.DetailsModalAssetRegistry
        if (!registry || !startEl) return null
        for (const key of Object.keys(registry)) {
            const cfg = registry[key]
            const selectors = cfg.delegateClickSelectors || []
            const target = AssetDetailsModalLoader.findDelegateTarget(
                startEl,
                selectors,
            )
            if (target) return { cfg, target }
        }
        return null
    }

    /**
     * @param {HTMLElement} startEl
     */
    static async openDetailsFromTrigger(startEl) {
        const resolved =
            AssetDetailsModalLoader.resolveDetailsModalFromTrigger(startEl)
        if (!resolved) return

        const { cfg, target } = resolved
        const uuid = cfg.resolveUuidFromTrigger(target)
        if (!uuid || uuid === "null" || uuid === "undefined") {
            console.warn("No valid UUID for details modal:", target)
            return
        }

        const shell =
            typeof cfg.resolveShell === "function" ? cfg.resolveShell() : null
        if (!shell?.modal || !shell.bodyEl) {
            console.warn("Details modal shell not found:", cfg.assetType, uuid)
            return
        }

        const { modal, titleEl, bodyEl } = shell

        if (cfg.assetType === "capture") {
            const visualizeBtn = document.getElementById("visualize-btn")
            visualizeBtn?.classList.add("d-none")
        }

        const loadingTitle = cfg.loadingTitle || "Loading..."
        if (titleEl) {
            titleEl.textContent = loadingTitle
        }
        bodyEl.innerHTML = `
				<div class="d-flex justify-content-center py-4">
					<div class="spinner-border text-primary" role="status">
						<span class="visually-hidden">${loadingTitle}</span>
					</div>
				</div>`

        const bsModal = window.ModalManager?.getOrCreateBootstrapModal?.(modal)
        if (bsModal) {
            bsModal.show()
        }

        try {
            const response = await fetch(cfg.buildDetailsUrl(uuid), {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}`)
            }
            const data = await response.json()

            if (titleEl) {
                titleEl.textContent = data.title || loadingTitle
            }
            bodyEl.innerHTML = data.html || ""

            const meta = data.meta || {}

            if (typeof cfg.afterInject === "function") {
                cfg.afterInject({ modal, meta, uuid, cfg })
            }
        } catch (error) {
            console.error("Error opening details modal:", error)
            const errTitle = "Error"
            const errBody =
                cfg.assetType === "capture"
                    ? "Error displaying capture details"
                    : "Error displaying dataset details"
            if (titleEl) {
                titleEl.textContent = errTitle
            }
            bodyEl.innerHTML = `<p class="text-danger mb-0">${errBody}</p>`
        }
    }

    /**
     * @returns {() => void} cleanup
     */
    static attachDocumentDetailsClickDelegation() {
        const handler = (e) => {
            if (
                e.target.matches('[data-bs-toggle="dropdown"]') ||
                e.target.closest('[data-bs-toggle="dropdown"]')
            ) {
                return
            }
            const resolved =
                AssetDetailsModalLoader.resolveDetailsModalFromTrigger(e.target)
            if (!resolved) return
            e.preventDefault()
            const { target } = resolved
            void AssetDetailsModalLoader.openDetailsFromTrigger(target)
        }
        document.addEventListener("click", handler)
        return () => {
            document.removeEventListener("click", handler)
            if (typeof document !== "undefined" && document.body) {
                document.body.dataset.detailsAssetClickWired = ""
            }
        }
    }

    /**
     * Idempotent global details click delegation.
     * @returns {() => void} cleanup
     */
    static ensureDetailsClickDelegation() {
        if (
            typeof document === "undefined" ||
            document.body?.dataset?.detailsAssetClickWired === "1"
        ) {
            return () => {}
        }
        document.body.dataset.detailsAssetClickWired = "1"
        return AssetDetailsModalLoader.attachDocumentDetailsClickDelegation()
    }
}

if (typeof window !== "undefined") {
    window.AssetDetailsModalLoader = AssetDetailsModalLoader
}
if (typeof module !== "undefined" && module.exports) {
    module.exports = { AssetDetailsModalLoader }
}
