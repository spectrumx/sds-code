/**
 * Permission Levels JavaScript
 * Handles permission level selection and display functionality
 */

document.addEventListener("DOMContentLoaded", () => {
	initializePermissionLevels();
});

function initializePermissionLevels() {
	// Initialize permission level selectors
	const permissionSelects = document.querySelectorAll(
		'[id^="permission-level-"]',
	);

	permissionSelects.forEach((select) => {
		// Add change event listener
		select.addEventListener("change", handlePermissionLevelChange);

		// Add visual feedback on selection
		select.addEventListener("focus", function () {
			this.parentElement.classList.add("focused");
		});

		select.addEventListener("blur", function () {
			this.parentElement.classList.remove("focused");
		});
	});

	// Initialize permission level selectors for existing users
	initializeExistingUserPermissionSelectors();

	// Initialize permission badges with tooltips
	initializePermissionBadges();

	// Initialize group permission management
	initializeGroupPermissionManagement();

	// Initialize toggle buttons for member permissions
	initializeMemberPermissionToggles();
}

function initializeExistingUserPermissionSelectors() {
	// Handle permission level changes for existing users
	const existingUserSelectors = document.querySelectorAll(
		".permission-level-selector",
	);

	existingUserSelectors.forEach((select) => {
		select.addEventListener("change", handleExistingUserPermissionChange);

		// Add visual feedback
		select.addEventListener("focus", function () {
			this.classList.add("focused");
		});

		select.addEventListener("blur", function () {
			this.classList.remove("focused");
		});
	});
}

function handleExistingUserPermissionChange(event) {
	const select = event.target;
	const userEmail = select.getAttribute("data-user-email");
	const userName = select.getAttribute("data-user-name");
	const itemUuid = select.getAttribute("data-item-uuid");
	const itemType = select.getAttribute("data-item-type");
	const newPermissionLevel = select.value;

	// Show loading state
	select.disabled = true;
	select.classList.add("updating");

	// Prepare form data
	const formData = new FormData();
	formData.append("user_email", userEmail);
	formData.append("permission_level", newPermissionLevel);
	formData.append("csrfmiddlewaretoken", getCSRFToken());

	// Send PATCH request to update permission
	fetch(`/users/share/${itemType}/${itemUuid}/`, {
		method: "PATCH",
		body: formData,
		headers: {
			"X-Requested-With": "XMLHttpRequest",
		},
	})
		.then((response) => response.json())
		.then((data) => {
			if (data.success) {
				// Show success message
				showAlert(data.message, "success");

				// Update visual appearance
				updatePermissionSelectorAppearance(select, newPermissionLevel);

				// Trigger authors update if this is a dataset
				if (itemType === "dataset") {
					triggerDatasetAuthorsUpdate(itemUuid);
				}
			} else {
				// Show error message
				showAlert(data.error || "Failed to update permission level", "error");

				// Revert to previous value
				select.value = select.getAttribute("data-original-value") || "viewer";
			}
		})
		.catch((error) => {
			console.error("Error updating permission level:", error);
			showAlert("Failed to update permission level", "error");

			// Revert to previous value
			select.value = select.getAttribute("data-original-value") || "viewer";
		})
		.finally(() => {
			// Remove loading state
			select.disabled = false;
			select.classList.remove("updating");
		});
}

function updatePermissionSelectorAppearance(select, permissionLevel) {
	// Remove existing permission classes
	select.classList.remove(
		"permission-viewer",
		"permission-contributor",
		"permission-co-owner",
	);

	// Add new permission class
	select.classList.add(`permission-${permissionLevel}`);

	// Store the new value as original
	select.setAttribute("data-original-value", permissionLevel);
}

function triggerDatasetAuthorsUpdate(datasetUuid) {
	// Trigger a custom event to notify other components that authors have changed
	const event = new CustomEvent("datasetAuthorsUpdated", {
		detail: { datasetUuid: datasetUuid },
	});
	document.dispatchEvent(event);
}

function handlePermissionLevelChange(event) {
	const select = event.target;
	const selectedValue = select.value;
	const form = select.closest("form");
	const saveButton = form.querySelector('[id^="share-item-btn-"]');
	const pendingMessage = form.querySelector('[id^="pending-changes-message-"]');

	// Update visual feedback
	updatePermissionLevelVisualFeedback(select, selectedValue);

	// Update form data
	updateFormPermissionLevel(form, selectedValue);

	// Show pending changes message
	if (pendingMessage) {
		pendingMessage.classList.remove("d-none");
	}

	// Enable save button if there are selected users
	const selectedChips = form.querySelectorAll(".selected-user-chip");
	if (selectedChips.length > 0 && saveButton) {
		saveButton.disabled = false;
	}

	// Show permission level description
	showPermissionLevelDescription(select, selectedValue);
}

function updatePermissionLevelVisualFeedback(select, permissionLevel) {
	const section = select.closest(".permission-level-section");

	// Remove existing visual classes
	section.classList.remove(
		"viewer-selected",
		"contributor-selected",
		"co-owner-selected",
	);

	// Add new visual class
	section.classList.add(`${permissionLevel}-selected`);

	// Update select styling
	select.className = `form-select permission-${permissionLevel}`;
}

