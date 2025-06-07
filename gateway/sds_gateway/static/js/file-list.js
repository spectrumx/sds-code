/* File List Page JavaScript */

document.addEventListener("DOMContentLoaded", () => {
	console.log("File list script loaded!");

	// Helper function to format file size
	function formatFileSize(bytes) {
		if (bytes === 0) return "0 Bytes";
		const k = 1024;
		const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
	}

	// AJAX Search functionality
	const searchInput = document.getElementById("search-input");
	const searchBtn = document.getElementById("search-btn");
	const resetSearchBtn = document.getElementById("reset-search-btn");
	const loadingIndicator = document.getElementById("loading-indicator");
	const tableContainer = document.querySelector(".table-responsive");

	// Date filter inputs
	const startDateInput = document.getElementById("start_date");
	const endDateInput = document.getElementById("end_date");

	// Center frequency filter inputs
	const centerFreqMin = document.getElementById("centerFreqMin");
	const centerFreqMax = document.getElementById("centerFreqMax");
	const centerFreqMinInput = document.getElementById("centerFreqMinInput");
	const centerFreqMaxInput = document.getElementById("centerFreqMaxInput");
	const minFreqDisplay = document.getElementById("minFreqDisplay");
	const maxFreqDisplay = document.getElementById("maxFreqDisplay");
	const frequencyTrack = document.getElementById("frequencyTrack");

	// Filter buttons
	const applyFiltersBtn = document.querySelector('.btn-primary[type="submit"]');
	const clearFiltersBtn = document.querySelector('.btn-primary[type="button"]');

	console.log("Elements found:", {
		searchInput: !!searchInput,
		searchBtn: !!searchBtn,
		resetSearchBtn: !!resetSearchBtn,
		loadingIndicator: !!loadingIndicator,
		tableContainer: !!tableContainer,
		startDateInput: !!startDateInput,
		endDateInput: !!endDateInput,
		centerFreqMin: !!centerFreqMin,
		centerFreqMax: !!centerFreqMax,
		centerFreqMinInput: !!centerFreqMinInput,
		centerFreqMaxInput: !!centerFreqMaxInput,
		applyFiltersBtn: !!applyFiltersBtn,
		clearFiltersBtn: !!clearFiltersBtn,
	});

	// Get current sort parameters from URL
	const urlParams = new URLSearchParams(window.location.search);
	const currentSortBy = urlParams.get("sort_by") || "created_at";
	const currentSortOrder = urlParams.get("sort_order") || "desc";

	// Set initial date values from URL
	if (urlParams.get("date_start")) {
		startDateInput.value = urlParams.get("date_start");
	}
	if (urlParams.get("date_end")) {
		endDateInput.value = urlParams.get("date_end");
	}

	// Only set frequency values if they exist in URL and are meaningful
	if (urlParams.get("min_freq")?.trim()) {
		const minFreq = Number.parseFloat(urlParams.get("min_freq"));
		if (!Number.isNaN(minFreq)) {
			centerFreqMinInput.value = minFreq;
			if (centerFreqMin) centerFreqMin.value = minFreq;
		}
	}
	if (urlParams.get("max_freq")?.trim()) {
		const maxFreq = Number.parseFloat(urlParams.get("max_freq"));
		if (!Number.isNaN(maxFreq)) {
			centerFreqMaxInput.value = maxFreq;
			if (centerFreqMax) centerFreqMax.value = maxFreq;
		}
	}

	// Initialize dual range slider
	if (centerFreqMin && centerFreqMax && frequencyTrack) {
		console.log("Initializing dual range slider...");

		// Track whether user has interacted with sliders
		let userInteractedWithMin = false;
		let userInteractedWithMax = false;

		function updateTrack() {
			// Only update if both sliders have values AND user has interacted
			if (!userInteractedWithMin && !userInteractedWithMax) {
				// Clear the track and displays when no user interaction
				frequencyTrack.style.left = "0%";
				frequencyTrack.style.width = "0%";

				if (minFreqDisplay) {
					minFreqDisplay.textContent = "-- GHz";
				}
				if (maxFreqDisplay) {
					maxFreqDisplay.textContent = "-- GHz";
				}
				return;
			}

			const min = Number.parseFloat(centerFreqMin.min);
			const max = Number.parseFloat(centerFreqMax.max);
			const minVal = Number.parseFloat(centerFreqMin.value);
			const maxVal = Number.parseFloat(centerFreqMax.value);

			const minPercent = ((minVal - min) / (max - min)) * 100;
			const maxPercent = ((maxVal - min) / (max - min)) * 100;

			frequencyTrack.style.left = `${minPercent}%`;
			frequencyTrack.style.width = `${maxPercent - minPercent}%`;

			// Update displays
			if (minFreqDisplay) {
				minFreqDisplay.textContent = `${minVal.toFixed(1)} GHz`;
			}
			if (maxFreqDisplay) {
				maxFreqDisplay.textContent = `${maxVal.toFixed(1)} GHz`;
			}

			// Sync with input fields only if user has interacted
			if (
				userInteractedWithMin &&
				centerFreqMinInput &&
				centerFreqMinInput.value !== minVal
			) {
				centerFreqMinInput.value = minVal;
			}
			if (
				userInteractedWithMax &&
				centerFreqMaxInput &&
				centerFreqMaxInput.value !== maxVal
			) {
				centerFreqMaxInput.value = maxVal;
			}
		}

		function validateRange() {
			// Only validate and sync if user has interacted with sliders
			if (!userInteractedWithMin && !userInteractedWithMax) {
				return; // Don't sync if user hasn't interacted
			}

			let minVal = Number.parseFloat(centerFreqMin.value);
			let maxVal = Number.parseFloat(centerFreqMax.value);

			if (minVal > maxVal) {
				if (event.target === centerFreqMin) {
					centerFreqMax.value = minVal;
					maxVal = minVal;
					userInteractedWithMax = true;
				} else {
					centerFreqMin.value = maxVal;
					minVal = maxVal;
					userInteractedWithMin = true;
				}
			}

			// Only sync to inputs if user has interacted
			if (userInteractedWithMin) centerFreqMinInput.value = minVal;
			if (userInteractedWithMax) centerFreqMaxInput.value = maxVal;
			updateTrack();
		}

		// Range slider events - mark as user-interacted
		centerFreqMin.addEventListener("input", () => {
			userInteractedWithMin = true;
			validateRange();
		});

		centerFreqMax.addEventListener("input", () => {
			userInteractedWithMax = true;
			validateRange();
		});

		// Number input events
		centerFreqMinInput.addEventListener("change", function () {
			const val = Number.parseFloat(this.value);
			if (this.value && !Number.isNaN(val) && val >= 0 && val <= 10) {
				centerFreqMin.value = val;
				userInteractedWithMin = true;
				// Only validate if both inputs have values
				if (centerFreqMaxInput.value) {
					validateRange();
				} else {
					updateTrack();
				}
			} else if (!this.value) {
				// Clear the corresponding slider if input is empty
				centerFreqMin.value = "";
				userInteractedWithMin = false;
				updateTrack();
			}
		});

		centerFreqMaxInput.addEventListener("change", function () {
			const val = Number.parseFloat(this.value);
			if (this.value && !Number.isNaN(val) && val >= 0 && val <= 10) {
				centerFreqMax.value = val;
				userInteractedWithMax = true;
				// Only validate if both inputs have values
				if (centerFreqMinInput.value) {
					validateRange();
				} else {
					updateTrack();
				}
			} else if (!this.value) {
				// Clear the corresponding slider if input is empty
				centerFreqMax.value = "";
				userInteractedWithMax = false;
				updateTrack();
			}
		});

		// Only initialize the track if there are values from URL
		if (centerFreqMin.value || centerFreqMax.value) {
			// Mark as user-interacted if values came from URL
			if (centerFreqMinInput.value) userInteractedWithMin = true;
			if (centerFreqMaxInput.value) userInteractedWithMax = true;
			updateTrack();
		} else {
			// Start with empty display
			if (minFreqDisplay) {
				minFreqDisplay.textContent = "-- GHz";
			}
			if (maxFreqDisplay) {
				maxFreqDisplay.textContent = "-- GHz";
			}
		}
	}

	function performSearch() {
		const searchQuery = searchInput.value.trim();
		const startDate = startDateInput.value;
		const endDate = endDateInput.value;
		// Use input field values instead of slider values for frequency
		const minFreq = centerFreqMinInput ? centerFreqMinInput.value : "";
		const maxFreq = centerFreqMaxInput ? centerFreqMaxInput.value : "";

		console.log("Starting search with filters:", {
			search: searchQuery,
			startDate: startDate,
			endDate: endDate,
			minFreq: minFreq,
			maxFreq: maxFreq,
			sortBy: currentSortBy,
			sortOrder: currentSortOrder,
		});

		// Show loading indicator
		loadingIndicator.classList.remove("d-none");
		tableContainer.style.opacity = "0.5";

		// Build search URL for the dedicated API endpoint
		const searchParams = new URLSearchParams();
		if (searchQuery) searchParams.set("search", searchQuery);
		if (startDate) searchParams.set("date_start", startDate);
		if (endDate) searchParams.set("date_end", endDate);
		// Only add frequency parameters if they have non-empty values
		if (minFreq?.trim()) searchParams.set("min_freq", minFreq);
		if (maxFreq?.trim()) searchParams.set("max_freq", maxFreq);
		searchParams.set("sort_by", currentSortBy);
		searchParams.set("sort_order", currentSortOrder);

		// Use the dedicated API endpoint
		const apiUrl = `${window.location.pathname.replace(/\/$/, "")}/api/?${searchParams.toString()}`;
		console.log("API URL:", apiUrl);

		fetch(apiUrl, {
			method: "GET",
			headers: {
				Accept: "application/json",
			},
			credentials: "same-origin", // Include cookies for authentication
		})
			.then((response) => {
				if (!response.ok) {
					throw new Error(`HTTP ${response.status}: ${response.statusText}`);
				}
				return response.text().then((text) => {
					try {
						return JSON.parse(text);
					} catch (e) {
						console.error("Invalid JSON response:", text);
						throw new Error("Invalid JSON response from server");
					}
				});
			})
			.then((data) => {
				if (data.error) {
					throw new Error(`Server error: ${data.error}`);
				}
				// Update table with new data
				updateTable(data.captures, data.has_results);

				// Update URL without page refresh (remove /api/ from the URL)
				const newUrl = `${window.location.pathname}?${searchParams.toString()}`;
				window.history.pushState({}, "", newUrl);

				// Hide loading indicator
				loadingIndicator.classList.add("d-none");
				tableContainer.style.opacity = "1";
			})
			.catch((error) => {
				console.error("Search error:", error);
				// Hide loading indicator
				loadingIndicator.classList.add("d-none");
				tableContainer.style.opacity = "1";

				// Show error message in the table instead of falling back
				const tbody = document.querySelector("tbody");
				tbody.innerHTML = `
        <tr>
          <td colspan="8" class="text-center text-danger py-4">
            <i class="fas fa-exclamation-triangle"></i> Search failed: ${error.message}
            <br><small class="text-muted">Try refreshing the page or contact support if the problem persists.</small>
          </td>
        </tr>
      `;
			});
	}

	function updateTable(captures, hasResults) {
		const tbody = document.querySelector("tbody");

		if (!hasResults || captures.length === 0) {
			tbody.innerHTML = `
        <tr>
          <td colspan="8" class="text-center text-muted py-4">No captures found.</td>
        </tr>
      `;
			return;
		}

		let tableHTML = "";
		for (const cap of captures) {
			tableHTML += `
        <tr class="capture-row"
            data-uuid="${cap.uuid || ""}"
            data-channel="${cap.channel || ""}"
            data-scan-group="${cap.scan_group || ""}"
            data-capture-type="${cap.capture_type || ""}"
            data-top-level-dir="${cap.top_level_dir || ""}"
            data-index-name="${cap.index_name || ""}"
            data-owner="${cap.owner || ""}"
            data-origin="${cap.origin || ""}"
            data-dataset="${cap.dataset || ""}"
            data-created-at="${cap.created_at || ""}"
            data-updated-at="${cap.updated_at || ""}"
            data-is-public="${cap.is_public || ""}"
            data-is-deleted="${cap.is_deleted || ""}">
          <td>
            <div class="text-muted small">${cap.uuid || ""}</div>
          </td>
          <td>${cap.index_name || cap.channel || ""}</td>
          <td>${cap.channel || ""}</td>
          <td>${cap.created_at ? `${new Date(cap.created_at).toLocaleString()} UTC` : ""}</td>
          <td>${cap.capture_type || ""}</td>
          <td>${cap.files_count || "0"}${cap.total_file_size ? ` / <span class="text-muted">${formatFileSize(cap.total_file_size)}</span>` : ""}</td>
          <td>${cap.center_frequency_ghz ? `${cap.center_frequency_ghz.toFixed(3)} GHz` : '<span class="text-muted">-</span>'}</td>
          <td>${cap.sample_rate_mhz ? `${cap.sample_rate_mhz.toFixed(1)} MHz` : '<span class="text-muted">-</span>'}</td>
        </tr>
      `;
		}

		tbody.innerHTML = tableHTML;

		// Re-attach click handlers to new rows
		attachRowClickHandlers();
	}

	function attachRowClickHandlers() {
		const captureRows = document.querySelectorAll(".capture-row");
		for (const row of captureRows) {
			row.addEventListener("click", function (e) {
				e.preventDefault();
				openCaptureModal(this);
			});
		}
	}

	// Search on button click
	searchBtn.addEventListener("click", performSearch);

	// Date filter change events
	if (startDateInput) {
		startDateInput.addEventListener("change", function () {
			console.log("Start date changed to:", this.value);
			performSearch();
		});
	}

	if (endDateInput) {
		endDateInput.addEventListener("change", function () {
			console.log("End date changed to:", this.value);
			performSearch();
		});
	}

	// Apply filters button
	if (applyFiltersBtn) {
		applyFiltersBtn.addEventListener("click", (e) => {
			e.preventDefault();
			console.log("Apply filters clicked");
			performSearch();
		});
	}

	// Clear filters button
	if (clearFiltersBtn) {
		clearFiltersBtn.addEventListener("click", (e) => {
			e.preventDefault();
			console.log("Clear filters clicked");

			// Reset all filter inputs to empty values
			searchInput.value = "";
			if (startDateInput) startDateInput.value = "";
			if (endDateInput) endDateInput.value = "";

			// Clear frequency sliders completely - set to empty values, not min/max
			if (centerFreqMin) {
				centerFreqMin.value = "";
			}
			if (centerFreqMax) {
				centerFreqMax.value = "";
			}
			if (centerFreqMinInput) {
				centerFreqMinInput.value = "";
			}
			if (centerFreqMaxInput) {
				centerFreqMaxInput.value = "";
			}

			// Reset interaction tracking
			if (typeof userInteractedWithMin !== "undefined") {
				userInteractedWithMin = false;
				userInteractedWithMax = false;
			}

			// Update the visual slider track to show no selection
			if (centerFreqMin && centerFreqMax && frequencyTrack) {
				updateTrack(); // This will now show empty state
			}

			// Redirect to base URL to show original table state
			window.location.href = window.location.pathname;
		});
	}

	// Reset search button click
	if (resetSearchBtn) {
		console.log("Attaching reset search event listener...");
		resetSearchBtn.addEventListener("click", () => {
			console.log("Reset search button clicked!");
			console.log("Current search value before reset:", searchInput.value);
			searchInput.value = "";
			console.log("Search value after reset:", searchInput.value);
			console.log("Calling performSearch...");
			performSearch();
		});
		console.log("Reset search event listener attached successfully");
	} else {
		console.error("Reset search button not found!");
	}

	// Search on Enter key
	searchInput.addEventListener("keypress", (e) => {
		if (e.key === "Enter") {
			e.preventDefault();
			performSearch();
		}
	});

	// Modal logic for capture row clicks
	let currentModal = null; // Track the current modal instance

	function openCaptureModal(row) {
		// Dispose of any existing modal instance first
		if (currentModal) {
			currentModal.dispose();
			currentModal = null;
		}

		// Get all data attributes
		const uuid = row.getAttribute("data-uuid");
		const channel = row.getAttribute("data-channel");
		const scanGroup = row.getAttribute("data-scan-group");
		const captureType = row.getAttribute("data-capture-type");
		const topLevelDir = row.getAttribute("data-top-level-dir");
		const indexName = row.getAttribute("data-index-name");
		const owner = row.getAttribute("data-owner");
		const origin = row.getAttribute("data-origin");
		const dataset = row.getAttribute("data-dataset");
		const createdAt = row.getAttribute("data-created-at");
		const updatedAt = row.getAttribute("data-updated-at");
		const isPublic = row.getAttribute("data-is-public");
		const isDeleted = row.getAttribute("data-is-deleted");

		const modalBody = document.getElementById("channelModalBody");
		if (modalBody) {
			modalBody.innerHTML = `
        <div class="row">
          <div class="col-md-6">
            <h6 class="fw-bold">Basic Information</h6>
            <p><strong>UUID:</strong> ${uuid || "N/A"}</p>
            <p><strong>Index Name:</strong> ${indexName || "N/A"}</p>
            <p><strong>Channel:</strong> ${channel || "N/A"}</p>
            <p><strong>Capture Type:</strong> ${captureType || "N/A"}</p>
            <p><strong>Origin:</strong> ${origin || "N/A"}</p>
            <p><strong>Owner:</strong> ${owner || "N/A"}</p>
          </div>
          <div class="col-md-6">
            <h6 class="fw-bold">Technical Details</h6>
            <p><strong>Scan Group:</strong> ${scanGroup || "N/A"}</p>
            <p><strong>Top Level Directory:</strong> ${topLevelDir || "N/A"}</p>
            <p><strong>Dataset:</strong> ${dataset || "N/A"}</p>
            <p><strong>Is Public:</strong> ${isPublic === "True" ? "Yes" : "No"}</p>
            <p><strong>Is Deleted:</strong> ${isDeleted === "True" ? "Yes" : "No"}</p>
          </div>
        </div>
        <div class="row mt-3">
          <div class="col-12">
            <h6 class="fw-bold">Timestamps</h6>
            <p><strong>Created At:</strong> ${createdAt || "N/A"} UTC</p>
            <p><strong>Updated At:</strong> ${updatedAt || "N/A"} UTC</p>
          </div>
        </div>
      `;

			// Update modal title
			const modalTitle = document.getElementById("channelModalLabel");
			if (modalTitle) {
				modalTitle.textContent = `Capture Details - ${indexName || channel || "Unknown"}`;
			}

			// Create new modal instance and track it
			const modalElement = document.getElementById("channelModal");
			currentModal = new bootstrap.Modal(modalElement);

			// Add event listener for proper cleanup when modal is hidden
			modalElement.addEventListener(
				"hidden.bs.modal",
				() => {
					if (currentModal) {
						currentModal.dispose();
						currentModal = null;
					}
					// Ensure any remaining backdrop is removed
					const backdrop = document.querySelector(".modal-backdrop");
					if (backdrop) {
						backdrop.remove();
					}
					// Restore body scroll if needed
					document.body.classList.remove("modal-open");
					document.body.style.removeProperty("overflow");
					document.body.style.removeProperty("padding-right");
				},
				{ once: true },
			); // Use once: true so the listener is automatically removed

			currentModal.show();
		}
	}

	// Initial setup for existing rows
	attachRowClickHandlers();
});
