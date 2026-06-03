/**
 * Confirm and delete captures or datasets via the assets API.
 */
class AssetDeletionManager extends ModalManager {
	constructor() {
		super();
		this.modalId = "deleteAssetModal";
		this.modalEl = document.getElementById(this.modalId);
		if (!this.modalEl) return;

		this.typeLabelEl = document.getElementById("delete-asset-type-label");
		this.nameEl = document.getElementById("delete-asset-name");
		this.messageEl = document.getElementById("delete-asset-message");
		this.confirmBtn = document.getElementById("delete-asset-confirm-btn");

		this.assetType = null;
		this.assetUuid = null;
		this.assetName = null;

		this.initializeEventListeners();
	}

	initializeEventListeners() {
		document.addEventListener("click", (e) => {
			const btn = e.target.closest(".delete-asset-btn");
			if (!btn) return;
			e.preventDefault();
			e.stopPropagation();
			const assetType = btn.getAttribute("data-asset-type");
			const assetUuid = btn.getAttribute("data-asset-uuid");
			if (!assetType || !assetUuid) return;
			this.openForAsset(
				assetType,
				assetUuid,
				btn.getAttribute("data-asset-name") || "",
			);
		});

		if (!this.modalEl) return;

		this.modalEl.addEventListener("show.bs.modal", () => {
			this.clearInlineMessage();
			if (this.confirmBtn) {
				this.confirmBtn.disabled = false;
			}
		});

		if (this.confirmBtn) {
			this.confirmBtn.addEventListener("click", () => void this.confirmDeletion());
		}
	}

	openForAsset(assetType, assetUuid, assetName) {
		this.assetType = assetType;
		this.assetUuid = assetUuid;
		this.assetName = assetName || "this asset";

		const typeLabel =
			assetType === "dataset"
				? "dataset"
				: assetType === "capture"
					? "capture"
					: "asset";
		if (this.typeLabelEl) {
			this.typeLabelEl.textContent = typeLabel;
		}
		if (this.nameEl) {
			this.nameEl.textContent = this.assetName;
		}

		this.openModal(this.modalId);
	}

	buildDeleteUrl(assetType, assetUuid) {
		const plural =
			assetType === "dataset"
				? "datasets"
				: assetType === "capture"
					? "captures"
					: `${assetType}s`;
		return `/api/v1/assets/${plural}/${assetUuid}/`;
	}

	clearInlineMessage() {
		window.DOMUtils?.toggleHidden(this.messageEl, true);
		if (this.messageEl) this.messageEl.textContent = "";
	}

	showInlineMessage(text) {
		if (!this.messageEl) return;
		this.messageEl.textContent = text;
		window.DOMUtils?.toggleHidden(this.messageEl, false);
	}

	async confirmDeletion() {
		const { assetType, assetUuid } = this;
		if (!assetType || !assetUuid) return;

		if (this.confirmBtn) this.confirmBtn.disabled = true;
		this.clearInlineMessage();

		try {
			await window.APIClient.delete(this.buildDeleteUrl(assetType, assetUuid));

			const label =
				assetType === "dataset"
					? "Dataset"
					: assetType === "capture"
						? "Capture"
						: "Asset";
			this.closeModalWithToast(`${label} deleted successfully.`, "success", () => {
				if (!window.listRefreshManager?.loadTable) return;
				const params = Object.fromEntries(
					new URLSearchParams(window.location.search),
				);
				void window.listRefreshManager.loadTable(params, {
					showLoading: false,
				});
			});
		} catch (err) {
			console.error(err);
			const detail =
				err?.data?.detail || err?.message || "Could not delete this asset.";
			this.showInlineMessage(
				typeof detail === "string" ? detail : "Could not delete this asset.",
			);
			if (this.confirmBtn) this.confirmBtn.disabled = false;
		}
	}

	closeModalWithToast(msg, alertType, onAfterClose) {
		const modalEl = document.getElementById(this.modalId);
		if (modalEl) {
			this.modalEl = modalEl;
		}
		const afterClose = () => {
			this.showToast(msg, alertType);
			onAfterClose?.();
		};
		if (modalEl) {
			modalEl.addEventListener("hidden.bs.modal", afterClose, { once: true });
			this.closeModal(this.modalId);
		} else {
			afterClose();
		}
	}
}

window.AssetDeletionManager = AssetDeletionManager;

if (typeof module !== "undefined" && module.exports) {
	module.exports = { AssetDeletionManager };
}
