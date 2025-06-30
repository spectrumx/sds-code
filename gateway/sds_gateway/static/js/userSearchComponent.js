// User search functionality for dataset sharing
class UserSearchHandler {
	constructor() {
		this.datasetUuid = null;
		this.searchTimeout = null;
		this.currentRequest = null;
		this.selectedUsersMap = {}; // key: input id, value: array of {name, email}
		this.init();
	}

	setDatasetUuid(uuid) {
		this.datasetUuid = uuid;
	}

	init() {
		// Initialize user search for all modals
		document.addEventListener("DOMContentLoaded", () => {
			this.setupUserSearch();
		});

		// Handle modal show events for dynamically loaded content
		document.addEventListener("shown.bs.modal", (event) => {
			const modal = event.target;
			const searchInput = modal.querySelector(".user-search-input");
			if (searchInput) {
				this.setupSearchInput(searchInput);
			}

			const shareButton = document.getElementById(
				`share-dataset-btn-${this.datasetUuid}`,
			);
			if (shareButton) {
				this.setupShareDataset(shareButton);
			}
		});
	}

	setupUserSearch() {
		const searchInputs = document.querySelectorAll(".user-search-input");
		for (const input of searchInputs) {
			this.setupSearchInput(input);
		}
	}

	setupSearchInput(input) {
		const dropdown = document.getElementById(
			`user-search-dropdown-${input.id.replace("user-search-", "")}`,
		);
		const chipContainer = input
			.closest(".user-search-input-container")
			.querySelector(".selected-users-chips");
		const form = input.closest("form");
		const inputId = input.id;
		if (!this.selectedUsersMap[inputId]) this.selectedUsersMap[inputId] = [];

		// Debounced search on input
		input.addEventListener("input", (e) => {
			clearTimeout(this.searchTimeout);
			const query = e.target.value.trim();

			if (query.length < 2) {
				this.hideDropdown(dropdown);
				return;
			}

			this.searchTimeout = setTimeout(() => {
				this.searchUsers(query, dropdown);
			}, 300);
		});

		// Handle keyboard navigation
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
					this.navigateDropdown(visibleItems, currentIndex, 1);
					break;
				case "ArrowUp":
					e.preventDefault();
					this.navigateDropdown(visibleItems, currentIndex, -1);
					break;
				case "Enter": {
					e.preventDefault();
					const selectedItem = dropdown.querySelector(
						".list-group-item.selected",
					);
					if (selectedItem) {
						this.selectUser(selectedItem, input);
					}
					break;
				}
				case "Escape":
					this.hideDropdown(dropdown);
					input.blur();
					break;
			}
		});

		// Handle clicks outside to close dropdown
		document.addEventListener("click", (e) => {
			if (!input.contains(e.target) && !dropdown.contains(e.target)) {
				this.hideDropdown(dropdown);
			}
		});

		// Handle dropdown item clicks
		dropdown.addEventListener("click", (e) => {
			const item = e.target.closest(".list-group-item");
			if (item && !item.classList.contains("no-results")) {
				this.selectUser(item, input);
			}
		});

		// On form submit, set input value to comma-separated emails
		form.addEventListener("submit", (e) => {
			input.value = this.selectedUsersMap[inputId]
				.map((u) => u.email)
				.join(",");
		});
	}

	setupShareDataset(shareButton) {
		shareButton.addEventListener("click", async () => {
			// get the user emails from the selected users map
			// The selectedUsersMap is keyed by input ID, so we need to get the first (and only) array
			const inputId = `user-search-${this.datasetUuid}`;

			const selectedUsers = this.selectedUsersMap[inputId] || [];

			const userEmails = selectedUsers.map((u) => u.email).join(",");

			if (!userEmails) {
				alert("Please select at least one user to share with.");
				return;
			}

			// Get CSRF token from the form
			const form = document.getElementById(`share-form-${this.datasetUuid}`);
			const csrfToken = form.querySelector(
				'input[name="csrfmiddlewaretoken"]',
			).value;

			const formData = new FormData();
			formData.append("user-search", userEmails);

			try {
				const response = await fetch(
					`/users/share-dataset/${this.datasetUuid}/`,
					{
						method: "POST",
						body: formData,
						headers: {
							"X-CSRFToken": csrfToken,
						},
					},
				);

				const result = await response.json();

				if (response.ok) {
					// Show success message
					alert(result.message || "Dataset shared successfully!");
					// Close modal
					const modal = document.getElementById(
						`share-modal-${this.datasetUuid}`,
					);
					const bootstrapModal = bootstrap.Modal.getInstance(modal);
					if (bootstrapModal) {
						bootstrapModal.hide();
					}
					// Clear selected users
					this.selectedUsersMap = {};
					// Reload page to show updated shared users
					location.reload();
				} else {
					// Show error message
					alert(result.error || "Error sharing dataset");
				}
			} catch (error) {
				console.error("Error sharing dataset:", error);
				alert("Error sharing dataset. Please try again.");
			}
		});
	}

	async searchUsers(query, dropdown) {
		if (!this.datasetUuid) {
			console.error("Dataset UUID not set on UserSearchHandler");
			return;
		}
		// Cancel previous request if still pending
		if (this.currentRequest) {
			this.currentRequest.abort();
		}
		try {
			this.currentRequest = new AbortController();
			const response = await fetch(
				`/users/share-dataset/${this.datasetUuid}/?q=${encodeURIComponent(query)}&limit=10`,
				{
					signal: this.currentRequest.signal,
					headers: {
						"X-Requested-With": "XMLHttpRequest",
					},
				},
			);
			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}
			const users = await response.json();
			this.displayResults(users, dropdown, query);
		} catch (error) {
			if (error.name === "AbortError") {
				return;
			}
			console.error("Error searching users:", error);
			this.displayError(dropdown);
		} finally {
			this.currentRequest = null;
		}
	}

	displayResults(users, dropdown, query) {
		const listGroup = dropdown.querySelector(".list-group");

		if (users.length === 0) {
			listGroup.innerHTML =
				'<div class="list-group-item no-results">No users found</div>';
		} else {
			listGroup.innerHTML = users
				.map(
					(user) => `
                <div class="list-group-item" data-user-id="${user.url}" data-user-name="${user.name}" data-user-email="${user.email}">
                    <div class="user-search-item">
                        <div class="user-name">${this.highlightMatch(user.name, query)}</div>
                        <div class="user-email">${this.highlightMatch(user.email, query)}</div>
                    </div>
                </div>
            `,
				)
				.join("");
		}

		this.showDropdown(dropdown);
	}

	displayError(dropdown) {
		const listGroup = dropdown.querySelector(".list-group");
		listGroup.innerHTML =
			'<div class="list-group-item no-results">Error loading users</div>';
		this.showDropdown(dropdown);
	}

	highlightMatch(text, query) {
		if (!query) return text;
		const regex = new RegExp(`(${query})`, "gi");
		return text.replace(regex, "<mark>$1</mark>");
	}

	navigateDropdown(items, currentIndex, direction) {
		// Remove current selection
		for (const item of items) {
			item.classList.remove("selected");
		}

		// Calculate new index
		let newIndex = currentIndex + direction;
		if (newIndex < 0) newIndex = items.length - 1;
		if (newIndex >= items.length) newIndex = 0;

		// Add selection to new item
		if (items[newIndex]) {
			items[newIndex].classList.add("selected");
			items[newIndex].scrollIntoView({ block: "nearest" });
		}
	}

	selectUser(item, input) {
		const userName = item.dataset.userName;
		const userEmail = item.dataset.userEmail;
		const inputId = input.id;

		if (!this.selectedUsersMap[inputId]) {
			this.selectedUsersMap[inputId] = [];
		}

		if (!this.selectedUsersMap[inputId].some((u) => u.email === userEmail)) {
			this.selectedUsersMap[inputId].push({ name: userName, email: userEmail });
			this.renderChips(input);
		}

		input.value = "";
		this.hideDropdown(item.closest(".user-search-dropdown"));
		input.focus();
	}

	renderChips(input) {
		const inputId = input.id;
		const chipContainer = input
			.closest(".user-search-input-container")
			.querySelector(".selected-users-chips");
		chipContainer.innerHTML = "";
		for (const user of this.selectedUsersMap[inputId]) {
			const chip = document.createElement("span");
			chip.className = "user-chip";
			chip.textContent = user.email;
			const remove = document.createElement("span");
			remove.className = "remove-chip";
			remove.innerHTML = "&times;";
			remove.onclick = () => {
				this.selectedUsersMap[inputId] = this.selectedUsersMap[inputId].filter(
					(u) => u.email !== user.email,
				);
				this.renderChips(input);
			};
			chip.appendChild(remove);
			chipContainer.appendChild(chip);
		}
	}

	showDropdown(dropdown) {
		dropdown.classList.remove("d-none");
	}

	hideDropdown(dropdown) {
		dropdown.classList.add("d-none");
		// Clear any selections
		for (const item of dropdown.querySelectorAll(".list-group-item")) {
			item.classList.remove("selected");
		}
	}
}

window.UserSearchHandler = UserSearchHandler;

export { UserSearchHandler };
