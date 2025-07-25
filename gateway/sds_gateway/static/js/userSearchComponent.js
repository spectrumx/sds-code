// User search functionality for item sharing (datasets, captures, etc.)
class UserSearchHandler {
	constructor() {
		this.itemUuid = null;
		this.itemType = null;
		this.searchTimeout = null;
		this.currentRequest = null;
		this.selectedUsersMap = {}; // key: input id, value: array of {name, email}
		this.pendingRemovals = new Set(); // Track users marked for removal
	}

	getCSRFToken() {
		// Try to get CSRF token from meta tag first
		const metaToken = document.querySelector('meta[name="csrf-token"]');
		if (metaToken) {
			return metaToken.getAttribute("content");
		}

		// Fallback to input field
		const inputToken = document.querySelector('[name="csrfmiddlewaretoken"]');
		if (inputToken) {
			return inputToken.value;
		}

		// If still not found, try to get from cookie
		const cookieToken = this.getCookie("csrftoken");
		if (cookieToken) {
			return cookieToken;
		}

		console.error("CSRF token not found");
		return "";
	}

	getCookie(name) {
		let cookieValue = null;
		if (document.cookie && document.cookie !== "") {
			const cookies = document.cookie.split(";");
			for (let i = 0; i < cookies.length; i++) {
				const cookie = cookies[i].trim();
				if (cookie.substring(0, name.length + 1) === `${name}=`) {
					cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
					break;
				}
			}
		}
		return cookieValue;
	}

	setItemInfo(uuid, type) {
		this.itemUuid = uuid;
		this.itemType = type;
	}

	init() {
		if (!this.itemUuid || !this.itemType) {
			console.error(
				"Cannot initialize UserSearchHandler: item UUID and type not set",
			);
			return;
		}

		this.setupRemoveUserButtons();

		// Clear any existing search results when initializing
		this.clearSearchResults();

		// Setup modal-specific event handlers
		this.setupModalEventHandlers();
	}

	setupModalEventHandlers() {
		// Find the specific modal for this item
		const modal = document.getElementById(`share-modal-${this.itemUuid}`);
		if (!modal) {
			console.error(`Modal not found for ${this.itemType}: ${this.itemUuid}`);
			return;
		}

		// Setup search input for this specific modal
		const searchInput = modal.querySelector(".user-search-input");
		if (searchInput) {
			this.setupSearchInput(searchInput);
		}

		// Setup share button for this specific modal
		const shareButton = document.getElementById(
			`share-item-btn-${this.itemUuid}`,
		);
		if (shareButton) {
			this.setupShareItem(shareButton);
		}

		// Setup notify checkbox functionality
		setupNotifyCheckbox(this.itemUuid);
	}

	clearSearchResults() {
		// Clear all search dropdowns
		for (const dropdown of document.querySelectorAll(".user-search-dropdown")) {
			dropdown.classList.add("d-none");
			const listGroup = dropdown.querySelector(".list-group");
			if (listGroup) {
				listGroup.innerHTML = "";
			}
		}

		// Clear search inputs
		for (const input of document.querySelectorAll(".user-search-input")) {
			input.value = "";
		}
	}

