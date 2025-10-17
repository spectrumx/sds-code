/**
 * Share Group Manager
 * Handles all share group operations including creating, managing members, and deleting groups
 * Refactored to use core components and centralized management
 */
class ShareGroupManager {
	/**
	 * Initialize share group manager
	 * @param {Object} config - Configuration object
	 */
	constructor(config = {}) {
		this.currentGroupUuid = null;
		this.currentGroupName = null;
		this.pendingDeleteGroupUuid = null;
		this.pendingDeleteGroupName = null;
		this.pendingRemovals = new Set();
		this.shareGroupUserSearchHandler = null;

		// Configuration
		this.config = {
			apiEndpoint: config.apiEndpoint || "/users/share-groups/",
			...config,
		};

		this.initializeEventListeners();
	}

	/**
	 * Initialize all event listeners
	 */
	initializeEventListeners() {
		this.initializeCreateGroupForm();
		this.initializeAddMembersForm();
		this.initializeManageMembersModal();
		this.initializeSaveButton();
		this.initializeDeleteGroupConfirmation();
		this.initializeShareGroupUserSearch();
	}

	/**
	 * Initialize create group form
	 */
	initializeCreateGroupForm() {
		const createGroupForm = document.getElementById("createGroupForm");
		if (!createGroupForm) {
			console.error("Create group form not found");
			return;
		}

		createGroupForm.addEventListener("submit", (e) => {
			e.preventDefault();
			this.handleCreateGroup(createGroupForm);
		});
	}

	/**
	 * Handle create group form submission
	 * @param {HTMLFormElement} form - Form element
	 */
	async handleCreateGroup(form) {
		const groupName = document.getElementById("groupName").value;

		if (!groupName.trim()) {
			this.showAlert("Group name is required", "error");
			return;
		}

		const formData = new URLSearchParams();
		formData.append("action", "create");
		formData.append("name", groupName);

		try {
			const response = await window.APIClient.request(this.config.apiEndpoint, {
				method: "POST",
				headers: {
					"Content-Type": "application/x-www-form-urlencoded",
				},
				body: formData,
			});

			if (response.success) {
				// Show success message
				this.showAlert(response.message, "success");

				// Close the create modal
				const createModal = bootstrap.Modal.getInstance(
					document.getElementById("createGroupModal"),
				);
				createModal.hide();

				// Clear the form
				document.getElementById("groupName").value = "";

				// Add the new group to the table dynamically
				this.addNewGroupToTable(response.group);

				// Automatically open the manage modal for the new group
				setTimeout(() => {
					this.openManageModalForGroup(
						response.group.uuid,
						response.group.name,
					);
				}, 500);
			} else {
				this.showAlert(response.error, "error");
			}
		} catch (error) {
			// Extract specific error message from the response
			let errorMessage = "An error occurred while creating the group.";
			if (error.data?.error) {
				errorMessage = error.data.error;
			} else if (error.message?.includes("400")) {
				errorMessage =
					"Bad request - please check the form data and try again.";
			}

			this.showAlert(errorMessage, "error");
		}
	}

	/**
	 * Initialize add members form
	 */
	initializeAddMembersForm() {
		const addMembersForm = document.getElementById("addMembersForm");
		if (!addMembersForm) return;

		addMembersForm.addEventListener("submit", (e) => {
			e.preventDefault();
			this.handleAddMembers(addMembersForm);
		});
	}

	/**
	 * Handle add members form submission
	 * @param {HTMLFormElement} form - Form element
	 */
	async handleAddMembers(form) {
		const inputId = "user-search-sharegroup";
		const selectedUsers = this.shareGroupUserSearchHandler
			? this.shareGroupUserSearchHandler.selectedUsersMap[inputId] || []
			: [];

		if (selectedUsers.length === 0) {
			this.showAlert("Please select at least one user to add.", "error");
			return;
		}

		const userEmails = selectedUsers.map((user) => user.email).join(",");

		const formData = new URLSearchParams();
		formData.append("action", "add_members");
		formData.append("group_uuid", this.currentGroupUuid);
		formData.append("user_emails", userEmails);

		try {
			const response = await window.APIClient.request(this.config.apiEndpoint, {
				method: "POST",
				headers: {
					"Content-Type": "application/x-www-form-urlencoded",
				},
				body: formData,
			});

			if (response.success) {
				// Show success message in toast
				this.showAlert(response.message, "success");

				// Show any errors as warnings
				if (response.errors && response.errors.length > 0) {
					for (const error of response.errors) {
						this.showAlert(error, "warning");
					}
				}

				if (this.shareGroupUserSearchHandler) {
					this.shareGroupUserSearchHandler.resetShareGroup();
				}
				// Clear pending removals when members are added
				this.pendingRemovals.clear();
				this.loadCurrentMembers();
				this.updateSaveButtonState();

				// Update table member info by adding the new members
				if (response.added_users && response.added_users.length > 0) {
					this.updateTableMemberEmails(
						this.currentGroupUuid,
						response.added_users,
						"add",
					);
				}
			} else {
				this.showAlert(response.error, "error");
			}
		} catch (error) {
			// Extract specific error message from the response
			let errorMessage = "An error occurred while adding members.";
			if (error.data?.error) {
				errorMessage = error.data.error;
			}

			this.showAlert(errorMessage, "error");
		}
	}

