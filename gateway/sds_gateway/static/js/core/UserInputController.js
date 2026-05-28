/**
 * Shared user-input behaviors (clipboard fallbacks, debounced search wiring).
 * DOM rendering stays in DOMUtils; this module handles input/copy patterns.
 */
class UserInputController {
	/**
	 * Copy text using the hidden-textarea + execCommand fallback (no Clipboard API).
	 * @param {string} text
	 */
	static execCommandCopyFallback(text) {
		const textArea = document.createElement("textarea");
		textArea.value = text;
		textArea.style.position = "fixed";
		textArea.style.left = "-999999px";
		textArea.style.top = "-999999px";
		document.body.appendChild(textArea);
		textArea.focus();
		textArea.select();
		try {
			document.execCommand("copy");
		} finally {
			document.body.removeChild(textArea);
		}
	}

	/**
	 * Try navigator.clipboard, then {@link execCommandCopyFallback}.
	 * @param {string} text
	 * @returns {Promise<void>}
	 */
	static async copyTextToClipboard(text) {
		if (navigator.clipboard && window.isSecureContext) {
			await navigator.clipboard.writeText(text);
			return;
		}
		UserInputController.execCommandCopyFallback(text);
	}

	/**
	 * Wire debounced user search, keyboard navigation, and dropdown dismissal.
	 * @param {HTMLInputElement} input
	 * @param {{
	 *   selectedUsersMap: Record<string, Array<unknown>>,
	 *   getSearchTimeout: () => number | null | undefined,
	 *   setSearchTimeout: (id: number | null) => void,
	 *   getDropdownForInput: (input: HTMLElement) => HTMLElement | null,
	 *   hideDropdown: (dropdown: HTMLElement) => void,
	 *   navigateDropdown: (
	 *     items: NodeListOf<Element> | NodeList,
	 *     currentIndex: number,
	 *     direction: number,
	 *   ) => void,
	 *   searchUsers: (query: string, dropdown: HTMLElement) => void,
	 *   selectUser: (item: HTMLElement, input: HTMLInputElement) => void,
	 * }} adapter
	 */
	static bindUserSearchInput(input, adapter) {
		if (input.dataset.searchSetup === "true") {
			return;
		}
		input.dataset.searchSetup = "true";

		const dropdown = adapter.getDropdownForInput(input);
		if (!dropdown) {
			return;
		}

		const form = input.closest("form");
		const inputId = input.id;
		if (!adapter.selectedUsersMap[inputId]) {
			adapter.selectedUsersMap[inputId] = [];
		}

		input.addEventListener("input", (e) => {
			const prev = adapter.getSearchTimeout();
			if (prev) {
				clearTimeout(prev);
			}
			const query = /** @type {HTMLInputElement} */ (e.target).value.trim();

			if (query.length < 2) {
				adapter.hideDropdown(dropdown);
				adapter.setSearchTimeout(null);
				return;
			}

			const id = window.setTimeout(() => {
				adapter.searchUsers(query, dropdown);
			}, 300);
			adapter.setSearchTimeout(id);
		});

		input.addEventListener("keydown", (e) => {
			const visibleItems = dropdown.querySelectorAll(
				".list-group-item:not(.no-results)",
			);
			const currentIndex = Array.from(visibleItems).findIndex((item) =>
				item.classList.contains("selected"),
			);

			switch (e.key) {
				case "ArrowDown":
					e.preventDefault();
					adapter.navigateDropdown(visibleItems, currentIndex, 1);
					break;
				case "ArrowUp":
					e.preventDefault();
					adapter.navigateDropdown(visibleItems, currentIndex, -1);
					break;
				case "Enter": {
					e.preventDefault();
					const selectedItem = dropdown.querySelector(
						".list-group-item.selected",
					);
					if (selectedItem) {
						adapter.selectUser(selectedItem, input);
					}
					break;
				}
				case "Escape":
					adapter.hideDropdown(dropdown);
					input.blur();
					break;
				default:
					break;
			}
		});

		document.addEventListener("click", (e) => {
			const t = /** @type {Node} */ (e.target);
			if (!input.contains(t) && !dropdown.contains(t)) {
				adapter.hideDropdown(dropdown);
			}
		});

		dropdown.addEventListener("click", (e) => {
			const item = /** @type {HTMLElement} */ (e.target).closest(
				".list-group-item",
			);
			if (item && !item.classList.contains("no-results")) {
				e.preventDefault();
				e.stopPropagation();
				adapter.selectUser(item, input);
			}
		});

		if (form) {
			form.addEventListener("submit", () => {
				input.value = adapter.selectedUsersMap[inputId]
					.map((u) => /** @type {{ email: string }} */ (u).email)
					.join(",");
			});
		}
	}
}

window.UserInputController = UserInputController;

if (typeof module !== "undefined" && module.exports) {
	module.exports = { UserInputController };
}
