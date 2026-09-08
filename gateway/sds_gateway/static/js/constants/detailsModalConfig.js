/**
 * Registry for details modal loading (asset type → URLs + trigger resolution).
 * ModalManager reads window.DetailsModalAssetRegistry — no branching on asset type there.
 */
;(function attachDetailsModalAssetRegistry(global) {
    function resolveAssetDetailsShell() {
        const modal = document.getElementById("asset-details-modal")
        if (!modal) return null
        return {
            modal,
            titleEl:
                document.getElementById("asset-details-modal-label") ||
                modal.querySelector(".modal-title"),
            bodyEl:
                document.getElementById("asset-details-modal-body") ||
                modal.querySelector(".modal-body"),
        }
    }

    function federatedPeerFromTrigger(el) {
        if (!el) return false
        const nodes = [el]
        const link = el.querySelector?.(".dataset-name-link")
        if (link) nodes.push(link)
        const closestLink = el.closest?.(".dataset-name-link")
        if (closestLink) nodes.push(closestLink)
        for (const node of nodes) {
            const raw = node.getAttribute("data-federated-peer")
            if (raw == null || raw === "") continue
            if (/^(true|1)$/i.test(String(raw).trim())) return true
        }
        return false
    }

    const capture = {
        assetType: "capture",
        delegateClickSelectors: [
            ".capture-details-btn",
            ".capture-link",
            ".view-capture-btn",
        ],
        buildDetailsUrl(uuid, triggerEl) {
            if (federatedPeerFromTrigger(triggerEl)) {
                return `/users/details-modal/capture/${encodeURIComponent(uuid)}/?federated_peer=true`
            }
            return `/users/details-modal/capture/${encodeURIComponent(uuid)}/`
        },
        resolveUuidFromTrigger(el) {
            if (!el) return ""
            return (
                el.getAttribute("data-item-uuid") ||
                el.getAttribute("data-capture-uuid") ||
                el.getAttribute("data-uuid") ||
                ""
            )
        },
        resolveShell() {
            return resolveAssetDetailsShell()
        },
        afterInject(ctx) {
            if (window.CaptureDetailsModalBehavior?.afterInject) {
                window.CaptureDetailsModalBehavior.afterInject(ctx)
            }
            if (window.DetailsActionManager?.attachUuidCopyButton) {
                window.DetailsActionManager.attachUuidCopyButton(
                    ctx.modal,
                    ctx.meta?.uuid,
                )
            }
        },
        loadingTitle: "Loading capture details...",
    }

    const dataset = {
        assetType: "dataset",
        delegateClickSelectors: [".dataset-details-open"],
        buildDetailsUrl(uuid, triggerEl) {
            if (federatedPeerFromTrigger(triggerEl)) {
                return `/users/details-modal/dataset/${encodeURIComponent(uuid)}/?federated_peer=true`
            }
            return `/users/details-modal/dataset/${encodeURIComponent(uuid)}/`
        },
        resolveUuidFromTrigger(el) {
            if (!el) return ""
            const row = el.closest?.(".dataset-details-open")
            const src = row || el
            return (
                src.getAttribute("data-dataset-uuid") ||
                src.getAttribute("data-item-uuid") ||
                ""
            )
        },
        resolveShell() {
            return resolveAssetDetailsShell()
        },
        afterInject(ctx) {
            if (window.DetailsActionManager?.attachUuidCopyButton) {
                window.DetailsActionManager.attachUuidCopyButton(
                    ctx.modal,
                    ctx.meta?.uuid,
                )
            }
        },
        loadingTitle: "Loading dataset details...",
    }

    global.DetailsModalAssetRegistry = {
        capture,
        dataset,
    }
})(typeof window !== "undefined" ? window : globalThis)
