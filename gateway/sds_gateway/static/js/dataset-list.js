document.addEventListener("DOMContentLoaded", () => {
	// Initialize sorting
	const sortableHeaders = document.querySelectorAll("th.sortable");
	const urlParams = new URLSearchParams(window.location.search);
	const currentSort = urlParams.get("sort_by") || "created_at";
	const currentOrder = urlParams.get("sort_order") || "desc";

	// Initialize sort icons
	function updateSortIcons() {
		for (const header of sortableHeaders) {
			const sortField = header.getAttribute("data-sort");
			const icon = header.querySelector(".sort-icon");

			// Reset all icons
			header.setAttribute("aria-sort", "none");
			icon.classList.remove("bi-caret-up-fill", "bi-caret-down-fill");
			icon.classList.add("bi-caret-down-fill");

			// Update current sort column
			if (sortField === currentSort) {
				if (currentOrder === "asc") {
					header.setAttribute("aria-sort", "ascending");
					icon.classList.remove("bi-caret-down-fill");
					icon.classList.add("bi-caret-up-fill");
				} else {
					header.setAttribute("aria-sort", "descending");
				}
			}
		}
	}

	// Handle sort clicks
	function handleSort(header) {
		const sortField = header.getAttribute("data-sort");
		let newOrder = "desc";

		// If already sorting by this field, toggle order
		if (currentSort === sortField && currentOrder === "asc") {
			newOrder = "desc";
		}

		// Update URL with new sort parameters
		urlParams.set("sort_by", sortField);
		urlParams.set("sort_order", newOrder);
		urlParams.set("page", "1"); // Reset to first page when sorting

		// Navigate to sorted results
		window.location.search = urlParams.toString();
	}

	// Add click handlers to sortable headers
	for (const header of sortableHeaders) {
		header.style.cursor = "pointer";
		header.addEventListener("click", () => handleSort(header));
	}

	// Initialize sort icons
	updateSortIcons();

	// Bootstrap handles dropdowns natively - no custom handling needed

	// Check for download alert messages
	const downloadAlert = sessionStorage.getItem("downloadAlert");
	if (downloadAlert) {
		const alertData = JSON.parse(downloadAlert);
		showAlert(alertData.message, alertData.type);
		sessionStorage.removeItem("downloadAlert");
	}

	// Handle download button clicks
	for (const button of document.querySelectorAll(".download-dataset-btn")) {
		button.addEventListener("click", function (e) {
			e.preventDefault();
			e.stopPropagation();

			const datasetUuid = this.getAttribute("data-dataset-uuid");
			const datasetName = this.getAttribute("data-dataset-name");

			// Update modal content
			document.getElementById("downloadDatasetName").textContent = datasetName;

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
				fetch(`/users/dataset-download/${datasetUuid}/`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")
							.value,
					},
				})
					.then((response) => response.json())
					.then((data) => {
						if (data.message && data.task_id) {
							button.innerHTML =
								'<i class="bi bi-check-circle text-success"></i> Download Requested';
							showAlert(
								"Download request submitted successfully! You will receive an email when ready.",
								"success",
							);
						} else {
							button.innerHTML =
								'<i class="bi bi-exclamation-triangle text-danger"></i> Request Failed';
							showAlert(
								data.message || "Download request failed. Please try again.",
								"error",
							);
						}
					})
					.catch((error) => {
						console.error("Download error:", error);
						button.innerHTML =
							'<i class="bi bi-exclamation-triangle text-danger"></i> Request Failed';
						showAlert(
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
});

function openCustomModal(modalId) {
	const modal = document.getElementById(modalId);
	if (modal) {
		modal.style.display = "block";
		document.body.style.overflow = "hidden";
	}
}

function closeCustomModal(modalId) {
	const modal = document.getElementById(modalId);
	if (modal) {
		modal.style.display = "none";
		document.body.style.overflow = "auto";
	}
}

// Function to show alerts
function showAlert(message, type) {
	const alertClass = type === "success" ? "alert-success" : "alert-danger";
	const alertHtml = `
		<div class="alert ${alertClass} alert-dismissible fade show" role="alert">
			${message}
			<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
		</div>
	`;

	const alertContainer = document.querySelector(
		".main-content-area .container",
	);
	if (alertContainer) {
		alertContainer.insertAdjacentHTML("afterbegin", alertHtml);
	}
}

// Close modal when clicking backdrop
document.addEventListener("click", (event) => {
	if (event.target.classList.contains("custom-modal-backdrop")) {
		const modal = event.target.closest(".custom-modal");
		if (modal) {
			closeCustomModal(modal.id);
		}
	}
});

function initDropdowns() {
	// Remove existing event listeners by cloning and replacing elements
	for (const toggle of document.querySelectorAll(".dropdown-toggle")) {
		const newToggle = toggle.cloneNode(true);
		toggle.parentNode.replaceChild(newToggle, toggle);
	}

	// Handle dropdown toggles
	for (const toggle of document.querySelectorAll(".dropdown-toggle")) {
		toggle.addEventListener("click", function (e) {
			e.preventDefault();
			e.stopPropagation();

			const dropdown = this.nextElementSibling;
			const isOpen = dropdown.classList.contains("show");

			// Close all other dropdowns
			for (const menu of document.querySelectorAll(".dropdown-menu.show")) {
				menu.classList.remove("show");
			}

			// Toggle current dropdown
			if (!isOpen) {
				dropdown.classList.add("show");
			}
		});
	}
}

// Global event listener for closing dropdowns (only add once)
if (!window.dropdownOutsideListenerAdded) {
	document.addEventListener("click", (e) => {
		if (!e.target.closest(".dropdown")) {
			for (const menu of document.querySelectorAll(".dropdown-menu.show")) {
				menu.classList.remove("show");
			}
		}
	});
	window.dropdownOutsideListenerAdded = true;
}