	/**
	 * Initialize manage members modal
	 */
	initializeManageMembersModal() {
		const manageMembersModal = document.getElementById(
			"share-modal-sharegroup",
		);
		if (manageMembersModal) {
			manageMembersModal.addEventListener("show.bs.modal", (event) => {
				const button = event.relatedTarget;
				// Only proceed if the button exists and has the required data attributes
				if (!button || !button.hasAttribute("data-group-uuid")) {
					return;
				}
				this.currentGroupUuid = button.getAttribute("data-group-uuid");
				this.currentGroupName = button.getAttribute("data-group-name");

				document.getElementById("addGroupUuid").value = this.currentGroupUuid;

				// Update modal title
				document.getElementById("manageMembersModalLabel").innerHTML =
					`<i class="bi bi-person-plus me-2"></i>Manage Members: ${this.currentGroupName}`;

				// Clear pending removals when opening modal
				this.pendingRemovals.clear();

				// Reset user search handler state
				if (this.shareGroupUserSearchHandler) {
					this.shareGroupUserSearchHandler.resetShareGroup();
				}

				// Load current members
				this.loadCurrentMembers();

				// Load and display shared assets information
				this.loadSharedAssetsInfo();
			});

			// Also handle modal hidden event to reset state
			manageMembersModal.addEventListener("hidden.bs.modal", () => {
				// Reset user search handler state (but don't destroy it)
				if (this.shareGroupUserSearchHandler) {
					this.shareGroupUserSearchHandler.resetShareGroup();
				}
				// Clear current group info
				this.currentGroupUuid = null;
				this.currentGroupName = null;
				// Clear pending removals
				this.pendingRemovals.clear();
				// Reset save button state
				this.updateSaveButtonState();
				// Hide shared assets section
				const sharedAssetsSection = document.getElementById(
					"sharedAssetsSection",
				);
				if (sharedAssetsSection) {
					sharedAssetsSection.classList.add("d-none");
				}
			});
		}
	}

	/**
	 * Initialize save button
	 */
	initializeSaveButton() {
		const saveBtn = document.getElementById("save-sharegroup-btn");
		if (saveBtn) {
			saveBtn.addEventListener("click", () => this.handleSaveButton(saveBtn));
		}
	}

	/**
	 * Handle save button click
	 * @param {HTMLButtonElement} button - Save button element
	 */
	async handleSaveButton(button) {
		const originalText = button.innerHTML;
		button.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
		button.disabled = true;

		// Handle pending removals
		if (this.pendingRemovals.size > 0) {
			const formData = new URLSearchParams();
			formData.append("action", "remove_members");
			formData.append("group_uuid", this.currentGroupUuid);
			formData.append(
				"user_emails",
				Array.from(this.pendingRemovals).join(","),
			);

			try {
				const response = await window.APIClient.request(
					this.config.apiEndpoint,
					{
						method: "POST",
						headers: {
							"Content-Type": "application/x-www-form-urlencoded",
						},
						body: formData,
					},
				);

				if (response.success) {
					// Show success message in toast
					this.showAlert(response.message, "success");

					// Show any errors as warnings
					if (response.errors && response.errors.length > 0) {
						for (const error of response.errors) {
							this.showAlert(error, "warning");
						}
					}

					// Clear pending removals
					this.pendingRemovals.clear();
					// Reset all remove buttons
					this.resetRemoveButtons();
					// Reload members
					this.loadCurrentMembers();

					// Update table member info by removing the members
					if (response.removed_users && response.removed_users.length > 0) {
						this.updateTableMemberEmails(
							this.currentGroupUuid,
							response.removed_users,
							"remove",
						);
					}
				} else {
					this.showAlert(response.error, "error");
				}
			} catch (error) {
				// Extract specific error message from the response
				let errorMessage = "An error occurred while removing members.";
				if (error.data?.error) {
					errorMessage = error.data.error;
				}

				this.showAlert(errorMessage, "error");
			} finally {
				button.innerHTML = originalText;
				button.disabled = false;
				this.updateSaveButtonState();
			}
		}
	}

