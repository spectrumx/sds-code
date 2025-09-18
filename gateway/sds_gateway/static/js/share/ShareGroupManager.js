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
			...config
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
		if (createGroupForm) {
			createGroupForm.addEventListener("submit", (e) => {
				e.preventDefault();
				this.handleCreateGroup(createGroupForm);
			});
		} else {
			console.error("Create group form not found");
		}
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

		// Use URLSearchParams for form-encoded data instead of FormData
		const formData = new URLSearchParams();
		formData.append("action", "create");
		formData.append("name", groupName);


		try {
			const response = await APIClient.request(this.config.apiEndpoint, {
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
					this.openManageModalForGroup(response.group.uuid, response.group.name);
				}, 500);
			} else {
				this.showAlert(response.error, "error");
			}
		} catch (error) {
			// Extract specific error message from the response
			let errorMessage = "An error occurred while creating the group.";
			if (error.data && error.data.error) {
				errorMessage = error.data.error;
			} else if (error.message && error.message.includes("400")) {
				errorMessage = "Bad request - please check the form data and try again.";
			}
			
			this.showAlert(errorMessage, "error");
		}
	}

	/**
	 * Initialize add members form
	 */
	initializeAddMembersForm() {
		const addMembersForm = document.getElementById("addMembersForm");
		if (addMembersForm) {
			addMembersForm.addEventListener("submit", (e) => {
				e.preventDefault();
				this.handleAddMembers(addMembersForm);
			});
		}
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
			const response = await APIClient.request(this.config.apiEndpoint, {
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
			if (error.data && error.data.error) {
				errorMessage = error.data.error;
			}
			
			this.showAlert(errorMessage, "error");
		}
	}

	/**
	 * Initialize manage members modal
	 */
	initializeManageMembersModal() {
		const manageMembersModal = document.getElementById("share-modal-sharegroup");
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
			formData.append("user_emails", Array.from(this.pendingRemovals).join(","));

			try {
				const response = await APIClient.request(this.config.apiEndpoint, {
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
				if (error.data && error.data.error) {
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
			confirmDeleteBtn.addEventListener("click", () => this.handleDeleteGroup(confirmDeleteBtn));
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
			const response = await APIClient.request(this.config.apiEndpoint, {
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
			if (error.data && error.data.error) {
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

		const loadingHtml = `
			<tr>
				<td class="p-2 shadow-sm">
					<div class="text-center text-muted">
						<i class="bi bi-people"></i>
						<p class="mb-0">Loading members...</p>
					</div>
				</td>
			</tr>
		`;
		HTMLInjectionManager.injectHTML(membersList, loadingHtml, { escape: false });

		try {
			const response = await APIClient.request(
				`${this.config.apiEndpoint}?group_uuid=${this.currentGroupUuid}`,
				{
					headers: {
						"X-Requested-With": "XMLHttpRequest",
					},
				}
			);

			if (response.success) {
				if (response.members.length === 0) {
					// Clear member count for empty group
					const memberCountElement = document.getElementById("memberCount");
					if (memberCountElement) {
						memberCountElement.textContent = "";
					}

					const emptyHtml = `
						<tr>
							<td class="p-2 shadow-sm">
								<div class="text-center text-muted mb-1 mt-1">
									<i class="bi bi-people"></i>
									<p>No members in this group</p>
								</div>
							</td>
						</tr>
					`;
					HTMLInjectionManager.injectHTML(membersList, emptyHtml, { escape: false });
				} else {
					// Update the display list with table structure like share modal
					const memberHtml = response.members
						.map(
							(member) => `
								<tr>
									<td class="p-2 shadow-sm">
										<div class="row">
											<div class="col-md-10">
												<div>
													<h5 class="mb-1">${member.name || "No name"}</h5>
													<p class="mb-0">
														<small class="text-muted">${member.email}</small>
													</p>
												</div>
											</div>
											<div class="col-md-2 d-flex justify-content-end align-items-center">
												<button type="button"
														class="btn btn-sm btn-outline-danger remove-member-btn"
														data-user-email="${member.email}"
														data-user-name="${member.name || "No name"}"
														onclick="shareGroupManager.removeMemberFromGroup(event, '${member.email}', '${member.name || "No name"}')">
													<i class="bi bi-person-slash me-1"></i>Remove
												</button>
											</div>
										</div>
									</td>
								</tr>
							`,
						)
						.join("");

					HTMLInjectionManager.injectHTML(membersList, memberHtml, { escape: false });

					// Update member count above the title
					const memberCountElement = document.getElementById("memberCount");
					if (memberCountElement) {
						memberCountElement.textContent = `${response.count} member${response.count !== 1 ? "s" : ""}`;
					}

					// Update table member info
					this.updateTableMemberInfo(this.currentGroupUuid, response.members);

					// Update save button state after loading members
					this.updateSaveButtonState();
				}
			} else {
				const errorHtml = `
					<div class="text-center text-danger">
						<i class="bi bi-exclamation-triangle"></i>
						<p class="mb-0">Error loading members</p>
					</div>
				`;
				HTMLInjectionManager.injectHTML(membersList, errorHtml, { escape: false });
			}
		} catch (error) {
			const errorHtml = `
				<div class="text-center text-danger">
					<i class="bi bi-exclamation-triangle"></i>
					<p class="mb-0">Error loading members</p>
				</div>
			`;
			HTMLInjectionManager.injectHTML(membersList, errorHtml, { escape: false });
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
			const response = await APIClient.request(this.config.apiEndpoint, {
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
	displaySharedAssetsInfo(sharedAssets) {
		// Find the shared assets section in the modal
		const sharedAssetsSection = document.getElementById("sharedAssetsSection");

		if (sharedAssetsSection) {
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

				// Build datasets column
				let datasetsHtml = "";
				if (displayDatasets.length > 0) {
					const datasetsList = displayDatasets
						.map(
							(asset) => `
								<div class="d-flex align-items-center mb-2">
									<i class="bi bi-collection me-2"></i>
									<div class="flex-grow-1">
										<div class="fw-bold">${asset.name}</div>
										<div class="text-muted small">Dataset • Shared by ${asset.owner_name}</div>
									</div>
								</div>
							`,
						)
						.join("");

					let moreDatasetsText = "";
					if (hasMoreDatasets) {
						const remainingDatasets = totalDatasets - 3;
						moreDatasetsText = `
							<div class="text-muted small mt-2">
								<i class="bi bi-three-dots me-1"></i>
								and ${remainingDatasets} more dataset${remainingDatasets !== 1 ? "s" : ""}
							</div>
						`;
					}

					datasetsHtml = `
						<div class="col-md-6">
							<h6>
								<i class="bi bi-collection me-2"></i>Datasets (${totalDatasets})
							</h6>
							<div class="shared-datasets-list">
								${datasetsList}
								${moreDatasetsText}
							</div>
						</div>
					`;
				}

				// Build captures column
				let capturesHtml = "";
				if (displayCaptures.length > 0) {
					const capturesList = displayCaptures
						.map(
							(asset) => `
								<div class="d-flex align-items-center mb-2">
									<i class="bi bi-folder me-2"></i>
									<div class="flex-grow-1">
										<div class="fw-bold">${asset.name}</div>
										<div class="text-muted small">Capture • Shared by ${asset.owner_name}</div>
									</div>
								</div>
							`,
						)
						.join("");

					let moreCapturesText = "";
					if (hasMoreCaptures) {
						const remainingCaptures = totalCaptures - 3;
						moreCapturesText = `
							<div class="text-muted small mt-2">
								<i class="bi bi-three-dots me-1"></i>
								and ${remainingCaptures} more capture${remainingCaptures !== 1 ? "s" : ""}
							</div>
						`;
					}

					capturesHtml = `
						<div class="col-md-6">
							<h6>
								<i class="bi bi-folder me-2"></i>Captures (${totalCaptures})
							</h6>
							<div class="shared-captures-list">
								${capturesList}
								${moreCapturesText}
							</div>
						</div>
					`;
				}

				const sharedAssetsHtml = `
					<h6>
						<i class="bi bi-share me-2"></i>Shared Assets (${totalDatasets + totalCaptures})
					</h6>
					<div class="alert alert-info">
						<div class="mb-2">
							<strong>New members will automatically have access to these shared assets:</strong>
						</div>
						<div class="row">
							${datasetsHtml}
							${capturesHtml}
						</div>
					</div>
				`;
				HTMLInjectionManager.injectHTML(sharedAssetsSection, sharedAssetsHtml, { escape: false });
				sharedAssetsSection.classList.remove("d-none");
			} else {
				const noAssetsHtml = `
					<h6 class="text-muted">
						<i class="bi bi-share me-2"></i>Shared Assets
					</h6>
					<div class="alert alert-light">
						<div class="text-muted">
							<i class="bi bi-info-circle me-1"></i>
							No assets are currently shared with this group. New members will not have access to any shared assets.
						</div>
					</div>
				`;
				HTMLInjectionManager.injectHTML(sharedAssetsSection, noAssetsHtml, { escape: false });
				sharedAssetsSection.classList.remove("d-none");
			}
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
		// Store reference to ShareGroupManager instance for proper method binding
		const shareGroupManager = this;
		
		// Create a custom search handler for ShareGroup using ShareActionManager's methods
		this.shareGroupUserSearchHandler = {
			selectedUsersMap: {},
			searchTimeout: null,
			currentRequest: null,

			// Search users using ShareGroup endpoint
			searchUsers: async (query, dropdown) => {
				if (query.length < 2) {
					shareGroupManager.hideDropdown(dropdown);
					return;
				}

				// Cancel previous request if still pending
				if (shareGroupManager.shareGroupUserSearchHandler.currentRequest) {
					shareGroupManager.shareGroupUserSearchHandler.currentRequest.abort();
				}

				try {
					shareGroupManager.shareGroupUserSearchHandler.currentRequest = new AbortController();
					const response = await APIClient.get(
						`${shareGroupManager.config.apiEndpoint}?q=${encodeURIComponent(query)}&group_uuid=${shareGroupManager.currentGroupUuid}`,
						{},
						null // No loading state for search
					);

					if (Array.isArray(response)) {
						shareGroupManager.shareGroupUserSearchHandler.displayResults(response, dropdown, query);
					} else {
						shareGroupManager.hideDropdown(dropdown);
					}
				} catch (error) {
					if (error.name === "AbortError") {
						return;
					}
					console.error("Search error:", error);
					shareGroupManager.shareGroupUserSearchHandler.displayError(dropdown);
				} finally {
					shareGroupManager.shareGroupUserSearchHandler.currentRequest = null;
				}
			},

			// Display search results (adapted from ShareActionManager)
			displayResults: (users, dropdown, query) => {
				const listGroup = dropdown.querySelector(".list-group");

				if (users.length === 0) {
					listGroup.innerHTML = '<div class="list-group-item no-results">No users found</div>';
				} else {
					const items = users.map((user) => {
						const icon = "bi-person-fill text-primary";
						const subtitle = `<div class="user-email">${shareGroupManager.highlightMatch(user.email, query)}</div>`;

						return `
							<div class="list-group-item" 
								 data-user-name="${HTMLInjectionManager.escapeHtml(user.name)}" 
								 data-user-email="${HTMLInjectionManager.escapeHtml(user.email)}">
								<div class="user-search-item">
									<div class="user-name">
										<i class="bi ${icon} me-2"></i>
										${shareGroupManager.highlightMatch(user.name, query)}
									</div>
									${subtitle}
								</div>
							</div>
						`;
					}).join("");

					HTMLInjectionManager.injectHTML(listGroup, items, { escape: false });
				}

				shareGroupManager.showDropdown(dropdown);
			},

			// Display error (adapted from ShareActionManager)
			displayError: (dropdown) => {
				const listGroup = dropdown.querySelector(".list-group");
				listGroup.innerHTML = '<div class="list-group-item no-results">Error loading users</div>';
				shareGroupManager.showDropdown(dropdown);
			},

			// Select user from dropdown
			selectUser: (item, input) => {
				const userName = item.dataset.userName;
				const userEmail = item.dataset.userEmail;
				const inputId = input.id;

				if (!shareGroupManager.shareGroupUserSearchHandler.selectedUsersMap[inputId]) {
					shareGroupManager.shareGroupUserSearchHandler.selectedUsersMap[inputId] = [];
				}

				// Check if user is already selected
				if (!shareGroupManager.shareGroupUserSearchHandler.selectedUsersMap[inputId].some((u) => u.email === userEmail)) {
					shareGroupManager.shareGroupUserSearchHandler.selectedUsersMap[inputId].push({ name: userName, email: userEmail });
					shareGroupManager.shareGroupUserSearchHandler.renderChips(input);
				}

				// Clear the input field
				input.value = "";
				shareGroupManager.hideDropdown(item.closest(".user-search-dropdown"));
				input.focus();

				// Update save button state for share group
				shareGroupManager.updateSaveButtonState();
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
				for (const user of shareGroupManager.shareGroupUserSearchHandler.selectedUsersMap[inputId]) {
					const chip = document.createElement("span");
					chip.className = "user-chip";
					chip.textContent = user.email;
					const remove = document.createElement("span");
					remove.className = "remove-chip";
					remove.innerHTML = "&times;";
					remove.onclick = () => {
						shareGroupManager.shareGroupUserSearchHandler.selectedUsersMap[inputId] = shareGroupManager.shareGroupUserSearchHandler.selectedUsersMap[inputId].filter(
							(u) => u.email !== user.email,
						);
						shareGroupManager.shareGroupUserSearchHandler.renderChips(input);
						// Update save button state when removing chips
						shareGroupManager.updateSaveButtonState();
					};
					chip.appendChild(remove);
					chipContainer.appendChild(chip);
				}
			},

			// Reset share group state
			resetShareGroup: () => {
				// Clear selected users
				shareGroupManager.shareGroupUserSearchHandler.selectedUsersMap = {};

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
				shareGroupManager.updateSaveButtonState();
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
					shareGroupManager.setupSearchInput(searchInput);
				}
			}
		};

		// Initialize the handler
		this.shareGroupUserSearchHandler.init();
	}

	/**
	 * Helper methods adapted from ShareActionManager
	 */
	
	/**
	 * Highlight search matches
	 * @param {string} text - Text to highlight
	 * @param {string} query - Search query
	 * @returns {string} Highlighted text
	 */
	highlightMatch(text, query) {
		if (!query) return HTMLInjectionManager.escapeHtml(text);
		const regex = new RegExp(`(${query})`, "gi");
		return HTMLInjectionManager.escapeHtml(text).replace(regex, "<mark>$1</mark>");
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
			this.shareGroupUserSearchHandler?.selectedUsersMap["user-search-sharegroup"] &&
			this.shareGroupUserSearchHandler.selectedUsersMap["user-search-sharegroup"]
				.length > 0;
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
				memberEmailsElement.style.display = "none";
				memberEmailsElement.innerHTML = "";
			} else {
				memberEmailsElement.style.display = "block";
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
			memberEmailsElement.style.display = "none";
			memberEmailsElement.innerHTML = "";
		} else {
			memberEmailsElement.style.display = "block";
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
		// Use the global showAlert function from HTMLInjectionManager
		if (window.showAlert) {
			window.showAlert(message, type);
		} else {
			console.error("Global showAlert function not available");
		}
	}

	/**
	 * Add new group to the table dynamically
	 * @param {Object} groupData - Group data object
	 */
	addNewGroupToTable(groupData) {
		const tableBody = document.querySelector(".table-responsive .table tbody");
		if (!tableBody) {
			console.error("Table body not found");
			return;
		}

		// Create the new row HTML
		const newRow = document.createElement("tr");
		newRow.setAttribute("data-group-uuid", groupData.uuid);

		const createdDate = new Date(groupData.created_at).toLocaleDateString(
			"en-US",
			{
				year: "numeric",
				month: "short",
				day: "numeric",
			},
		);

		const newRowHtml = `
			<td>
				<strong>${groupData.name}</strong>
			</td>
			<td>
				<span class="badge bg-secondary member-count" data-group-uuid="${groupData.uuid}">0 members</span>
				<div class="small text-muted mt-1 member-emails" data-group-uuid="${groupData.uuid}" style="display: none;"></div>
			</td>
			<td>${createdDate}</td>
			<td>
				<div class="dropdown">
					<button class="btn btn-sm btn-light dropdown-toggle btn-icon-dropdown"
							type="button"
							data-bs-toggle="dropdown"
							data-bs-popper="static"
							aria-expanded="false"
							aria-label="Actions for ${groupData.name}">
						<i class="bi bi-three-dots-vertical"></i>
					</button>
					<ul class="dropdown-menu">
						<li>
							<button type="button"
									class="dropdown-item"
									data-bs-toggle="modal"
									data-bs-target="#share-modal-sharegroup"
									data-group-uuid="${groupData.uuid}"
									data-group-name="${groupData.name}">
								<i class="bi bi-person-plus me-1"></i>Manage
							</button>
						</li>
						<li>
							<button type="button"
									class="dropdown-item"
									onclick="shareGroupManager.deleteGroup('${groupData.uuid}', '${groupData.name}')">
								<i class="bi bi-trash me-1"></i>Delete
							</button>
						</li>
					</ul>
				</div>
			</td>
		`;

		HTMLInjectionManager.injectHTML(newRow, newRowHtml, { escape: false });

		// Add the new row to the table
		tableBody.appendChild(newRow);

		// Hide the "no groups" message if it exists
		const noGroupsMessage = document.querySelector(".text-center.py-5");
		if (noGroupsMessage) {
			noGroupsMessage.style.display = "none";
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
