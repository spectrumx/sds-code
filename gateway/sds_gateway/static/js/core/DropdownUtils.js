/**
 * Bootstrap dropdown initialization for icon action menus (body container).
 * Migrated from deprecated/file-list.js.
 */
const DropdownUtils = {
	/**
	 * @param {ParentNode} [root]
	 */
	initIconDropdowns(root = document) {
		const dropdownButtons = root.querySelectorAll(".btn-icon-dropdown");

		if (dropdownButtons.length === 0) {
			return;
		}

		for (const toggle of dropdownButtons) {
			if (toggle._dropdown) {
				continue;
			}

			toggle._dropdown = new bootstrap.Dropdown(toggle, {
				container: "body",
				boundary: "viewport",
				popperConfig: {
					modifiers: [
						{
							name: "preventOverflow",
							options: {
								boundary: "viewport",
							},
						},
					],
				},
			});

			toggle.addEventListener("show.bs.dropdown", () => {
				const dropdownMenu = toggle.nextElementSibling;
				if (dropdownMenu?.classList.contains("dropdown-menu")) {
					document.body.appendChild(dropdownMenu);
				}
			});
		}
	},
};

if (typeof window !== "undefined") {
	window.DropdownUtils = DropdownUtils;
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { DropdownUtils };
}