	/**
	 * Initialize delete group confirmation
	 */
	initializeDeleteGroupConfirmation() {
		const confirmDeleteBtn = document.getElementById("confirmDeleteGroup");
		if (confirmDeleteBtn) {
			confirmDeleteBtn.addEventListener("click", () =>
				this.handleDeleteGroup(confirmDeleteBtn),
			);
		}
	}

	/**
	 * Handle delete group confirmation
	 * @param {HTMLButtonElement} button - Delete button element
	 */
	async handleDeleteGroup(button) {
		if (!this.pendingDeleteGroupUuid) {
			return;
		}
		const originalText = button.innerHTML;
		button.innerHTML = '<i class="bi bi-hourglass-split"></i> Deleting...';
		button.disabled = true;

		const formData = new URLSearchParams();
		formData.append("action", "delete_group");
		formData.append("group_uuid", this.pendingDeleteGroupUuid);

		try {
			const response = await window.APIClient.request(this.config.apiEndpoint, {
				method: "POST",
				headers: {
					"Content-Type": "application/x-www-form-urlencoded",
				},
				body: formData,
			});

			// Hide the confirmation modal
			const deleteModal = bootstrap.Modal.getInstance(
				document.getElementById("deleteGroupModal"),
			);
			deleteModal.hide();

			if (response.success) {
				// Store success message for after page reload
				localStorage.setItem("shareGroupSuccessMessage", response.message);
				setTimeout(() => window.location.reload(), 1000);
			} else {
				this.showAlert(response.error, "error");
			}
		} catch (error) {
			// Extract specific error message from the response
			let errorMessage = "An error occurred while deleting the group.";
			if (error.data?.error) {
				errorMessage = error.data.error;
			}

			this.showAlert(errorMessage, "error");
		} finally {
			// Reset button state
			button.innerHTML = originalText;
			button.disabled = false;

			// Clear pending deletion data
			this.pendingDeleteGroupUuid = null;
			this.pendingDeleteGroupName = null;
		}
	}

	/**
	 * Load current members for a group
	 */
	async loadCurrentMembers() {
		if (!this.currentGroupUuid) return;

		const membersList = document.getElementById("currentMembers");

		// Clear member count and show loading state
		const memberCountElement = document.getElementById("memberCount");
		if (memberCountElement) {
			memberCountElement.textContent = "";
		}

		// Show loading state using table_rows template
		await window.DOMUtils.renderTable(
			membersList,
			[
				{
					cells: [
						{
							html: '<div class="text-center text-muted"><i class="bi bi-people"></i><p class="mb-0">Loading members...</p></div>',
							css_class: "p-2 shadow-sm",
						},
					],
				},
			],
			{
				empty_message: "",
				empty_colspan: 1,
			},
		);

		try {
			const response = await window.APIClient.request(
				`${this.config.apiEndpoint}?group_uuid=${this.currentGroupUuid}`,
				{
					headers: {
						"X-Requested-With": "XMLHttpRequest",
					},
				},
			);

			if (response.success) {
				// Render members using generic table_rows template
				try {
					const rows = response.members.map((member) => ({
						cells: [
							{
								html: `
								<div class="row">
									<div class="col-md-10">
										<div>
											<h5 class="mb-1">${member.name || "No name"}</h5>
											<p class="mb-0">
												<small class="text-muted">${member.email}</small>
											</p>
										</div>
									</div>
								</div>
							`,
							},
						],
						actions: [
							{
								label: "Remove",
								icon: "bi-person-slash",
								css_class: "btn-outline-danger",
								extra_class: "remove-member-btn",
								data_attrs: {
									user_email: member.email,
									user_name: member.name || "No name",
								},
								onclick: `shareGroupManager.removeMemberFromGroup(event, '${member.email}', '${member.name || "No name"}')`,
							},
						],
					}));

					await window.DOMUtils.renderTable(membersList, rows, {
						empty_message: "No members in this group",
						empty_colspan: 1,
					});
				} catch (renderError) {
					console.error("Error rendering members:", renderError);
					membersList.innerHTML =
						'<tr><td class="p-2 shadow-sm"><div class="text-center text-danger">Error loading members</div></td></tr>';
				}

				// Update member count
				const memberCountElement = document.getElementById("memberCount");
				if (memberCountElement) {
					if (response.members.length > 0) {
						memberCountElement.textContent = `${response.count} member${response.count !== 1 ? "s" : ""}`;
					} else {
						memberCountElement.textContent = "";
					}
				}

				// Update table member info
				if (response.members.length > 0) {
					this.updateTableMemberInfo(this.currentGroupUuid, response.members);
				}

				// Update save button state after loading members
				this.updateSaveButtonState();
			} else {
				// Show error state using centralized renderError
				const errorDiv = document.createElement("div");
				await window.DOMUtils.renderError(errorDiv, "Error loading members", {
					format: "alert",
					alert_type: "danger",
					icon: "exclamation-triangle",
				});
				membersList.innerHTML = `<tr><td class="p-2 shadow-sm">${errorDiv.innerHTML}</td></tr>`;
			}
		} catch (error) {
			// Show error state using centralized renderError
			const errorDiv = document.createElement("div");
			await window.DOMUtils.renderError(errorDiv, "Error loading members", {
				format: "alert",
				alert_type: "danger",
				icon: "exclamation-triangle",
			});
			membersList.innerHTML = `<tr><td class="p-2 shadow-sm">${errorDiv.innerHTML}</td></tr>`;
		}
	}