function updateFormPermissionLevel(form, permissionLevel) {
	// Remove existing hidden input
	const existingInput = form.querySelector('input[name="permission_level"]');
	if (existingInput) {
		existingInput.remove();
	}

	// Create new hidden input
	const hiddenInput = document.createElement("input");
	hiddenInput.type = "hidden";
	hiddenInput.name = "permission_level";
	hiddenInput.value = permissionLevel;
	form.appendChild(hiddenInput);
}

function showPermissionLevelDescription(select, permissionLevel) {
	const descriptions = {
		viewer: "Can view dataset information and download files",
		contributor: "Can add their own assets to the dataset",
		"co-owner": "Can add/remove assets and edit dataset metadata",
	};

	const description = descriptions[permissionLevel];
	if (description) {
		// Create or update description tooltip
		let tooltip = select.parentElement.querySelector(
			".permission-description-tooltip",
		);
		if (!tooltip) {
			tooltip = document.createElement("div");
			tooltip.className =
				"permission-description-tooltip alert alert-info mt-2";
			tooltip.style.fontSize = "0.875rem";
			select.parentElement.appendChild(tooltip);
		}

		tooltip.innerHTML = `<i class="bi bi-info-circle me-1"></i>${description}`;

		// Auto-hide after 3 seconds
		setTimeout(() => {
			if (tooltip && tooltip.parentElement) {
				tooltip.remove();
			}
		}, 3000);
	}
}

function initializePermissionBadges() {
	const permissionBadges = document.querySelectorAll(".permission-badge");

	permissionBadges.forEach((badge) => {
		// Add hover tooltip
		const permissionLevel = badge.textContent
			.trim()
			.toLowerCase()
			.replace(/\s+/g, "-");
		const tooltips = {
			"co-owner":
				"Full access: Can add/remove assets and edit dataset metadata",
			contributor: "Can add assets: Can add their own assets to the dataset",
			viewer: "Read-only: Can view dataset information and download files",
			owner: "Dataset owner: Full control over the dataset",
		};

		const tooltip = tooltips[permissionLevel];
		if (tooltip) {
			badge.setAttribute("data-bs-toggle", "tooltip");
			badge.setAttribute("data-bs-placement", "top");
			badge.setAttribute("title", tooltip);
		}

		// Add click animation
		badge.addEventListener("click", function () {
			this.style.transform = "scale(1.1)";
			setTimeout(() => {
				this.style.transform = "";
			}, 200);
		});
	});

	// Initialize Bootstrap tooltips
	if (typeof bootstrap !== "undefined" && bootstrap.Tooltip) {
		const tooltipTriggerList = [].slice.call(
			document.querySelectorAll('[data-bs-toggle="tooltip"]'),
		);
		tooltipTriggerList.map(
			(tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl),
		);
	}
}

// Group permission management functions
function initializeGroupPermissionManagement() {
	// Handle group permission level changes
	const groupPermissionSelectors = document.querySelectorAll(
		".group-permission-selector",
	);

	groupPermissionSelectors.forEach((select) => {
		select.addEventListener("change", handleGroupPermissionChange);
	});

	// Handle individual member permission changes within groups
	const memberPermissionSelectors = document.querySelectorAll(
		".member-permission-selector",
	);

	memberPermissionSelectors.forEach((select) => {
		select.addEventListener("change", handleMemberPermissionChange);
	});
}

function initializeMemberPermissionToggles() {
	// Handle toggle buttons for member permissions
	const toggleButtons = document.querySelectorAll(".toggle-member-permissions");

	toggleButtons.forEach((button) => {
		button.addEventListener("click", function () {
			const memberPermissions = this.parentElement.querySelector(
				".member-permissions",
			);
			const icon = this.querySelector("i");

			if (memberPermissions.style.display === "none") {
				memberPermissions.style.display = "block";
				icon.className = "bi bi-chevron-up";
				this.innerHTML =
					'<i class="bi bi-chevron-up"></i> Hide Individual Permissions';
			} else {
				memberPermissions.style.display = "none";
				icon.className = "bi bi-chevron-down";
				this.innerHTML =
					'<i class="bi bi-chevron-down"></i> Manage Individual Permissions';
			}
		});
	});
}

