/**
 * Share Action Manager
 * Handles all sharing-related actions and user management
 */
class ShareActionManager {
	/**
	 * Initialize share action manager
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.itemUuid = config.itemUuid;
		this.itemType = config.itemType;
		this.permissions = config.permissions;
		this.searchTimeout = null;
		this.currentRequest = null;
		this.selectedUsersMap = {}; // key: input id, value: array of {name, email}
		this.pendingRemovals = new Set(); // Track users marked for removal
		this.pendingPermissionChanges = new Map(); // Track permission level changes

		this.initializeEventListeners();
	}

	/**
	 * Initialize event listeners
	 */
	initializeEventListeners() {
		this.setupRemoveUserButtons();
		this.setupModalEventHandlers();
	}

	/**
	 * Setup modal event handlers
	 */
	setupModalEventHandlers() {
		// Find the specific modal for this item
		let modal = document.getElementById(`share-modal-${this.itemUuid}`);
		if (!modal) {
			// Try alternative modal IDs
			const alternativeModalIds = [
				"manageMembersModal",
				`modal-${this.itemUuid}`,
				`${this.itemType}-modal`,
			];

			for (const id of alternativeModalIds) {
				modal = document.getElementById(id);
				if (modal) break;
			}
		}

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
		if (typeof setupNotifyCheckbox === "function") {
			const notifyCheckbox = document.getElementById(
				`notify-users-checkbox-${this.itemUuid}`,
			);
			const textareaContainer = document.getElementById(
				`notify-message-textarea-container-${this.itemUuid}`,
			);

			if (notifyCheckbox && textareaContainer) {
				setupNotifyCheckbox(this.itemUuid);
			}
		}
	}