	/**
	 * Load shared assets info
	 */
	async loadSharedAssetsInfo() {
		if (!this.currentGroupUuid) {
			return;
		}

		// Create a temporary request to get shared assets info
		const formData = new URLSearchParams();
		formData.append("action", "get_shared_assets");
		formData.append("group_uuid", this.currentGroupUuid);

		try {
			const response = await window.APIClient.request(this.config.apiEndpoint, {
				method: "POST",
				headers: {
					"Content-Type": "application/x-www-form-urlencoded",
				},
				body: formData,
			});

			if (response.success) {
				this.displaySharedAssetsInfo(response.shared_assets);
			} else {
				console.error("Error loading shared assets:", response.error);
			}
		} catch (error) {
			console.error("Error loading shared assets:", error);
		}
	}

	/**
	 * Display shared assets info
	 * @param {Array} sharedAssets - Array of shared assets
	 */
	async displaySharedAssetsInfo(sharedAssets) {
		// Find the shared assets section in the modal
		const sharedAssetsSection = document.getElementById("sharedAssetsSection");

		if (!sharedAssetsSection) return;

		try {
			if (sharedAssets && sharedAssets.length > 0) {
				// Separate assets by type
				const datasets = sharedAssets
					.filter((asset) => asset.type === "dataset")
					.sort((a, b) => a.name.localeCompare(b.name));
				const captures = sharedAssets
					.filter((asset) => asset.type === "capture")
					.sort((a, b) => a.name.localeCompare(b.name));

				const totalDatasets = datasets.length;
				const totalCaptures = captures.length;

				// Show first 3 of each type
				const displayDatasets = datasets.slice(0, 3);
				const displayCaptures = captures.slice(0, 3);

				const hasMoreDatasets = totalDatasets > 3;
				const hasMoreCaptures = totalCaptures > 3;

				// Prepare context for template
				const context = {
					has_assets: true,
					datasets: displayDatasets,
					captures: displayCaptures,
					total_datasets: totalDatasets,
					total_captures: totalCaptures,
					show_datasets: displayDatasets.length > 0,
					show_captures: displayCaptures.length > 0,
					has_more_datasets: hasMoreDatasets,
					has_more_captures: hasMoreCaptures,
					remaining_datasets: totalDatasets - 3,
					remaining_captures: totalCaptures - 3,
				};

				const response = await window.APIClient.post("/users/render-html/", {
					template: "users/components/shared_assets_display.html",
					context: context,
				});

				if (response.html) {
					sharedAssetsSection.innerHTML = response.html;
					sharedAssetsSection.classList.remove("d-none");
				}
			} else {
				const response = await window.APIClient.post("/users/render-html/", {
					template: "users/components/shared_assets_display.html",
					context: { has_assets: false },
				});

				if (response.html) {
					sharedAssetsSection.innerHTML = response.html;
					sharedAssetsSection.classList.remove("d-none");
				}
			}
		} catch (error) {
			console.error("Error rendering shared assets:", error);
			sharedAssetsSection.innerHTML =
				'<div class="alert alert-danger">Error loading shared assets</div>';
			sharedAssetsSection.classList.remove("d-none");
		}
	}

	/**
	 * Delete Group Function - shows confirmation modal
	 * @param {string} groupUuid - Group UUID
	 * @param {string} groupName - Group name
	 */
	deleteGroup(groupUuid, groupName) {
		// Store the group info for confirmation
		this.pendingDeleteGroupUuid = groupUuid;
		this.pendingDeleteGroupName = groupName;

		// Update the confirmation modal content
		document.getElementById("deleteGroupName").textContent = groupName;

		// Hide any other open modals first
		const openModals = document.querySelectorAll(".modal.show");
		for (const modal of openModals) {
			const modalInstance = bootstrap.Modal.getInstance(modal);
			if (modalInstance) {
				modalInstance.hide();
			}
		}

		// Show the confirmation modal
		const deleteModalElement = document.getElementById("deleteGroupModal");
		if (!deleteModalElement) {
			console.error("Delete modal element not found");
			return;
		}

		// Check if modal instance already exists
		let deleteModal = bootstrap.Modal.getInstance(deleteModalElement);
		if (!deleteModal) {
			deleteModal = new bootstrap.Modal(deleteModalElement, {
				backdrop: true,
				keyboard: true,
				focus: true,
			});
		}

		deleteModal.show();
	}

