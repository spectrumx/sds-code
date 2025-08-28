// Share Group Manager JavaScript
// Handles all share group operations including creating, managing members, and deleting groups

// Global variables
let currentGroupUuid = null;
let currentGroupName = null;
let pendingDeleteGroupUuid = null;
let pendingDeleteGroupName = null;
const pendingRemovals = new Set();
let shareGroupUserSearchHandler = null;

// Create Group Form Handler
function initializeCreateGroupForm() {
	const createGroupForm = document.getElementById("createGroupForm");
	if (createGroupForm) {
		createGroupForm.addEventListener("submit", (e) => {
			e.preventDefault();

			const groupName = document.getElementById("groupName").value;

			if (!groupName.trim()) {
				showAlert("Group name is required", "error");
				return;
			}

			const formData = new FormData();
			formData.append("action", "create");
			formData.append("name", groupName);

			const csrfToken = document.querySelector(
				"[name=csrfmiddlewaretoken]",
			).value;

			fetch(window.location.href, {
				method: "POST",
				headers: {
					"X-CSRFToken": csrfToken,
				},
				body: formData,
			})
				.then((response) => {
					return response.json();
				})
				.then((data) => {
					if (data.success) {
						// Show success message
						showAlert(data.message, "success");

						// Close the create modal
						const createModal = bootstrap.Modal.getInstance(
							document.getElementById("createGroupModal"),
						);
						createModal.hide();

						// Clear the form
						document.getElementById("groupName").value = "";

						// Add the new group to the table dynamically
						addNewGroupToTable(data.group);

						// Automatically open the manage modal for the new group
						setTimeout(() => {
							openManageModalForGroup(data.group.uuid, data.group.name);
						}, 500);
					} else {
						showAlert(data.error, "error");
					}
				})
				.catch((error) => {
					console.error("Error:", error);
					showAlert("An error occurred while creating the group.", "error");
				});
		});
	} else {
		console.error("Create group form not found");
	}
}

// Add Members Form Handler
function initializeAddMembersForm() {
	const addMembersForm = document.getElementById("addMembersForm");
	if (addMembersForm) {
		addMembersForm.addEventListener("submit", (e) => {
			e.preventDefault();

			const inputId = "user-search-sharegroup";
			const selectedUsers = shareGroupUserSearchHandler
				? shareGroupUserSearchHandler.selectedUsersMap[inputId] || []
				: [];

			if (selectedUsers.length === 0) {
				showAlert("Please select at least one user to add.", "error");
				return;
			}

			const userEmails = selectedUsers.map((user) => user.email).join(",");

			const formData = new FormData();
			formData.append("action", "add_members");
			formData.append("group_uuid", currentGroupUuid);
			formData.append("user_emails", userEmails);

			fetch(window.location.href, {
				method: "POST",
				headers: {
					"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")
						.value,
				},
				body: formData,
			})
				.then((response) => response.json())
				.then((data) => {
					if (data.success) {
						// Show success message in toast
						showAlert(data.message, "success");

						// Show any errors as warnings
						if (data.errors && data.errors.length > 0) {
							for (const error of data.errors) {
								showAlert(error, "warning");
							}
						}

						if (shareGroupUserSearchHandler) {
							shareGroupUserSearchHandler.resetShareGroup();
						}
						// Clear pending removals when members are added
						pendingRemovals.clear();
						loadCurrentMembers();
						updateSaveButtonState();

						// Update table member info by adding the new members
						if (data.added_users && data.added_users.length > 0) {
							updateTableMemberEmails(
								currentGroupUuid,
								data.added_users,
								"add",
							);
						}
					} else {
						showAlert(data.error, "error");
					}
				})
				.catch((error) => {
					console.error("Error:", error);
					showAlert("An error occurred while adding members.", "error");
				});
		});
	}
}

