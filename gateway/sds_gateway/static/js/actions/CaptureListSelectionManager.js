/**
 * Bulk capture selection on the captures list page (quick-add to dataset).
 */
class CaptureListSelectionManager {
	/**
	 * @param {import("./QuickAddToDatasetManager.js").QuickAddToDatasetManager} quickAddManager
	 */
	constructor(quickAddManager) {
		this.quickAdd = quickAddManager;
		this.bulkBtn = document.getElementById("capture-list-add-to-dataset-btn");
		this.countEl = document.getElementById("capture-list-selected-count");

		document.addEventListener("change", (e) => {
			if (!e.target.matches(".capture-select-checkbox")) return;
			e.stopPropagation();
			this.updateToolbar();
		});

		document.addEventListener("click", (e) => {
			if (e.target.matches(".capture-select-checkbox")) {
				e.stopPropagation();
			}
		});

		this.bulkBtn?.addEventListener("click", (e) => {
			e.preventDefault();
			this.openBulkModal();
		});

		this.updateToolbar();
	}

	getSelectedUuids() {
		return [
			...document.querySelectorAll(".capture-select-checkbox:checked"),
		]
			.map((cb) => cb.getAttribute("data-capture-uuid"))
			.filter(Boolean);
	}

	updateToolbar() {
		const count = this.getSelectedUuids().length;
		if (this.countEl) {
			this.countEl.textContent =
				count === 1 ? "1 capture selected" : `${count} captures selected`;
		}
		if (this.bulkBtn) {
			this.bulkBtn.disabled = count === 0;
		}
	}

	clearSelection() {
		for (const cb of document.querySelectorAll(
			".capture-select-checkbox:checked",
		)) {
			cb.checked = false;
		}
		this.updateToolbar();
	}

	openBulkModal() {
		const uuids = this.getSelectedUuids();
		if (!uuids.length || !this.quickAdd?.openForCaptureUuids) return;
		this.quickAdd.openForCaptureUuids(uuids);
	}
}

window.CaptureListSelectionManager = CaptureListSelectionManager;

if (typeof module !== "undefined" && module.exports) {
	module.exports = { CaptureListSelectionManager };
}
