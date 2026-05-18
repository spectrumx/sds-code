/**
 * Details Action Manager
 * Thin helpers for details UI (e.g. dataset UUID copy after server-rendered modal HTML).
 */
class DetailsActionManager {
	constructor(config) {
		this.permissions = config.permissions;
		this.itemUuid = config.itemUuid;
		this.itemType = config.itemType;
		this.initializeEventListeners();
	}

	initializeEventListeners() {
		// Per-instance wiring removed; dataset/capture details load via ModalManager + registry.
	}

	/**
	 * Wire UUID copy on a dataset details modal after HTML injection.
	 * @param {Element} modal
	 * @param {string} uuid
	 */
	static attachUuidCopyButton(modal, uuid) {
		const copyButton = modal?.querySelector?.(".copy-uuid-btn");
		if (!copyButton || !uuid) return;

		copyButton.dataset.uuid = uuid;
		copyButton.replaceWith(copyButton.cloneNode(true));
		const btn = modal.querySelector(".copy-uuid-btn");
		if (!btn) return;

		btn.addEventListener("click", (e) => {
			void DetailsActionManager.handleUuidCopy(e, uuid);
		});

		if (window.bootstrap?.Tooltip) {
			const bs = window.bootstrap;
			const existing = bs.Tooltip.getInstance(btn);
			if (existing) existing.dispose();
			new bs.Tooltip(btn);
		}
	}

	static async handleUuidCopy(event, uuid) {
		event.preventDefault();
		event.stopPropagation();

		try {
			await navigator.clipboard.writeText(uuid);
			await DetailsActionManager.showCopyFeedback(event.target, "Copied!");
		} catch (error) {
			console.warn("Clipboard API failed, trying fallback method:", error);
			try {
				window.UserInputController.execCommandCopyFallback(
					uuid,
				);
				await DetailsActionManager.showCopyFeedback(event.target, "Copied!");
			} catch (fallbackError) {
				console.error("Failed to copy UUID:", fallbackError);
				await DetailsActionManager.showCopyFeedback(
					event.target,
					"Copy failed",
					"error",
				);
			}
		}
	}

	static async showCopyFeedback(button, message, type = "success") {
		const copyButton = button.closest(".copy-uuid-btn") || button;
		const originalTitle = copyButton.getAttribute("title");
		const originalIcon = copyButton.innerHTML;

		const icon = type === "success" ? "check" : "x";
		const color = type === "success" ? "success" : "danger";

		await window.DOMUtils.renderContent(copyButton, { icon, color });
		copyButton.setAttribute("title", message);

		setTimeout(() => {
			copyButton.innerHTML = originalIcon;
			copyButton.setAttribute("title", originalTitle);
			if (window.bootstrap?.Tooltip) {
				const bs = window.bootstrap;
				const tooltip = bs.Tooltip.getInstance(copyButton);
				if (tooltip) {
					tooltip.dispose();
				}
				new bs.Tooltip(copyButton);
			}
		}, 2000);
	}

	/**
	 * Show modal loading state (legacy / tests)
	 * @param {string} modalId - Modal element id
	 */
	async showModalLoading(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const modalBody = modal.querySelector(".modal-body");
		if (modalBody) {
			if (!modalBody.dataset.originalContent) {
				modalBody.dataset.originalContent = modalBody.innerHTML;
			}

			await window.DOMUtils.renderLoading(modalBody, "Loading details...", {
				format: "modal",
			});
		}
	}

	cleanup() {
		// no-op
	}
}

window.DetailsActionManager = DetailsActionManager;

if (typeof module !== "undefined" && module.exports) {
	module.exports = { DetailsActionManager };
}