// Manage Members Modal Event Handler
function initializeManageMembersModal() {
	const manageMembersModal = document.getElementById("share-modal-sharegroup");
	if (manageMembersModal) {
		manageMembersModal.addEventListener("show.bs.modal", (event) => {
			const button = event.relatedTarget;

			// If there's a button with data attributes, use those values
			if (button?.hasAttribute("data-group-uuid")) {
				currentGroupUuid = button.getAttribute("data-group-uuid");
				currentGroupName = button.getAttribute("data-group-name");
			}

			// If currentGroupUuid is not set, the modal was opened programmatically
			// and the group info should already be set by openManageModalForGroup
			if (!currentGroupUuid) {
				return;
			}

			document.getElementById("addGroupUuid").value = currentGroupUuid;

			// Update modal title
			document.getElementById("manageMembersModalLabel").innerHTML =
				`<i class="bi bi-person-plus me-2"></i>Manage Members: ${currentGroupName}`;

			// Clear pending removals when opening modal
			pendingRemovals.clear();

			// Reset user search handler state
			if (shareGroupUserSearchHandler) {
				shareGroupUserSearchHandler.resetShareGroup();
			}

			// Load current members
			loadCurrentMembers();

			// Load and display shared assets information
			loadSharedAssetsInfo();
		});

		// Also handle modal hidden event to reset state
		manageMembersModal.addEventListener("hidden.bs.modal", () => {
			// Reset user search handler state (but don't destroy it)
			if (shareGroupUserSearchHandler) {
				shareGroupUserSearchHandler.resetShareGroup();
			}
			// Clear current group info
			currentGroupUuid = null;
			currentGroupName = null;
			// Clear pending removals
			pendingRemovals.clear();
			// Reset save button state
			updateSaveButtonState();
			// Hide shared assets section
			const sharedAssetsSection = document.getElementById(
				"sharedAssetsSection",
			);
			if (sharedAssetsSection) {
				sharedAssetsSection.style.display = "none";
			}
		});
	}
}

// Save Button Handler
function initializeSaveButton() {
	const saveBtn = document.getElementById("save-sharegroup-btn");
	if (saveBtn) {
		saveBtn.addEventListener("click", function () {
			const originalText = this.innerHTML;
			this.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
			this.disabled = true;
			// Handle pending removals
			if (pendingRemovals.size > 0) {
				const formData = new FormData();
				formData.append("action", "remove_members");
				formData.append("group_uuid", currentGroupUuid);
				formData.append("user_emails", Array.from(pendingRemovals).join(","));

				fetch(window.location.href, {
					method: "POST",
					headers: {
						"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")
							.value,
					},
					body: formData,
				})
					.then((response) => response.json())
					.then((data) => {
						if (data.success) {
							// Show success message in toast
							showAlert(data.message, "success");

							// Show any errors as warnings
							if (data.errors && data.errors.length > 0) {
								for (const error of data.errors) {
									showAlert(error, "warning");
								}
							}

							// Clear pending removals
							pendingRemovals.clear();
							// Reset all remove buttons
							resetRemoveButtons();
							// Reload members
							loadCurrentMembers();

							// Update table member info by removing the members
							if (data.removed_users && data.removed_users.length > 0) {
								updateTableMemberEmails(
									currentGroupUuid,
									data.removed_users,
									"remove",
								);
							}
						} else {
							showAlert(data.error, "error");
						}
					})
					.catch((error) => {
						console.error("Error:", error);
						showAlert("An error occurred while removing members.", "error");
					})
					.finally(() => {
						this.innerHTML = originalText;
						this.disabled = false;
						updateSaveButtonState();
					});
			}
		});
	}
}

// Delete Group Confirmation Handler
function initializeDeleteGroupConfirmation() {
	const confirmDeleteBtn = document.getElementById("confirmDeleteGroup");
	if (confirmDeleteBtn) {
		confirmDeleteBtn.addEventListener("click", function () {
			if (!pendingDeleteGroupUuid) {
				return;
			}
			const originalText = this.innerHTML;
			this.innerHTML = '<i class="bi bi-hourglass-split"></i> Deleting...';
			this.disabled = true;

			const formData = new FormData();
			formData.append("action", "delete_group");
			formData.append("group_uuid", pendingDeleteGroupUuid);

			fetch(window.location.href, {
				method: "POST",
				headers: {
					"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")
						.value,
				},
				body: formData,
			})
				.then((response) => response.json())
				.then((data) => {
					// Hide the confirmation modal
					const deleteModal = bootstrap.Modal.getInstance(
						document.getElementById("deleteGroupModal"),
					);
					deleteModal.hide();

					if (data.success) {
						// Store success message for after page reload
						localStorage.setItem("shareGroupSuccessMessage", data.message);
						setTimeout(() => window.location.reload(), 1000);
					} else {
						showAlert(data.error, "error");
					}
				})
				.catch((error) => {
					console.error("Error:", error);
					showAlert("An error occurred while deleting the group.", "error");
				})
				.finally(() => {
					// Reset button state
					this.innerHTML = originalText;
					this.disabled = false;

					// Clear pending deletion data
					pendingDeleteGroupUuid = null;
					pendingDeleteGroupName = null;
				});
		});
	}
}

