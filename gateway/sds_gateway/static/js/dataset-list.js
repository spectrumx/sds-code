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

	// Handle dataset download
	const downloadButtons = document.querySelectorAll(".download-btn");
	const downloadModal = document.getElementById("downloadModal");
	const datasetNameSpan = document.getElementById("datasetName");
	const confirmDownloadBtn = document.getElementById("confirmDownloadBtn");
	let currentDatasetUuid = null;

	for (const button of downloadButtons) {
		button.addEventListener("click", function () {
			currentDatasetUuid = this.getAttribute("data-uuid");
			const datasetName = this.getAttribute("data-name");
			datasetNameSpan.textContent = datasetName;
		});
	}

	confirmDownloadBtn.addEventListener("click", async () => {
		if (!currentDatasetUuid) return;

		try {
			const response = await fetch(
				`/users/dataset/${currentDatasetUuid}/download/`,
				{
					method: "POST",
					headers: {
						"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")
							.value,
					},
				},
			);

			if (response.ok) {
				const data = await response.json();
				if (data.redirect_url) {
					window.location.href = data.redirect_url;
				}
			} else {
				console.error("Download failed");
			}
		} catch (error) {
			console.error("Error:", error);
		}
	});
});