function handleGroupPermissionChange(event) {
	const select = event.target;
	const groupUuid = select.getAttribute("data-group-uuid");
	const itemUuid = select.getAttribute("data-item-uuid");
	const itemType = select.getAttribute("data-item-type");
	const newPermissionLevel = select.value;

	// Don't send request for "multiple" selection
	if (newPermissionLevel === "multiple") {
		return;
	}

	// Show loading state
	select.disabled = true;
	select.classList.add("updating");

	// Prepare form data
	const formData = new FormData();
	formData.append("group_uuid", groupUuid);
	formData.append("permission_level", newPermissionLevel);
	formData.append("csrfmiddlewaretoken", getCSRFToken());

	// Send PUT request to update group permissions
	fetch(`/users/share/${itemType}/${itemUuid}/`, {
		method: "PUT",
		body: formData,
		headers: {
			"X-Requested-With": "XMLHttpRequest",
		},
	})
		.then((response) => response.json())
		.then((data) => {
			if (data.success) {
				// Show success message
				showAlert(data.message, "success");

				// Update all member permissions to match group permission
				const memberSelectors = document.querySelectorAll(
					`[data-group-uuid="${groupUuid}"].member-permission-selector`,
				);

				memberSelectors.forEach((memberSelect) => {
					memberSelect.value = newPermissionLevel;
					memberSelect.classList.remove(
						"permission-viewer",
						"permission-contributor",
						"permission-co-owner",
					);
					memberSelect.classList.add(`permission-${newPermissionLevel}`);
				});

				// Update group selector appearance
				updatePermissionSelectorAppearance(select, newPermissionLevel);

				// Trigger authors update if this is a dataset
				if (itemType === "dataset") {
					triggerDatasetAuthorsUpdate(itemUuid);
				}
			} else {
				// Show error message
				showAlert(
					data.error || "Failed to update group permission level",
					"error",
				);

				// Revert to previous value
				select.value = select.getAttribute("data-original-value") || "viewer";
			}
		})
		.catch((error) => {
			console.error("Error updating group permission level:", error);
			showAlert("Failed to update group permission level", "error");

			// Revert to previous value
			select.value = select.getAttribute("data-original-value") || "viewer";
		})
		.finally(() => {
			// Remove loading state
			select.disabled = false;
			select.classList.remove("updating");
		});
}

function handleMemberPermissionChange(event) {
	const select = event.target;
	const groupUuid = select.getAttribute("data-group-uuid");
	const memberEmail = select.getAttribute("data-member-email");
	const itemUuid = select.getAttribute("data-item-uuid");
	const itemType = select.getAttribute("data-item-type");
	const newPermissionLevel = select.value;

	// Show loading state
	select.disabled = true;
	select.classList.add("updating");

	// Prepare form data
	const formData = new FormData();
	formData.append("user_email", memberEmail);
	formData.append("permission_level", newPermissionLevel);
	formData.append("csrfmiddlewaretoken", getCSRFToken());

	// Send PATCH request to update individual member permission
	fetch(`/users/share/${itemType}/${itemUuid}/`, {
		method: "PATCH",
		body: formData,
		headers: {
			"X-Requested-With": "XMLHttpRequest",
		},
	})
		.then((response) => response.json())
		.then((data) => {
			if (data.success) {
				// Show success message
				showAlert(
					`Updated ${memberEmail} to ${newPermissionLevel} permission`,
					"success",
				);

				// Check if all members have the same permission level
				const memberSelectors = document.querySelectorAll(
					`[data-group-uuid="${groupUuid}"].member-permission-selector`,
				);
				const allSame = Array.from(memberSelectors).every(
					(memberSelect) => memberSelect.value === newPermissionLevel,
				);

				// Update group selector
				const groupSelector = document.querySelector(
					`[data-group-uuid="${groupUuid}"].group-permission-selector`,
				);
				if (groupSelector) {
					if (allSame) {
						groupSelector.value = newPermissionLevel;
						updatePermissionSelectorAppearance(
							groupSelector,
							newPermissionLevel,
						);
					} else {
						groupSelector.value = "multiple";
						groupSelector.classList.add("permission-multiple");
					}
				}

				// Update member selector appearance
				updatePermissionSelectorAppearance(select, newPermissionLevel);

				// Trigger authors update if this is a dataset
				if (itemType === "dataset") {
					triggerDatasetAuthorsUpdate(itemUuid);
				}
			} else {
				// Show error message
				showAlert(
					data.error || "Failed to update member permission level",
					"error",
				);

				// Revert to previous value
				select.value = select.getAttribute("data-original-value") || "viewer";
			}
		})
		.catch((error) => {
			console.error("Error updating member permission level:", error);
			showAlert("Failed to update member permission level", "error");

			// Revert to previous value
			select.value = select.getAttribute("data-original-value") || "viewer";
		})
		.finally(() => {
			// Remove loading state
			select.disabled = false;
			select.classList.remove("updating");
		});
}

// Utility functions
function getCSRFToken() {
	const tokenElement = document.querySelector("[name=csrfmiddlewaretoken]");
	return tokenElement ? tokenElement.value : "";
}

function showAlert(message, type = "info") {
	// Use existing alert system if available
	if (window.showAlert) {
		window.showAlert(message, type);
	} else {
		// Fallback alert
		alert(`${type.toUpperCase()}: ${message}`);
	}
}

// Export functions for use in other modules
window.PermissionLevels = {
	initialize: initializePermissionLevels,
	handleChange: handlePermissionLevelChange,
	updateVisualFeedback: updatePermissionLevelVisualFeedback,
	showDescription: showPermissionLevelDescription,
	initializeBadges: initializePermissionBadges,
	initializeGroupManagement: initializeGroupPermissionManagement,
	handleExistingUserChange: handleExistingUserPermissionChange,
	handleGroupChange: handleGroupPermissionChange,
	handleMemberChange: handleMemberPermissionChange,
};
