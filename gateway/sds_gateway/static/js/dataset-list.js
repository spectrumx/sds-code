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

	// Bootstrap handles dropdowns natively with data-bs-toggle="dropdown" - no custom handling needed

	// Check for dataset download alert messages only
	const downloadAlert = sessionStorage.getItem("datasetDownloadAlert");
	if (downloadAlert) {
		const alertData = JSON.parse(downloadAlert);
		showAlert(alertData.message, alertData.type);
		sessionStorage.removeItem("datasetDownloadAlert");
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
			if (window.components?.openCustomModal) {
				window.components.openCustomModal("downloadModal");
			} else {
				openCustomModal("downloadModal");
			}

			// Handle confirm download
			document.getElementById("confirmDownloadBtn").onclick = () => {
				// Close modal first
				if (window.components?.closeCustomModal) {
					window.components.closeCustomModal("downloadModal");
				} else {
					closeCustomModal("downloadModal");
				}

				// Use unified download handler
				if (window.components?.handleDownload) {
					window.components.handleDownload("dataset", datasetUuid, button);
				}
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

// Make functions available globally
window.openCustomModal = openCustomModal;
window.closeCustomModal = closeCustomModal;

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

// Make function available globally
window.showAlert = showAlert;

// Close modal when clicking backdrop
document.addEventListener("click", (event) => {
	if (event.target.classList.contains("custom-modal-backdrop")) {
		const modal = event.target.closest(".custom-modal");
		if (modal) {
			closeCustomModal(modal.id);
		}
	}
});

// Bootstrap handles dropdowns natively with data-bs-toggle="dropdown" - no custom handling needed
