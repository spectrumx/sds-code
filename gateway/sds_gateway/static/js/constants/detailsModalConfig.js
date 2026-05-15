/**
 * Registry for details modal loading (asset type → URLs + trigger resolution).
 * ModalManager reads window.DetailsModalAssetRegistry — no branching on asset type there.
 */
(function attachDetailsModalAssetRegistry(global) {
	function resolveAssetDetailsShell() {
		const modal = document.getElementById("asset-details-modal");
		if (!modal) return null;
		return {
			modal,
			titleEl:
				document.getElementById("asset-details-modal-label") ||
				modal.querySelector(".modal-title"),
			bodyEl:
				document.getElementById("asset-details-modal-body") ||
				modal.querySelector(".modal-body"),
		};
	}

	const capture = {
		assetType: "capture",
		delegateClickSelectors: [
			".capture-details-btn",
			".capture-link",
			".view-capture-btn",
		],
		buildDetailsUrl(uuid) {
			return `/users/details-modal/capture/${encodeURIComponent(uuid)}/`;
		},
		buildFilesSummaryUrl(uuid) {
			return `/users/details-modal/capture/${encodeURIComponent(uuid)}/?fragment=files`;
		},
		resolveUuidFromTrigger(el) {
			if (!el) return "";
			return (
				el.getAttribute("data-item-uuid") ||
				el.getAttribute("data-capture-uuid") ||
				el.getAttribute("data-uuid") ||
				""
			);
		},
		resolveShell() {
			return resolveAssetDetailsShell();
		},
		loadingTitle: "Loading capture details...",
	};

	const dataset = {
		assetType: "dataset",
		delegateClickSelectors: [".dataset-details-open"],
		buildDetailsUrl(uuid) {
			return `/users/details-modal/dataset/${encodeURIComponent(uuid)}/`;
		},
		resolveUuidFromTrigger(el) {
			if (!el) return "";
			const row = el.closest?.(".dataset-details-open");
			const src = row || el;
			return (
				src.getAttribute("data-dataset-uuid") ||
				src.getAttribute("data-item-uuid") ||
				""
			);
		},
		resolveShell() {
			return resolveAssetDetailsShell();
		},
		afterInject(ctx) {
			if (window.DetailsActionManager?.attachUuidCopyButton) {
				window.DetailsActionManager.attachUuidCopyButton(
					ctx.modal,
					ctx.meta?.uuid,
				);
			}
		},
		loadingTitle: "Loading dataset details...",
	};

	global.DetailsModalAssetRegistry = {
		capture,
		dataset,
	};
})(typeof window !== "undefined" ? window : globalThis);
