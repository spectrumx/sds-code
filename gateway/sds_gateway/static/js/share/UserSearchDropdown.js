/**
 * Shared DOM helpers for user-search dropdowns in share modals.
 * Used by ShareActionManager and ShareGroupManager.
 */
class UserSearchDropdown {
	/**
	 * @param {HTMLInputElement} input
	 * @param {{ itemUuid?: string }} [options]
	 * @returns {Element|null}
	 */
	static getDropdownForInput(input, options = {}) {
		if (!input) return null;

		const suffix = input.id.replace("user-search-", "");
		let dropdown = document.getElementById(`user-search-dropdown-${suffix}`);
		if (dropdown) {
			return dropdown;
		}

		const altIds = [];
		if (options.itemUuid) {
			altIds.push(`user-search-dropdown-${options.itemUuid}`);
		}
		altIds.push(
			"user-search-dropdown-sharegroup",
			"user-search-dropdown",
			input.id.replace("user-search-", "user-search-dropdown-"),
			`${input.id}-dropdown`,
		);

		for (const id of altIds) {
			dropdown = document.getElementById(id);
			if (dropdown) {
				return dropdown;
			}
		}

		const container = input.closest(".user-search-input-container");
		if (container) {
			dropdown = container.querySelector(".user-search-dropdown");
			if (dropdown) {
				return dropdown;
			}
		}

		console.error(`Could not find dropdown for input: ${input.id}`);
		return null;
	}

	/**
	 * @param {NodeListOf<Element>|Element[]} items
	 * @param {number} currentIndex
	 * @param {number} direction
	 */
	static navigateDropdown(items, currentIndex, direction) {
		for (const item of items) {
			item.classList.remove("selected");
		}

		let newIndex;
		if (currentIndex === -1) {
			newIndex = direction > 0 ? 0 : items.length - 1;
		} else {
			newIndex = currentIndex + direction;
			if (newIndex < 0) newIndex = items.length - 1;
			if (newIndex >= items.length) newIndex = 0;
		}

		if (items[newIndex]) {
			items[newIndex].classList.add("selected");
			items[newIndex].scrollIntoView({ block: "nearest" });
		}
	}

	/** @param {Element|null|undefined} dropdown */
	static showDropdown(dropdown) {
		if (dropdown) {
			dropdown.classList.remove("d-none");
		}
	}

	/** @param {Element|null|undefined} dropdown */
	static hideDropdown(dropdown) {
		if (dropdown) {
			dropdown.classList.add("d-none");
			for (const item of dropdown.querySelectorAll(".list-group-item")) {
				item.classList.remove("selected");
			}
		}
	}
}

if (typeof window !== "undefined") {
	window.UserSearchDropdown = UserSearchDropdown;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { UserSearchDropdown };
}