	/**
	 * Initialize share group user search using ShareActionManager functionality
	 */
	initializeShareGroupUserSearch() {
		// Create a custom search handler for ShareGroup using ShareActionManager's methods
		this.shareGroupUserSearchHandler = {
			selectedUsersMap: {},
			searchTimeout: null,
			currentRequest: null,

			// Search users using ShareGroup endpoint
			searchUsers: async (query, dropdown) => {
				if (query.length < 2) {
					this.hideDropdown(dropdown);
					return;
				}

				// Cancel previous request if still pending
				if (this.shareGroupUserSearchHandler.currentRequest) {
					this.shareGroupUserSearchHandler.currentRequest.abort();
				}

				try {
					this.shareGroupUserSearchHandler.currentRequest =
						new AbortController();
					const response = await window.APIClient.get(
						`${this.config.apiEndpoint}?q=${encodeURIComponent(query)}&group_uuid=${this.currentGroupUuid}`,
						{},
						null, // No loading state for search
					);

					if (Array.isArray(response)) {
						this.shareGroupUserSearchHandler.displayResults(
							response,
							dropdown,
							query,
						);
					} else {
						this.hideDropdown(dropdown);
					}
				} catch (error) {
					if (error.name === "AbortError") {
						return;
					}
					console.error("Search error:", error);
					this.shareGroupUserSearchHandler.displayError(dropdown);
				} finally {
					this.shareGroupUserSearchHandler.currentRequest = null;
				}
			},

			// Display search results (adapted from ShareActionManager)
			displayResults: async (users, dropdown, query) => {
				const listGroup = dropdown.querySelector(".list-group");

				// Use server-side rendering for user results
				try {
					const response = await window.APIClient.post("/users/render-html/", {
						template: "users/components/user_search_results.html",
						context: { users: users },
					});

					if (response.html) {
						listGroup.innerHTML = response.html;
					}
				} catch (error) {
					console.error("Error rendering user search results:", error);
					listGroup.innerHTML =
						'<div class="list-group-item no-results">Error loading users</div>';
				}

				this.showDropdown(dropdown);
			},

			// Display error (adapted from ShareActionManager)
			displayError: (dropdown) => {
				const listGroup = dropdown.querySelector(".list-group");
				listGroup.innerHTML =
					'<div class="list-group-item no-results">Error loading users</div>';
				this.showDropdown(dropdown);
			},

			// Select user from dropdown
			selectUser: (item, input) => {
				const userName = item.dataset.userName;
				const userEmail = item.dataset.userEmail;
				const inputId = input.id;

				if (!this.shareGroupUserSearchHandler.selectedUsersMap[inputId]) {
					this.shareGroupUserSearchHandler.selectedUsersMap[inputId] = [];
				}

				// Check if user is already selected
				if (
					!this.shareGroupUserSearchHandler.selectedUsersMap[inputId].some(
						(u) => u.email === userEmail,
					)
				) {
					this.shareGroupUserSearchHandler.selectedUsersMap[inputId].push({
						name: userName,
						email: userEmail,
					});
					this.shareGroupUserSearchHandler.renderChips(input);
				}

				// Clear the input field
				input.value = "";
				this.hideDropdown(item.closest(".user-search-dropdown"));
				input.focus();

				// Update save button state for share group
				this.updateSaveButtonState();
			},

			// Render user chips
			renderChips: (input) => {
				const inputId = input.id;
				const chipContainer = input
					.closest(".user-search-input-container")
					.querySelector(".selected-users-chips");

				if (!chipContainer) {
					console.warn("Chip container not found for input:", inputId);
					return;
				}

				chipContainer.innerHTML = "";
				for (const user of this.shareGroupUserSearchHandler.selectedUsersMap[
					inputId
				]) {
					const chip = document.createElement("span");
					chip.className = "user-chip";
					chip.textContent = user.email;
					const remove = document.createElement("span");
					remove.className = "remove-chip";
					remove.innerHTML = "&times;";
					remove.onclick = () => {
						this.shareGroupUserSearchHandler.selectedUsersMap[inputId] =
							this.shareGroupUserSearchHandler.selectedUsersMap[inputId].filter(
								(u) => u.email !== user.email,
							);
						this.shareGroupUserSearchHandler.renderChips(input);
						// Update save button state when removing chips
						this.updateSaveButtonState();
					};
					chip.appendChild(remove);
					chipContainer.appendChild(chip);
				}
			},

			// Reset share group state
			resetShareGroup: () => {
				// Clear selected users
				this.shareGroupUserSearchHandler.selectedUsersMap = {};

				// Clear input and chips
				const input = document.getElementById("user-search-sharegroup");
				if (input) {
					input.value = "";
					const chipContainer = input
						.closest(".user-search-input-container")
						.querySelector(".selected-users-chips");
					if (chipContainer) {
						chipContainer.innerHTML = "";
					}
				}

				// Update save button state
				this.updateSaveButtonState();
			},

			// Initialize search input (adapted from ShareActionManager)
			init: () => {
				const modal = document.getElementById("share-modal-sharegroup");
				if (!modal) {
					console.error("Modal not found for sharegroup");
					return;
				}

				// Setup search input
				const searchInput = modal.querySelector(".user-search-input");
				if (searchInput) {
					this.setupSearchInput(searchInput);
				}
			},
		};

		// Initialize the handler
		this.shareGroupUserSearchHandler.init();
	}