	setupSearchInput(input) {
		// Prevent duplicate event listener attachment
		if (input.dataset.searchSetup === "true") {
			return;
		}
		input.dataset.searchSetup = "true";

		const dropdown = document.getElementById(
			`user-search-dropdown-${input.id.replace("user-search-", "")}`,
		);
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

	setupShareItem(shareButton) {
		// Prevent duplicate event listener attachment
		if (shareButton.dataset.shareSetup === "true") {
			return;
		}
		shareButton.dataset.shareSetup = "true";

		shareButton.addEventListener("click", async () => {
			// get the user emails from the selected users map
			// The selectedUsersMap is keyed by input ID, so we need to get the first (and only) array
			const inputId = `user-search-${this.itemUuid}`;

			const selectedUsers = this.selectedUsersMap[inputId] || [];

			const userEmails = selectedUsers.map((u) => u.email).join(",");

			// Get CSRF token
			const csrfToken = this.getCSRFToken();

			const formData = new FormData();
			formData.append("user-search", userEmails);

			// Add notify_users and notify_message if present
			const notifyCheckbox = document.getElementById(
				`notify-users-checkbox-${this.itemUuid}`,
			);
			if (notifyCheckbox?.checked) {
				formData.append("notify_users", "1");
				const messageTextarea = document.getElementById(
					`notify-message-textarea-${this.itemUuid}`,
				);
				if (messageTextarea?.value.trim()) {
					formData.append("notify_message", messageTextarea.value.trim());
				}
			}

			// Handle pending removals
			if (this.pendingRemovals.size > 0) {
				formData.append(
					"remove_users",
					JSON.stringify(Array.from(this.pendingRemovals)),
				);
			}

			try {
				const response = await fetch(
					`/users/share-item/${this.itemType}/${this.itemUuid}/`,
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
					showToast(
						result.message || `${this.itemType} shared successfully!`,
						"success",
					);
					// Close modal
					const modal = document.getElementById(`share-modal-${this.itemUuid}`);
					const bootstrapModal = bootstrap.Modal.getInstance(modal);
					if (bootstrapModal) {
						bootstrapModal.hide();
					}

					// Manually remove backdrop if it remains
					const backdrop = document.querySelector(".modal-backdrop");
					if (backdrop) {
						backdrop.remove();
					}

					// Remove modal-open class from body
					document.body.classList.remove("modal-open");
					document.body.style.overflow = "";
					document.body.style.paddingRight = "";

					// Clear selected users and pending removals
					this.selectedUsersMap = {};
					this.pendingRemovals.clear();

					// Refresh the appropriate list based on item type
					await this.refreshItemList();
				} else {
					// Show error message
					showToast(result.error || `Error sharing ${this.itemType}`, "danger");
				}
			} catch (error) {
				console.error(`Error sharing ${this.itemType}:`, error);
				showToast(
					`Error sharing ${this.itemType}. Please try again.`,
					"danger",
				);
			}
		});
	}

	async searchUsers(query, dropdown) {
		if (!this.itemUuid || !this.itemType) {
			console.error("Item UUID and type not set on UserSearchHandler");
			return;
		}

		// Cancel previous request if still pending
		if (this.currentRequest) {
			this.currentRequest.abort();
		}
		try {
			this.currentRequest = new AbortController();
			const response = await fetch(
				`/users/share-item/${this.itemType}/${this.itemUuid}/?q=${encodeURIComponent(query)}&limit=10`,
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

			// Add click event listeners to the dropdown items
			const input = document.getElementById(`user-search-${this.itemUuid}`);
			for (const item of listGroup.querySelectorAll(".list-group-item")) {
				item.addEventListener("click", () => {
					this.selectUser(item, input);
				});
			}
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
		let newIndex;
		if (currentIndex === -1) {
			// No item is currently selected
			if (direction > 0) {
				// ArrowDown: start from first item
				newIndex = 0;
			} else {
				// ArrowUp: start from last item
				newIndex = items.length - 1;
			}
		} else {
			// An item is currently selected
			newIndex = currentIndex + direction;
			if (newIndex < 0) newIndex = items.length - 1;
			if (newIndex >= items.length) newIndex = 0;
		}

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

		// Toggle notify/message and users-with-access sections
		const itemUuid = inputId.replace("user-search-", "");
		const notifySection = document.getElementById(
			`notify-message-section-${itemUuid}`,
		);
		const usersWithAccessSection = document.getElementById(
			`users-with-access-section-${itemUuid}`,
		);
		const saveBtn = document.getElementById(`share-item-btn-${itemUuid}`);
		const modalDivider = document.querySelector(
			`#share-modal-${itemUuid} .modal-divider`,
		);

		if (
			this.selectedUsersMap[inputId] &&
			this.selectedUsersMap[inputId].length > 0
		) {
			notifySection.classList.remove("d-none");
			usersWithAccessSection.classList.add("d-none");

			// Hide the modal divider when chips are present
			if (modalDivider) {
				modalDivider.classList.add("d-none");
			}

			// Clear pending removals when adding new users
			this.pendingRemovals.clear();

			// Reset all dropdown buttons to their original state
			const modal = document.getElementById(`share-modal-${itemUuid}`);
			for (const button of modal.querySelectorAll(".btn-icon-dropdown")) {
				button.innerHTML =
					'<i class="bi bi-three-dots-vertical" aria-hidden="true"></i>';
				button.classList.remove("btn-outline-danger");
				button.classList.add("btn-light");
				button.disabled = false;
			}

			// Change button text to "Share"
			saveBtn.textContent = "Share";

			// Setup notify checkbox functionality with a small delay to ensure DOM is updated
			setTimeout(() => {
				setupNotifyCheckbox(itemUuid);
			}, 10);
		} else {
			notifySection.classList.add("d-none");
			usersWithAccessSection.classList.remove("d-none");

			// Show the modal divider when no chips are present
			if (modalDivider) {
				modalDivider.classList.remove("d-none");
			}

			// Change button text back to "Save"
			saveBtn.textContent = "Save";
		}

		// Update save button state
		this.updateSaveButtonState(itemUuid);
	}

	updateSaveButtonState(itemUuid) {
		const inputId = `user-search-${itemUuid}`;
		const selectedUsers = this.selectedUsersMap[inputId] || [];
		const hasSelectedUsers = selectedUsers.length > 0;
		const hasPendingRemovals = this.pendingRemovals.size > 0;

		const saveBtn = document.getElementById(`share-item-btn-${itemUuid}`);
		const pendingMessage = document.getElementById(
			`pending-changes-message-${itemUuid}`,
		);

		if (hasSelectedUsers || hasPendingRemovals) {
			saveBtn.disabled = false;
			if (hasPendingRemovals) {
				pendingMessage.classList.remove("d-none");
			} else {
				pendingMessage.classList.add("d-none");
			}
		} else {
			saveBtn.disabled = true;
			pendingMessage.classList.add("d-none");
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

	resetAll() {
		// Clear selected users
		this.selectedUsersMap = {};

		// Clear pending removals
		this.pendingRemovals.clear();

		// Reset all dropdown buttons to their original state
		for (const button of document.querySelectorAll(".btn-icon-dropdown")) {
			button.innerHTML =
				'<i class="bi bi-three-dots-vertical" aria-hidden="true"></i>';
			button.classList.remove("btn-outline-danger");
			button.classList.add("btn-light");
			button.disabled = false;
		}

		// Reset save button state for all modals
		for (const btn of document.querySelectorAll('[id^="share-item-btn-"]')) {
			btn.disabled = true;
			btn.textContent = "Save";
		}

		// Hide pending changes messages
		for (const msg of document.querySelectorAll(
			'[id^="pending-changes-message-"]',
		)) {
			msg.classList.add("d-none");
		}

		// Clear chips
		for (const container of document.querySelectorAll(
			".selected-users-chips",
		)) {
			container.innerHTML = "";
		}

		// Hide notify sections and show users-with-access sections
		for (const section of document.querySelectorAll(
			'[id^="notify-message-section-"]',
		)) {
			section.classList.add("d-none");
		}
		for (const section of document.querySelectorAll(
			'[id^="users-with-access-section-"]',
		)) {
			section.classList.remove("d-none");
		}

		// Show modal dividers
		for (const divider of document.querySelectorAll(".modal-divider")) {
			divider.classList.remove("d-none");
		}

		// Clear search inputs
		for (const input of document.querySelectorAll(".user-search-input")) {
			input.value = "";
		}

		// Hide dropdowns and clear their content
		for (const dropdown of document.querySelectorAll(".user-search-dropdown")) {
			dropdown.classList.add("d-none");
			const listGroup = dropdown.querySelector(".list-group");
			if (listGroup) {
				listGroup.innerHTML = "";
			}
		}

		// Reset notify checkboxes and textareas
		for (const checkbox of document.querySelectorAll(
			'[id^="notify-users-checkbox-"]',
		)) {
			checkbox.checked = true;
			// Get the item UUID from the checkbox ID and setup the notify functionality
			const itemUuid = checkbox.id.replace("notify-users-checkbox-", "");
			setupNotifyCheckbox(itemUuid);
		}
		for (const textarea of document.querySelectorAll(
			'[id^="notify-message-textarea-"]',
		)) {
			textarea.value = "";
		}
	}

	setupRemoveUserButtons() {
		// Find the specific modal for this item
		const modal = document.getElementById(`share-modal-${this.itemUuid}`);
		if (!modal) {
			console.error(`Modal not found for ${this.itemType}: ${this.itemUuid}`);
			return;
		}

		// Prevent duplicate event listener attachment
		if (modal.dataset.removeButtonsSetup === "true") {
			return;
		}
		modal.dataset.removeButtonsSetup = "true";

		// Setup remove access buttons for this specific modal only
		modal.addEventListener("click", async (e) => {
			if (e.target.closest(".remove-access-btn")) {
				const button = e.target.closest(".remove-access-btn");
				const userEmail = button.dataset.userEmail;
				const userName = button.dataset.userName;
				const itemUuid = button.dataset.itemUuid;
				const itemType = button.dataset.itemType;

				if (!userEmail || !itemUuid || !itemType) {
					console.error("Missing user email, item UUID, or item type");
					return;
				}

				// Add to pending removals
				this.pendingRemovals.add(userEmail);

				// Update the button to show "Remove Access" is selected
				const dropdownMenu = button.closest(".dropdown-menu");
				const dropdownButton = dropdownMenu.previousElementSibling;

				// Change the dropdown button to show "Remove Access" is selected
				dropdownButton.innerHTML =
					'<i class="bi bi-person-slash text-danger"></i>';
				dropdownButton.classList.add("btn-outline-danger");
				dropdownButton.classList.remove("btn-light");

				// Disable the dropdown to prevent further changes
				dropdownButton.disabled = true;

				// Close the dropdown menu
				const dropdownToggle = dropdownButton;
				if (dropdownToggle?.classList.contains("dropdown-toggle")) {
					const dropdownMenu = dropdownToggle.nextElementSibling;
					if (dropdownMenu?.classList.contains("dropdown-menu")) {
						dropdownMenu.classList.remove("show");
						dropdownToggle.setAttribute("aria-expanded", "false");
					}
				}

				// Update save button state
				this.updateSaveButtonState(itemUuid);
			}
		});
	}

	async refreshItemList() {
		try {
			// Get current URL parameters
			const urlParams = new URLSearchParams(window.location.search);
			const currentPage = urlParams.get("page") || "1";
			const sortBy = urlParams.get("sort_by") || "created_at";
			const sortOrder = urlParams.get("sort_order") || "desc";

			// Determine the appropriate URL based on item type
			let refreshUrl;
			if (this.itemType === "dataset") {
				refreshUrl = `/users/dataset-list/?page=${currentPage}&sort_by=${sortBy}&sort_order=${sortOrder}`;
			} else if (this.itemType === "capture") {
				refreshUrl = `/users/file-list/?page=${currentPage}&sort_by=${sortBy}&sort_order=${sortOrder}`;
			} else {
				console.error(`Unknown item type: ${this.itemType}`);
				return;
			}

			// Fetch updated list
			const response = await fetch(refreshUrl, {
				headers: {
					"X-Requested-With": "XMLHttpRequest",
				},
			});

			if (response.ok) {
				const html = await response.text();

				// Create a temporary div to parse the HTML
				const tempDiv = document.createElement("div");
				tempDiv.innerHTML = html;

				// Update the main content area
				const mainContent = document.querySelector("main");
				const newMainContent = tempDiv.querySelector("main");

				if (mainContent && newMainContent) {
					// Update the main content
					mainContent.innerHTML = newMainContent.innerHTML;

					// Re-initialize any necessary event listeners
					this.initializeItemListEventListeners();

					// Re-initialize modals and their handlers
					this.initializeModals();
				}
			}
		} catch (error) {
			console.error(`Error refreshing ${this.itemType} list:`, error);
			// Fallback to page reload if refresh fails
			location.reload();
		}
	}

	initializeModals() {
		// Re-create UserSearchHandler for each share modal
		for (const modal of document.querySelectorAll(".modal[data-item-uuid]")) {
			const itemUuid = modal.getAttribute("data-item-uuid");
			const itemType = modal.getAttribute("data-item-type");
			if (window.UserSearchHandler) {
				const handler = new window.UserSearchHandler();
				// Store the handler on the modal element
				modal.userSearchHandler = handler;
			}

			// On modal show, set the item info and call init()
			modal.addEventListener("show.bs.modal", () => {
				if (modal.userSearchHandler) {
					modal.userSearchHandler.setItemInfo(itemUuid, itemType);
					modal.userSearchHandler.init();
				}
			});

			// On modal hide, reset all selections and entered data
			modal.addEventListener("hidden.bs.modal", () => {
				if (modal.userSearchHandler) {
					modal.userSearchHandler.resetAll();
				}
			});
		}
	}

	initializeItemListEventListeners() {
		// Re-attach event listeners for the updated item list
		// This ensures the share buttons and other interactions still work

		// Re-initialize sort functionality
		const sortableHeaders = document.querySelectorAll("th.sortable");
		for (const header of sortableHeaders) {
			header.style.cursor = "pointer";
			header.addEventListener("click", () => {
				const sortField = header.getAttribute("data-sort");
				const urlParams = new URLSearchParams(window.location.search);
				let newOrder = "desc";

				// If already sorting by this field, toggle order
				if (
					urlParams.get("sort_by") === sortField &&
					urlParams.get("sort_order") === "asc"
				) {
					newOrder = "desc";
				}

				// Update URL with new sort parameters
				urlParams.set("sort_by", sortField);
				urlParams.set("sort_order", newOrder);
				urlParams.set("page", "1"); // Reset to first page when sorting

				// Navigate to sorted results
				window.location.search = urlParams.toString();
			});
		}

		// Re-initialize download buttons (only for datasets)
		if (this.itemType === "dataset") {
			const downloadButtons = document.querySelectorAll(
				".download-dataset-btn",
			);
			for (const button of downloadButtons) {
				button.addEventListener("click", (e) => {
					e.preventDefault();
					e.stopPropagation();

					const datasetUuid = button.getAttribute("data-dataset-uuid");
					const datasetName = button.getAttribute("data-dataset-name");

					// Update modal content
					document.getElementById("downloadDatasetName").textContent =
						datasetName;

					// Show the modal
					openCustomModal("downloadModal");

					// Handle confirm download
					document.getElementById("confirmDownloadBtn").onclick = () => {
						// Close modal first
						closeCustomModal("downloadModal");

						// Show loading state
						button.innerHTML =
							'<i class="bi bi-hourglass-split"></i> Processing...';
						button.disabled = true;

						// Make API request
						fetch(`/users/download-item/dataset/${datasetUuid}/`, {
							method: "POST",
							headers: {
								"Content-Type": "application/json",
								"X-CSRFToken": this.getCSRFToken(),
							},
						})
							.then((response) => {
								// Check if response is JSON
								const contentType = response.headers.get("content-type");
								if (contentType?.includes("application/json")) {
									return response.json();
								}
								// If not JSON, throw an error with the response text
								return response.text().then((text) => {
									throw new Error(`Server returned non-JSON response: ${text}`);
								});
							})
							.then((data) => {
								if (data.success === true) {
									button.innerHTML =
										'<i class="bi bi-check-circle text-success"></i> Download Requested';
									showAlert(
										data.message ||
											"Download request submitted successfully! You will receive an email when ready.",
										"success",
									);
								} else {
									button.innerHTML =
										'<i class="bi bi-exclamation-triangle text-danger"></i> Request Failed';
									showAlert(
										data.message ||
											"Download request failed. Please try again.",
										"error",
									);
								}
							})
							.catch((error) => {
								console.error("Download error:", error);
								button.innerHTML =
									'<i class="bi bi-exclamation-triangle text-danger"></i> Request Failed';
								showAlert(
									error.message ||
										"An error occurred while processing your request.",
									"error",
								);
							})
							.finally(() => {
								// Reset button after 3 seconds
								setTimeout(() => {
									button.innerHTML = "Download";
									button.disabled = false;
								}, 3000);
							});
					};
				});
			}
		}
	}
}

window.UserSearchHandler = UserSearchHandler;

// Toast utility for notifications
function showToast(message, type = "success") {
	const toastContainer = document.getElementById("toast-container");
	if (!toastContainer) return;
	const toastId = `toast-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
	const bgClass =
		type === "success" ? "bg-success text-white" : "bg-danger text-white";
	const toastHtml = `
        <div id="${toastId}" class="toast align-items-center ${bgClass}" role="alert" aria-live="assertive" aria-atomic="true" data-bs-delay="3500">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
	toastContainer.insertAdjacentHTML("beforeend", toastHtml);
	const toastElem = document.getElementById(toastId);
	const toast = new bootstrap.Toast(toastElem);
	toast.show();
	toastElem.addEventListener("hidden.bs.toast", () => toastElem.remove());
}

// Add logic to show/hide textarea based on notify checkbox
function setupNotifyCheckbox(itemUuid) {
	const notifyCheckbox = document.getElementById(
		`notify-users-checkbox-${itemUuid}`,
	);
	const textareaContainer = document.getElementById(
		`notify-message-textarea-container-${itemUuid}`,
	);

	if (!notifyCheckbox || !textareaContainer) {
		console.error("Missing elements for setupNotifyCheckbox:", {
			itemUuid,
			notifyCheckbox: !!notifyCheckbox,
			textareaContainer: !!textareaContainer,
		});
		return;
	}

	function toggleTextarea() {
		if (notifyCheckbox.checked) {
			textareaContainer.classList.add("show");
		} else {
			textareaContainer.classList.remove("show");
		}
	}

	// Remove any existing event listeners to prevent duplicates
	notifyCheckbox.removeEventListener("change", toggleTextarea);
	notifyCheckbox.addEventListener("change", toggleTextarea);

	// Call toggleTextarea immediately to set initial state
	toggleTextarea();
}