// Load current members for a group
function loadCurrentMembers() {
	if (!currentGroupUuid) return;

	const membersList = document.getElementById("currentMembers");

	// Clear member count and show loading state
	const memberCountElement = document.getElementById("memberCount");
	if (memberCountElement) {
		memberCountElement.textContent = "";
	}

	membersList.innerHTML = `
        <tr>
            <td class="p-2 shadow-sm">
                <div class="text-center text-muted">
                    <i class="bi bi-people"></i>
                    <p class="mb-0">Loading members...</p>
                </div>
            </td>
        </tr>
    `;

	fetch(`${window.location.href}?group_uuid=${currentGroupUuid}`, {
		headers: {
			"X-Requested-With": "XMLHttpRequest",
		},
	})
		.then((response) => response.json())
		.then((data) => {
			if (data.success) {
				if (data.members.length === 0) {
					// Clear member count for empty group
					const memberCountElement = document.getElementById("memberCount");
					if (memberCountElement) {
						memberCountElement.textContent = "";
					}

					membersList.innerHTML = `
                    <tr>
                        <td class="p-2 shadow-sm">
                            <div class="text-center text-muted mb-1 mt-1">
                                <i class="bi bi-people"></i>
                                <p>No members in this group</p>
                            </div>
                        </td>
                    </tr>
                `;
				} else {
					// Update the display list with table structure like share modal
					const memberHtml = data.members
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
                                            onclick="removeMemberFromGroup(event, '${member.email}', '${member.name || "No name"}')">
                                        <i class="bi bi-person-slash me-1"></i>Remove
                                    </button>
                                </div>
                            </div>
                        </td>
                    </tr>
                `,
						)
						.join("");

					// Update member count above the title
					const memberCountElement = document.getElementById("memberCount");
					if (memberCountElement) {
						memberCountElement.textContent = `${data.count} member${data.count !== 1 ? "s" : ""}`;
					}

					membersList.innerHTML = memberHtml;

					// Update table member info
					updateTableMemberInfo(currentGroupUuid, data.members);

					// Update save button state after loading members
					updateSaveButtonState();
				}
			} else {
				const errorHtml = `
                <div class="text-center text-danger">
                    <i class="bi bi-exclamation-triangle"></i>
                    <p class="mb-0">Error loading members</p>
                </div>
            `;
				membersList.innerHTML = errorHtml;
			}
		})
		.catch((error) => {
			console.error("Error:", error);
			const errorHtml = `
            <div class="text-center text-danger">
                <i class="bi bi-exclamation-triangle"></i>
                <p class="mb-0">Error loading members</p>
            </div>
        `;
			membersList.innerHTML = errorHtml;
		});
}

function loadSharedAssetsInfo() {
	if (!currentGroupUuid) {
		return;
	}

	// Create a temporary request to get shared assets info
	const formData = new FormData();
	formData.append("action", "get_shared_assets");
	formData.append("group_uuid", currentGroupUuid);

	fetch(window.location.href, {
		method: "POST",
		headers: {
			"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value,
		},
		body: formData,
	})
		.then((response) => response.json())
		.then((data) => {
			if (data.success) {
				displaySharedAssetsInfo(data.shared_assets);
			} else {
				console.error("Error loading shared assets:", data.error);
			}
		})
		.catch((error) => {
			console.error("Error:", error);
		});
}

function displaySharedAssetsInfo(sharedAssets) {
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

			sharedAssetsSection.innerHTML = `
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
			sharedAssetsSection.style.display = "block";
		} else {
			sharedAssetsSection.innerHTML = `
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
			sharedAssetsSection.style.display = "block";
		}
	}
}

// Delete Group Function - shows confirmation modal
function deleteGroup(groupUuid, groupName) {
	// Store the group info for confirmation
	pendingDeleteGroupUuid = groupUuid;
	pendingDeleteGroupName = groupName;

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

	// Add event listeners for debugging
	deleteModalElement.addEventListener("shown.bs.modal", () => {});

	deleteModalElement.addEventListener("hidden.bs.modal", () => {});

	deleteModalElement.addEventListener("show.bs.modal", () => {});

	deleteModal.show();

	// Additional debugging after a short delay
	setTimeout(() => {}, 100);
}

// User Search Handler for ShareGroup
function initializeShareGroupUserSearch() {
	// Create a UserSearchHandler instance for ShareGroup
	shareGroupUserSearchHandler = new UserSearchHandler();
	shareGroupUserSearchHandler.setItemInfo("sharegroup", "sharegroup");

	// Override the searchUsers method to use ShareGroup endpoint
	shareGroupUserSearchHandler.searchUsers = async function (query, dropdown) {
		if (query.length < 2) {
			this.hideDropdown(dropdown);
			return;
		}

		try {
			const response = await fetch(
				`${window.location.href}?q=${encodeURIComponent(query)}&group_uuid=${currentGroupUuid}`,
				{
					headers: {
						"X-Requested-With": "XMLHttpRequest",
					},
				},
			);

			if (!response.ok) {
				throw new Error("Search request failed");
			}

			const data = await response.json();

			if (Array.isArray(data)) {
				this.displayResults(data, dropdown, query);
			} else {
				this.hideDropdown(dropdown);
			}
		} catch (error) {
			console.error("Search error:", error);
			this.hideDropdown(dropdown);
		}
	};

	// Override the selectUser method to properly handle share group context
	const originalSelectUser = shareGroupUserSearchHandler.selectUser;
	shareGroupUserSearchHandler.selectUser = function (item, input) {
		const userName = item.dataset.userName;
		const userEmail = item.dataset.userEmail;
		const inputId = input.id;

		if (!this.selectedUsersMap[inputId]) {
			this.selectedUsersMap[inputId] = [];
		}

		// Check if user is already selected
		if (!this.selectedUsersMap[inputId].some((u) => u.email === userEmail)) {
			this.selectedUsersMap[inputId].push({ name: userName, email: userEmail });
			this.renderChips(input);
		}

		// Clear the input field
		input.value = "";
		this.hideDropdown(item.closest(".user-search-dropdown"));
		input.focus();

		// Update save button state for share group
		updateSaveButtonState();
	};

	// Override the renderChips method to handle share group context
	shareGroupUserSearchHandler.renderChips = function (input) {
		const inputId = input.id;
		const chipContainer = input
			.closest(".user-search-input-container")
			.querySelector(".selected-users-chips");

		if (!chipContainer) {
			console.warn("Chip container not found for input:", inputId);
			return;
		}

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
				// Update save button state when removing chips
				updateSaveButtonState();
			};
			chip.appendChild(remove);
			chipContainer.appendChild(chip);
		}
	};

	// Initialize the handler
	shareGroupUserSearchHandler.init();

	// Add a custom reset method for share groups
	shareGroupUserSearchHandler.resetShareGroup = function () {
		// Clear selected users
		this.selectedUsersMap = {};

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
		updateSaveButtonState();
	};
}

// Remove member from group (inline) - marks for pending removal
function removeMemberFromGroup(event, email, name) {
	const button = event.target.closest(".remove-member-btn");
	if (!button) return;

	// Toggle removal state
	if (pendingRemovals.has(email)) {
		// Remove from pending removals
		pendingRemovals.delete(email);

		// Change button back to outline style
		button.innerHTML = '<i class="bi bi-person-slash me-1"></i>Remove';
		button.classList.remove("btn-danger");
		button.classList.add("btn-outline-danger");
	} else {
		// Add to pending removals
		pendingRemovals.add(email);

		// Change button to solid red style
		button.innerHTML = '<i class="bi bi-person-slash me-1"></i>Remove';
		button.classList.remove("btn-outline-danger");
		button.classList.add("btn-danger");
	}

	// Update save button state
	updateSaveButtonState();
}

// Update save button state based on pending changes
function updateSaveButtonState() {
	const saveBtn = document.getElementById("save-sharegroup-btn");
	const pendingMessage = document.getElementById(
		"pending-changes-message-sharegroup",
	);
	const pendingMessageFooter = document.getElementById(
		"pending-changes-message-sharegroup-footer",
	);

	const hasSelectedUsers =
		shareGroupUserSearchHandler?.selectedUsersMap["user-search-sharegroup"] &&
		shareGroupUserSearchHandler.selectedUsersMap["user-search-sharegroup"]
			.length > 0;
	const hasPendingRemovals = pendingRemovals.size > 0;

	if (saveBtn) {
		// Save button should only be enabled when there are pending removals
		// Adding members is handled by the "Add Members" button, not the save button
		if (hasPendingRemovals) {
			saveBtn.disabled = false;
		} else {
			saveBtn.disabled = true;
		}
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

// Reset all remove buttons to their original state
function resetRemoveButtons() {
	const buttons = document.querySelectorAll(".remove-member-btn");
	for (const button of buttons) {
		button.innerHTML = '<i class="bi bi-person-slash me-1"></i>Remove';
		button.classList.remove("btn-danger");
		button.classList.add("btn-outline-danger");
	}
}

// Update member count and emails in the table
function updateTableMemberInfo(groupUuid, members) {
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

// Update member emails list by adding or removing specific emails
function updateTableMemberEmails(groupUuid, emails, action) {
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

// Show Alert Function - Toast notifications
function showAlert(message, type = "info") {
	const toastContainer = document.getElementById("toast-container");
	if (!toastContainer) return;

	const toastId = `toast-${Date.now()}-${Math.floor(Math.random() * 1000)}`;

	// Map type to Bootstrap toast classes
	const bgClass =
		type === "error"
			? "bg-danger text-white"
			: type === "success"
				? "bg-success text-white"
				: type === "warning"
					? "bg-warning text-dark"
					: "bg-info text-white";

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

	// Remove element after toast is hidden
	toastElem.addEventListener("hidden.bs.toast", () => toastElem.remove());
}

// Initialize all event handlers when DOM is loaded
function initializeShareGroupManager() {
	initializeCreateGroupForm();
	initializeAddMembersForm();
	initializeManageMembersModal();
	initializeSaveButton();
	initializeDeleteGroupConfirmation();

	// Initialize user search handler once
	initializeShareGroupUserSearch();
}

// Add new group to the table dynamically
function addNewGroupToTable(groupData) {
	const cardBody = document.querySelector(".card-body");
	if (!cardBody) {
		console.error("Card body not found");
		return;
	}

	// Check if table structure exists, if not create it
	let tableBody = document.querySelector(".table-responsive .table tbody");
	if (!tableBody) {
		// Remove the "no groups" message
		const noGroupsMessage = document.querySelector(".text-center.py-5");
		if (noGroupsMessage) {
			noGroupsMessage.remove();
		}

		// Create the table structure
		const tableHtml = `
			<div class="table-responsive">
				<table class="table table-hover">
					<thead>
						<tr>
							<th>Group Name</th>
							<th>Members</th>
							<th>Created</th>
							<th>Actions</th>
						</tr>
					</thead>
					<tbody>
					</tbody>
				</table>
			</div>
		`;
		cardBody.insertAdjacentHTML("beforeend", tableHtml);

		// Get the newly created table body
		tableBody = document.querySelector(".table-responsive .table tbody");
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

	newRow.innerHTML = `
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
                                onclick="deleteGroup('${groupData.uuid}', '${groupData.name}')">
                            <i class="bi bi-trash me-1"></i>Delete
                        </button>
                    </li>
                </ul>
            </div>
        </td>
    `;

	// Add the new row to the table
	tableBody.appendChild(newRow);
}

// Open manage modal for a specific group
function openManageModalForGroup(groupUuid, groupName) {
	// Set the current group info
	currentGroupUuid = groupUuid;
	currentGroupName = groupName;

	// Set the hidden input value
	document.getElementById("addGroupUuid").value = groupUuid;

	// Update modal title
	document.getElementById("manageMembersModalLabel").innerHTML =
		`<i class="bi bi-person-plus me-2"></i>Manage Members: ${groupName}`;

	// Clear pending removals
	pendingRemovals.clear();

	// Reset user search handler state
	if (shareGroupUserSearchHandler) {
		shareGroupUserSearchHandler.resetShareGroup();
	}

	// Load current members
	loadCurrentMembers();

	// Load and display shared assets information
	loadSharedAssetsInfo();

	// Show the modal
	const manageModal = new bootstrap.Modal(
		document.getElementById("share-modal-sharegroup"),
	);
	manageModal.show();
}

// Export functions for global access
window.deleteGroup = deleteGroup;
window.removeMemberFromGroup = removeMemberFromGroup;
window.initializeShareGroupManager = initializeShareGroupManager;