	/**
	 * Helper methods adapted from ShareActionManager
	 */

	/**
	 * Highlight search matches - No longer needed, server-side rendering handles this
	 * @param {string} text - Text to highlight
	 * @param {string} query - Search query
	 * @returns {string} Highlighted text
	 * @deprecated Server-side rendering now handles text display
	 */
	highlightMatch(text, query) {
		// This method is kept for backwards compatibility but is no longer used
		// Server-side rendering via Django templates handles all HTML generation
		console.warn(
			"highlightMatch is deprecated, use server-side rendering instead",
		);
		return text;
	}

	/**
	 * Setup search input with event listeners
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
		if (!this.shareGroupUserSearchHandler.selectedUsersMap[inputId]) {
			this.shareGroupUserSearchHandler.selectedUsersMap[inputId] = [];
		}

		// Debounced search on input
		input.addEventListener("input", (e) => {
			clearTimeout(this.shareGroupUserSearchHandler.searchTimeout);
			const query = e.target.value.trim();

			if (query.length < 2) {
				this.hideDropdown(dropdown);
				return;
			}

			this.shareGroupUserSearchHandler.searchTimeout = setTimeout(() => {
				this.shareGroupUserSearchHandler.searchUsers(query, dropdown);
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
						this.shareGroupUserSearchHandler.selectUser(selectedItem, input);
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
				this.shareGroupUserSearchHandler.selectUser(item, input);
			}
		});

		// On form submit, set input value to comma-separated emails
		if (form) {
			form.addEventListener("submit", (e) => {
				input.value = this.shareGroupUserSearchHandler.selectedUsersMap[inputId]
					.map((u) => u.email)
					.join(",");
			});
		}
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
			"user-search-dropdown-sharegroup",
			"user-search-dropdown",
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
	 * Show dropdown
	 * @param {Element} dropdown - Dropdown element
	 */
	showDropdown(dropdown) {
		if (dropdown) {
			dropdown.classList.remove("d-none");
		}
	}

	/**
	 * Hide dropdown
	 * @param {Element} dropdown - Dropdown element
	 */
	hideDropdown(dropdown) {
		if (dropdown) {
			dropdown.classList.add("d-none");
			// Clear any selections
			for (const item of dropdown.querySelectorAll(".list-group-item")) {
				item.classList.remove("selected");
			}
		}
	}

	/**
	 * Remove member from group (inline) - marks for pending removal
	 * @param {Event} event - Click event
	 * @param {string} email - User email
	 * @param {string} name - User name
	 */
	removeMemberFromGroup(event, email, name) {
		const button = event.target.closest(".remove-member-btn");
		if (!button) return;

		// Toggle removal state
		if (this.pendingRemovals.has(email)) {
			// Remove from pending removals
			this.pendingRemovals.delete(email);

			// Change button back to outline style
			button.innerHTML = '<i class="bi bi-person-slash me-1"></i>Remove';
			button.classList.remove("btn-danger");
			button.classList.add("btn-outline-danger");
		} else {
			// Add to pending removals
			this.pendingRemovals.add(email);

			// Change button to solid red style
			button.innerHTML = '<i class="bi bi-person-slash me-1"></i>Remove';
			button.classList.remove("btn-outline-danger");
			button.classList.add("btn-danger");
		}

		// Update save button state
		this.updateSaveButtonState();
	}