	/**
	 * Setup search input
	 * @param {Element} input - Search input element
	 */
	setupSearchInput(input) {
		// Prevent duplicate event listener attachment
		if (input.dataset.searchSetup === "true") {
			return;
		}
		input.dataset.searchSetup = "true";

		const dropdown = this.getDropdownForInput(input);
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
				e.preventDefault();
				e.stopPropagation();
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

	/**
	 * Setup share item button
	 * @param {Element} shareButton - Share button element
	 */
	setupShareItem(shareButton) {
		// Prevent duplicate event listener attachment
		if (shareButton.dataset.shareSetup === "true") {
			return;
		}
		shareButton.dataset.shareSetup = "true";

		shareButton.addEventListener("click", async () => {
			await this.handleShareItem();
		});
	}

	/**
	 * Handle share item action
	 */
	async handleShareItem() {
		// Get the user emails from the selected users map
		const inputId = `user-search-${this.itemUuid}`;
		const selectedUsers = this.selectedUsersMap[inputId] || [];

		// Create a map of user emails to their permission levels
		const userPermissions = {};
		for (const user of selectedUsers) {
			userPermissions[user.email] = user.permission_level || "viewer";
		}

		const userEmails = selectedUsers.map((u) => u.email).join(",");

		const formData = {
			"user-search": userEmails,
			user_permissions: JSON.stringify(userPermissions),
		};

		// Add notify_users and notify_message if present
		const notifyCheckbox = document.getElementById(
			`notify-users-checkbox-${this.itemUuid}`,
		);
		if (notifyCheckbox?.checked) {
			formData.notify_users = "1";
			const messageTextarea = document.getElementById(
				`notify-message-textarea-${this.itemUuid}`,
			);
			if (messageTextarea?.value.trim()) {
				formData.notify_message = messageTextarea.value.trim();
			}
		}

		// Handle pending removals
		if (this.pendingRemovals.size > 0) {
			formData.remove_users = JSON.stringify(Array.from(this.pendingRemovals));
		}

		// Handle pending permission changes
		if (
			this.pendingPermissionChanges &&
			this.pendingPermissionChanges.size > 0
		) {
			formData.permission_changes = JSON.stringify(
				Array.from(this.pendingPermissionChanges.entries()),
			);
		}

		try {
			const response = await window.APIClient.post(
				`/users/share-item/${this.itemType}/${this.itemUuid}/`,
				formData,
			);

			if (response.success) {
				// Show success message
				this.showToast(
					response.message || `${this.itemType} shared successfully!`,
					"success",
				);

				// Close modal
				this.closeModal();

				// Reload the page to ensure everything is consistent
				window.location.reload();
			} else {
				// Show error message
				const errorMessage =
					response.error ||
					response.message ||
					`Error sharing ${this.itemType}`;
				this.showToast(errorMessage, "danger");
			}
		} catch (error) {
			console.error(`Error sharing ${this.itemType}:`, error);
			this.showToast(
				`Error sharing ${this.itemType}. Please try again.`,
				"danger",
			);
		}
	}

	/**
	 * Search users
	 * @param {string} query - Search query
	 * @param {Element} dropdown - Dropdown element
	 */
	async searchUsers(query, dropdown) {
		// Cancel previous request if still pending
		if (this.currentRequest) {
			this.currentRequest.abort();
		}

		try {
			this.currentRequest = new AbortController();
			const users = await window.APIClient.get(
				`/users/share-item/${this.itemType}/${this.itemUuid}/`,
				{ q: query, limit: 10 },
				null, // No loading state for search
			);
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

	/**
	 * Display search results
	 * @param {Array} users - User results
	 * @param {Element} dropdown - Dropdown element
	 * @param {string} query - Search query
	 */
	displayResults(users, dropdown, query) {
		const listGroup = dropdown.querySelector(".list-group");

		if (users.length === 0) {
			listGroup.innerHTML =
				'<div class="list-group-item no-results">No users or groups found</div>';
		} else {
			const items = users
				.map((user) => {
					const isGroup = user.type === "group";
					const icon = isGroup
						? "bi-people-fill text-info"
						: "bi-person-fill text-primary";
					const subtitle = isGroup
						? `<div class="user-email">Group • ${user.member_count} members</div>`
						: `<div class="user-email">${this.highlightMatch(user.email, query)}</div>`;

					return `
					<div class="list-group-item"
						 data-user-id="${window.HTMLInjectionManager.escapeHtml(user.url || "")}"
						 data-user-name="${window.HTMLInjectionManager.escapeHtml(user.name)}"
						 data-user-email="${window.HTMLInjectionManager.escapeHtml(user.email)}"
						 data-user-type="${window.HTMLInjectionManager.escapeHtml(user.type || "user")}"
						 data-member-count="${user.member_count || 0}">
						<div class="user-search-item">
							<div class="user-name">
								<i class="bi ${icon} me-2"></i>
								${this.highlightMatch(user.name, query)}
							</div>
							${subtitle}
						</div>
					</div>
				`;
				})
				.join("");

			window.HTMLInjectionManager.injectHTML(listGroup, items, {
				escape: false,
			});
		}

		this.showDropdown(dropdown);
	}

	/**
	 * Display error in dropdown
	 * @param {Element} dropdown - Dropdown element
	 */
	displayError(dropdown) {
		const listGroup = dropdown.querySelector(".list-group");
		listGroup.innerHTML =
			'<div class="list-group-item no-results">Error loading users</div>';
		this.showDropdown(dropdown);
	}

	/**
	 * Highlight search matches
	 * @param {string} text - Text to highlight
	 * @param {string} query - Search query
	 * @returns {string} Highlighted text
	 */
	highlightMatch(text, query) {
		if (!query) return window.HTMLInjectionManager.escapeHtml(text);
		const regex = new RegExp(`(${query})`, "gi");
		return window.HTMLInjectionManager.escapeHtml(text).replace(
			regex,
			"<mark>$1</mark>",
		);
	}

	/**
	 * Navigate dropdown with keyboard
	 * @param {NodeList} items - Dropdown items
	 * @param {number} currentIndex - Current selected index
	 * @param {number} direction - Direction to navigate
	 */
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

	/**
	 * Select user from dropdown
	 * @param {Element} item - Selected item
	 * @param {Element} input - Search input
	 */
	selectUser(item, input) {
		const userName = item.dataset.userName;
		const userEmail = item.dataset.userEmail;
		const userType = item.dataset.userType || "user";
		const inputId = input.id;

		if (!this.selectedUsersMap[inputId]) {
			this.selectedUsersMap[inputId] = [];
		}

		// Check if this user is already part of a selected group
		if (userType === "user") {
			const selectedGroups = this.selectedUsersMap[inputId].filter(
				(u) => u.type === "group",
			);
			for (const group of selectedGroups) {
				// Check if this user is in the group by making an API call
				this.checkUserInGroup(userEmail, group, input, userName);
				return; // Exit early, we'll handle the result in the callback
			}
		}

		if (!this.selectedUsersMap[inputId].some((u) => u.email === userEmail)) {
			// Create user object with all available data
			const userData = {
				name: userName,
				email: userEmail,
				type: userType,
				permission_level: "viewer", // Default permission level
			};

			// For groups, get member count from dataset attribute
			if (userType === "group") {
				const memberCount = item.dataset.memberCount;
				if (memberCount) {
					userData.member_count = Number.parseInt(memberCount, 10);
				}
			}

			this.selectedUsersMap[inputId].push(userData);
			this.renderChips(input);
		}

		input.value = "";
		this.hideDropdown(item.closest(".user-search-dropdown"));
		input.focus();
	}

	/**
	 * Check if user is in group
	 * @param {string} userEmail - User email
	 * @param {Object} group - Group object
	 * @param {Element} input - Search input
	 * @param {string} userName - User name
	 */
	async checkUserInGroup(userEmail, group, input, userName) {
		try {
			// Extract group UUID from group.email (format: "group:uuid")
			const groupUuid = group.email.replace("group:", "");

			// Make API call to check if user is in the group
			const data = await window.APIClient.get("/users/share-groups/", {
				group_uuid: groupUuid,
			});

			if (data.success && data.members) {
				const isUserInGroup = data.members.some(
					(member) => member.email === userEmail,
				);

				if (isUserInGroup) {
					// User is already in the group, show notification and don't add
					this.showToast(
						`${userName} is already part of the group "${group.name}"`,
						"warning",
					);
					input.value = "";
					this.hideDropdown(input.closest(".user-search-dropdown"));
					input.focus();
					return;
				}
			}

			// If we get here, user is not in the group, so add them normally
			if (!this.selectedUsersMap[input.id].some((u) => u.email === userEmail)) {
				this.selectedUsersMap[input.id].push({
					name: userName,
					email: userEmail,
					type: "user",
					permission_level: "viewer", // Default permission level
				});
				this.renderChips(input);
			}

			input.value = "";
			this.hideDropdown(input.closest(".user-search-dropdown"));
			input.focus();
		} catch (error) {
			console.error("Error checking if user is in group:", error);
			// If there's an error, just add the user normally
			if (!this.selectedUsersMap[input.id].some((u) => u.email === userEmail)) {
				this.selectedUsersMap[input.id].push({
					name: userName,
					email: userEmail,
					type: "user",
					permission_level: "viewer", // Default permission level
				});
				this.renderChips(input);
			}

			input.value = "";
			this.hideDropdown(input.closest(".user-search-dropdown"));
			input.focus();
		}
	}

	/**
	 * Render user chips
	 * @param {Element} input - Search input
	 */
	renderChips(input) {
		const inputId = input.id;

		// Try to find the chip container
		let chipContainer = input
			.closest(".user-search-input-container")
			.querySelector(".selected-users-chips");

		// If not found, try to find it in the permissions section
		if (!chipContainer) {
			chipContainer = input
				.closest("form")
				.querySelector(
					".selected-users-permissions-section .selected-users-chips",
				);
		}

		if (!chipContainer) {
			console.warn("Chip container not found for input:", inputId);
			return;
		}

		chipContainer.innerHTML = "";
		for (const user of this.selectedUsersMap[inputId]) {
			const chip = window.HTMLInjectionManager.createUserChip(user, {
				showPermissionSelect: true,
				showRemoveButton: true,
				permissionLevels: ["viewer", "contributor", "co-owner"],
			});

			window.HTMLInjectionManager.injectHTML(chipContainer, chip, {
				escape: false,
			});

			// Add click handler for removal
			const removeBtn = chipContainer
				.querySelector(`[data-user-email="${user.email}"]`)
				.closest(".user-chip")
				.querySelector(".remove-chip");
			if (removeBtn) {
				removeBtn.onclick = () => {
					this.selectedUsersMap[inputId] = this.selectedUsersMap[
						inputId
					].filter((u) => u.email !== user.email);
					this.renderChips(input);
				};
			}

			// Add change handler for permission level
			const permissionSelect = chipContainer.querySelector(
				`[data-user-email="${user.email}"]`,
			);
			if (permissionSelect) {
				permissionSelect.onchange = (e) => {
					// Update the user's permission level in the selectedUsersMap
					const userIndex = this.selectedUsersMap[inputId].findIndex(
						(u) => u.email === user.email,
					);
					if (userIndex !== -1) {
						this.selectedUsersMap[inputId][userIndex].permission_level =
							e.target.value;
					}
				};
			}
		}

		// Toggle notify/message and users-with-access sections
		this.toggleModalSections(inputId);
	}

	/**
	 * Toggle modal sections based on selections
	 * @param {string} inputId - Input ID
	 */
	toggleModalSections(inputId) {
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
			// Show notify section, hide users with access section
			if (notifySection) notifySection.classList.remove("d-none");
			if (usersWithAccessSection)
				usersWithAccessSection.classList.add("d-none");
			if (modalDivider) modalDivider.classList.add("d-none");

			// Clear pending removals when adding new users
			this.pendingRemovals.clear();

			// Reset all dropdown buttons to their original state
			const modal = document.getElementById(`share-modal-${itemUuid}`);
			if (modal) {
				for (const button of modal.querySelectorAll(".btn-icon-dropdown")) {
					button.innerHTML =
						'<i class="bi bi-three-dots-vertical" aria-hidden="true"></i>';
					button.classList.remove("btn-outline-danger");
					button.classList.add("btn-light");
					button.disabled = false;
				}
			}

			// Change button text to "Share"
			if (saveBtn) saveBtn.textContent = "Share";

			// Setup notify checkbox functionality
			if (typeof setupNotifyCheckbox === "function") {
				setTimeout(() => {
					setupNotifyCheckbox(itemUuid);
				}, 10);
			}
		} else {
			// Hide notify section, show users with access section
			if (notifySection) notifySection.classList.add("d-none");
			if (usersWithAccessSection)
				usersWithAccessSection.classList.remove("d-none");
			if (modalDivider) modalDivider.classList.remove("d-none");

			// Change button text back to "Save"
			if (saveBtn) saveBtn.textContent = "Save";
		}

		// Update save button state
		this.updateSaveButtonState(itemUuid);
	}

	/**
	 * Update save button state
	 * @param {string} itemUuid - Item UUID
	 */
	updateSaveButtonState(itemUuid) {
		const inputId = `user-search-${itemUuid}`;
		const selectedUsers = this.selectedUsersMap[inputId] || [];
		const hasSelectedUsers = selectedUsers.length > 0;
		const hasPendingRemovals = this.pendingRemovals.size > 0;
		const hasPendingPermissionChanges =
			this.pendingPermissionChanges && this.pendingPermissionChanges.size > 0;

		const saveBtn = document.getElementById(`share-item-btn-${itemUuid}`);
		const pendingMessage = document.getElementById(
			`pending-changes-message-${itemUuid}`,
		);

		// Update save button
		if (saveBtn) {
			if (
				hasSelectedUsers ||
				hasPendingRemovals ||
				hasPendingPermissionChanges
			) {
				saveBtn.disabled = false;
			} else {
				saveBtn.disabled = true;
			}
		}

		// Update pending message
		if (pendingMessage) {
			if (hasPendingRemovals || hasPendingPermissionChanges) {
				pendingMessage.classList.remove("d-none");
			} else {
				pendingMessage.classList.add("d-none");
			}
		}
	}

	/**
	 * Setup remove user buttons
	 */
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

		// Setup permission change buttons for this specific modal only
		modal.addEventListener("click", async (e) => {
			if (e.target.closest(".permission-change-btn")) {
				await this.handlePermissionChange(e);
			}
		});
	}

	/**
	 * Handle permission change
	 * @param {Event} e - Click event
	 */
	async handlePermissionChange(e) {
		const button = e.target.closest(".permission-change-btn");
		const userEmail = button.dataset.userEmail;
		const userName = button.dataset.userName;
		const itemUuid = button.dataset.itemUuid;
		const itemType = button.dataset.itemType;
		const permissionLevel = button.dataset.permissionLevel;

		if (!userEmail || !itemUuid || !itemType || !permissionLevel) {
			console.error(
				"Missing user email, item UUID, item type, or permission level",
			);
			return;
		}

		// Update the dropdown button text and icon to reflect the change
		const dropdown = button.closest(".dropdown");
		const dropdownButton = dropdown.querySelector(".access-level-dropdown");
		const currentPermission = dropdownButton.getAttribute(
			"data-current-permission",
		);

		// Don't do anything if selecting the same permission
		if (permissionLevel === currentPermission) {
			return;
		}

		// Update the dropdown button text and icon
		const iconClass =
			this.permissions.getPermissionIcon(permissionLevel);
		dropdownButton.innerHTML = `<i class="bi ${iconClass} me-1"></i>${permissionLevel.charAt(0).toUpperCase() + permissionLevel.slice(1)}`;
		dropdownButton.setAttribute("data-current-permission", permissionLevel);

		// Update checkmarks in dropdown menu
		this.updateDropdownMenu(dropdown, button);

		// Update user text for removal case
		if (permissionLevel === "remove") {
			this.markUserForRemoval(userEmail, userName);
		} else {
			this.clearUserRemovalMarking(userEmail);
		}

		// Handle permission level change
		if (permissionLevel !== "remove") {
			this.handlePermissionLevelChange(
				userEmail,
				userName,
				itemUuid,
				itemType,
				permissionLevel,
			);
		}

		// Update save button state
		this.updateSaveButtonState(itemUuid);

		// Close the dropdown
		const bsDropdown = bootstrap.Dropdown.getInstance(dropdownButton);
		if (bsDropdown) {
			bsDropdown.hide();
		}
	}

	/**
	 * Update dropdown menu
	 * @param {Element} dropdown - Dropdown element
	 * @param {Element} clickedButton - Clicked button
	 */
	updateDropdownMenu(dropdown, clickedButton) {
		const dropdownMenu = dropdown.querySelector(".access-level-menu");
		const allPermissionBtns = dropdownMenu.querySelectorAll(
			".permission-change-btn",
		);

		// Remove selected class and checkmarks from all buttons
		for (const btn of allPermissionBtns) {
			btn.classList.remove("selected");
			const checkmark = btn.querySelector(".bi-check");
			if (checkmark) {
				checkmark.remove();
			}
		}

		// Add selected class and checkmark to the clicked button
		clickedButton.classList.add("selected");
		const checkmark = document.createElement("i");
		checkmark.className = "bi bi-check ms-auto";
		clickedButton.appendChild(checkmark);
	}

	/**
	 * Mark user for removal
	 * @param {string} userEmail - User email
	 * @param {string} userName - User name
	 */
	markUserForRemoval(userEmail, userName) {
		this.pendingRemovals.add(userEmail);

		// Remove from permission changes if it was there
		if (this.pendingPermissionChanges?.has(userEmail)) {
			this.pendingPermissionChanges.delete(userEmail);
		}

		// Update user text styling
		const userRow = document
			.querySelector(`[data-user-email="${userEmail}"]`)
			.closest("tr");
		const userNameElement = userRow.querySelector("h5");
		if (userNameElement) {
			userNameElement.style.textDecoration = "line-through";
			userNameElement.style.opacity = "0.6";
		}
	}

	/**
	 * Clear user removal marking
	 * @param {string} userEmail - User email
	 */
	clearUserRemovalMarking(userEmail) {
		this.pendingRemovals.delete(userEmail);

		// Clear any existing text decoration or opacity
		const userRow = document
			.querySelector(`[data-user-email="${userEmail}"]`)
			.closest("tr");
		const userNameElement = userRow.querySelector("h5");
		if (userNameElement) {
			userNameElement.style.textDecoration = "none";
			userNameElement.style.opacity = "1";
		}
	}

	/**
	 * Handle permission level change
	 * @param {string} userEmail - User email
	 * @param {string} userName - User name
	 * @param {string} itemUuid - Item UUID
	 * @param {string} itemType - Item type
	 * @param {string} permissionLevel - New permission level
	 */
	handlePermissionLevelChange(
		userEmail,
		userName,
		itemUuid,
		itemType,
		permissionLevel,
	) {
		// Store the permission change
		if (!this.pendingPermissionChanges) {
			this.pendingPermissionChanges = new Map();
		}
		this.pendingPermissionChanges.set(userEmail, {
			userName: userName,
			itemUuid: itemUuid,
			itemType: itemType,
			permissionLevel: permissionLevel,
		});
	}

	/**
	 * Get dropdown for input
	 * @param {Element} input - Input element
	 * @returns {Element|null} Dropdown element
	 */
	getDropdownForInput(input) {
		// First try the original pattern: user-search-dropdown-{uuid}
		let dropdown = document.getElementById(
			`user-search-dropdown-${input.id.replace("user-search-", "")}`,
		);

		if (dropdown) {
			return dropdown;
		}

		// Try alternative patterns
		const alternativeIds = [
			`user-search-dropdown-${this.itemUuid}`,
			"user-search-dropdown",
			`${input.id.replace("user-search-", "user-search-dropdown-")}`,
			`${input.id}-dropdown`,
		];

		for (const id of alternativeIds) {
			dropdown = document.getElementById(id);
			if (dropdown) {
				return dropdown;
			}
		}

		// If still not found, look for any dropdown in the same container
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
	 * Show dropdown
	 * @param {Element} dropdown - Dropdown element
	 */
	showDropdown(dropdown) {
		dropdown.classList.remove("d-none");
	}

	/**
	 * Hide dropdown
	 * @param {Element} dropdown - Dropdown element
	 */
	hideDropdown(dropdown) {
		dropdown.classList.add("d-none");
		// Clear any selections
		for (const item of dropdown.querySelectorAll(".list-group-item")) {
			item.classList.remove("selected");
		}
	}

	/**
	 * Close modal
	 */
	closeModal() {
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
	}

	/**
	 * Clear selections
	 */
	clearSelections() {
		// Clear selected users
		this.selectedUsersMap = {};

		// Clear pending removals
		this.pendingRemovals.clear();

		// Clear pending permission changes
		if (this.pendingPermissionChanges) {
			this.pendingPermissionChanges.clear();
		}

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
			const itemUuid = checkbox.id.replace("notify-users-checkbox-", "");
			if (typeof setupNotifyCheckbox === "function") {
				setupNotifyCheckbox(itemUuid);
			}
		}
		for (const textarea of document.querySelectorAll(
			'[id^="notify-message-textarea-"]',
		)) {
			textarea.value = "";
		}
	}

	/**
	 * Get permission button text with icon (legacy method)
	 * @param {string} permissionLevel - Permission level
	 * @returns {string} Button text with icon
	 */
	getPermissionButtonText(permissionLevel) {
		// Handle undefined/null permission levels
		const level =
			!permissionLevel || typeof permissionLevel !== "string"
				? "viewer"
				: permissionLevel;

		const iconClass =
			this.permissions?.getPermissionIcon(level) ||
			"bi-question-circle";
		const displayText = level.charAt(0).toUpperCase() + level.slice(1);
		return `<i class="bi ${iconClass} me-1"></i>${displayText}`;
	}

	/**
	 * Show toast notification - Wrapper for global showAlert
	 * @param {string} message - Toast message
	 * @param {string} type - Toast type (success, danger, warning, info)
	 */
	showToast(message, type = "success") {
		// Map ShareActionManager types to showAlert types
		const mappedType = type === "danger" ? "error" : type;

		// Use the global showAlert function from HTMLInjectionManager
		if (window.showAlert) {
			window.showAlert(message, mappedType);
		} else {
			console.error("Global showAlert function not available");
		}
	}
}

// Make class available globally
window.ShareActionManager = ShareActionManager;

// Export for ES6 modules (Jest testing)
export { ShareActionManager };