	/**
	 * Update save button state based on pending changes
	 */
	updateSaveButtonState() {
		const saveBtn = document.getElementById("save-sharegroup-btn");
		const pendingMessage = document.getElementById(
			"pending-changes-message-sharegroup",
		);
		const pendingMessageFooter = document.getElementById(
			"pending-changes-message-sharegroup-footer",
		);

		const hasSelectedUsers =
			this.shareGroupUserSearchHandler?.selectedUsersMap[
				"user-search-sharegroup"
			] &&
			this.shareGroupUserSearchHandler.selectedUsersMap[
				"user-search-sharegroup"
			].length > 0;
		const hasPendingRemovals = this.pendingRemovals.size > 0;

		if (saveBtn) {
			// Save button should only be enabled when there are pending removals
			// Adding members is handled by the "Add Members" button, not the save button
			if (hasPendingRemovals) {
				saveBtn.disabled = false;
			} else {
				saveBtn.disabled = true;
			}
		}

		// Update "Add Members" button state
		const addMembersBtn = document.getElementById("add-members-btn");
		if (addMembersBtn) {
			// Enable "Add Members" button when users are selected
			addMembersBtn.disabled = !hasSelectedUsers;
		}

		if (pendingMessage) {
			if (hasPendingRemovals) {
				pendingMessage.classList.remove("d-none");
			} else {
				pendingMessage.classList.add("d-none");
			}
		}

		if (pendingMessageFooter) {
			if (hasPendingRemovals) {
				pendingMessageFooter.classList.remove("d-none");
			} else {
				pendingMessageFooter.classList.add("d-none");
			}
		}
	}

	/**
	 * Reset all remove buttons to their original state
	 */
	resetRemoveButtons() {
		const buttons = document.querySelectorAll(".remove-member-btn");
		for (const button of buttons) {
			button.innerHTML = '<i class="bi bi-person-slash me-1"></i>Remove';
			button.classList.remove("btn-danger");
			button.classList.add("btn-outline-danger");
		}
	}

	/**
	 * Update member count and emails in the table
	 * @param {string} groupUuid - Group UUID
	 * @param {Array} members - Array of members
	 */
	updateTableMemberInfo(groupUuid, members) {
		const memberCountElement = document.querySelector(
			`.member-count[data-group-uuid="${groupUuid}"]`,
		);
		const memberEmailsElement = document.querySelector(
			`.member-emails[data-group-uuid="${groupUuid}"]`,
		);

		if (memberCountElement) {
			const count = members.length;
			memberCountElement.textContent = `${count} member${count !== 1 ? "s" : ""}`;
		}

		if (memberEmailsElement) {
			if (members.length === 0) {
				window.DOMUtils.hide(memberEmailsElement);
				memberEmailsElement.innerHTML = "";
			} else {
				window.DOMUtils.show(memberEmailsElement);
				const emails = members.slice(0, 3).map((member) => member.email);
				let emailsHtml = emails.join(", ");
				if (members.length > 3) {
					emailsHtml += `<span class="text-muted"> and ${members.length - 3} more</span>`;
				}
				memberEmailsElement.innerHTML = emailsHtml;
			}
		}
	}

	/**
	 * Update member emails list by adding or removing specific emails
	 * @param {string} groupUuid - Group UUID
	 * @param {Array} emails - Array of emails
	 * @param {string} action - Action type (add or remove)
	 */
	updateTableMemberEmails(groupUuid, emails, action) {
		const memberCountElement = document.querySelector(
			`.member-count[data-group-uuid="${groupUuid}"]`,
		);
		const memberEmailsElement = document.querySelector(
			`.member-emails[data-group-uuid="${groupUuid}"]`,
		);

		if (!memberCountElement || !memberEmailsElement) {
			return;
		}

		// Get current member count
		const currentCountText = memberCountElement.textContent;
		const currentCount = Number.parseInt(currentCountText.match(/(\d+)/)[1]);

		// Get current emails from the display
		let currentEmails = [];
		if (memberEmailsElement.style.display !== "none") {
			const emailsText = memberEmailsElement.textContent;
			// Extract emails from the text (remove "and X more" part)
			const emailsMatch = emailsText.match(
				/([^,]+(?:,[^,]+)*?)(?:\s+and\s+\d+\s+more)?$/,
			);
			if (emailsMatch) {
				currentEmails = emailsMatch[1].split(",").map((email) => email.trim());
			}
		}

		const newEmails = [...currentEmails];
		let newCount = currentCount;

		if (action === "add") {
			// Add new emails to the list
			for (const email of emails) {
				if (!newEmails.includes(email)) {
					newEmails.push(email);
					newCount++;
				}
			}
		} else if (action === "remove") {
			// Remove emails from the list
			for (const email of emails) {
				const index = newEmails.indexOf(email);
				if (index > -1) {
					newEmails.splice(index, 1);
					newCount--;
				}
			}
		}

		// Update the count
		memberCountElement.textContent = `${newCount} member${newCount !== 1 ? "s" : ""}`;

		// Update the emails display
		if (newCount === 0) {
			window.DOMUtils.hide(memberEmailsElement);
			memberEmailsElement.innerHTML = "";
		} else {
			window.DOMUtils.show(memberEmailsElement);
			const displayEmails = newEmails.slice(0, 3);
			let emailsHtml = displayEmails.join(", ");
			if (newEmails.length > 3) {
				emailsHtml += `<span class="text-muted"> and ${newEmails.length - 3} more</span>`;
			}
			memberEmailsElement.innerHTML = emailsHtml;
		}
	}

	/**
	 * Show Alert Function - Wrapper for global showAlert
	 * @param {string} message - Alert message
	 * @param {string} type - Alert type (info, success, warning, error)
	 */
	showAlert(message, type = "info") {
		// Use DOMUtils.showAlert for toast notifications
		if (window.DOMUtils) {
			window.DOMUtils.showAlert(message, type);
		} else {
			console.error("DOMUtils not available");
		}
	}

	/**
	 * Add new group to the table dynamically
	 * @param {Object} groupData - Group data object
	 */
	async addNewGroupToTable(groupData) {
		const tableBody = document.querySelector(".table-responsive .table tbody");
		if (!tableBody) {
			console.error("Table body not found");
			return;
		}

		// Format date
		const createdDate = new Date(groupData.created_at).toLocaleDateString(
			"en-US",
			{
				year: "numeric",
				month: "short",
				day: "numeric",
			},
		);

		try {
			// Render dropdown menu using centralized template
			const dropdownHtml = await window.DOMUtils.renderDropdown({
				button_label: `Actions for ${groupData.name}`,
				items: [
					{
						label: "Manage",
						icon: "person-plus",
						type: "button",
						modal_toggle: true,
						modal_target: "#share-modal-sharegroup",
						data_attrs: {
							"group-uuid": groupData.uuid,
							"group-name": groupData.name,
						},
					},
					{
						label: "Delete",
						icon: "trash",
						type: "button",
						onclick: `shareGroupManager.deleteGroup('${groupData.uuid}', '${groupData.name}')`,
					},
				],
			});

			// Create a temporary container for the table
			const tempDiv = document.createElement("div");
			await window.DOMUtils.renderTable(
				tempDiv,
				[
					{
						data_attrs: { group_uuid: groupData.uuid },
						cells: [
							{ html: `<strong>${groupData.name}</strong>` },
							{
								html: `
						<span class="badge bg-secondary member-count" data-group-uuid="${groupData.uuid}">0 members</span>
						<div class="small text-muted mt-1 member-emails" data-group-uuid="${groupData.uuid}" style="display: none;"></div>
					`,
							},
							{ value: createdDate },
							{ html: dropdownHtml },
						],
					},
				],
				{
					empty_message: "",
					empty_colspan: 4,
				},
			);

			// Insert the rendered HTML directly
			tableBody.insertAdjacentHTML("beforeend", tempDiv.innerHTML);

			// Hide the "no groups" message if it exists
			const noGroupsMessage = document.querySelector(".text-center.py-5");
			if (noGroupsMessage) {
				window.DOMUtils.hide(noGroupsMessage);
			}
		} catch (error) {
			console.error("Error rendering new group row:", error);
			// Fallback: reload the page
			window.location.reload();
		}
	}

	/**
	 * Open manage modal for a specific group
	 * @param {string} groupUuid - Group UUID
	 * @param {string} groupName - Group name
	 */
	openManageModalForGroup(groupUuid, groupName) {
		// Set the current group info
		this.currentGroupUuid = groupUuid;
		this.currentGroupName = groupName;

		// Set the hidden input value
		document.getElementById("addGroupUuid").value = groupUuid;

		// Update modal title
		document.getElementById("manageMembersModalLabel").innerHTML =
			`<i class="bi bi-person-plus me-2"></i>Manage Members: ${groupName}`;

		// Clear pending removals
		this.pendingRemovals.clear();

		// Reset user search handler state
		if (this.shareGroupUserSearchHandler) {
			this.shareGroupUserSearchHandler.resetShareGroup();
		}

		// Load current members
		this.loadCurrentMembers();

		// Load and display shared assets information
		this.loadSharedAssetsInfo();

		// Show the modal
		const manageModal = new bootstrap.Modal(
			document.getElementById("share-modal-sharegroup"),
		);
		manageModal.show();
	}
}

// Make class available globally
window.ShareGroupManager = ShareGroupManager;

// Export for ES6 modules (Jest testing)
export { ShareGroupManager };
