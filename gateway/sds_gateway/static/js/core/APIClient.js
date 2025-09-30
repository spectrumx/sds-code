// PermissionLevels is now available globally

/**
 * Centralized API Client for all fetch operations
 * Handles CSRF tokens, error handling, and loading states consistently
 */
window.APIClient = class APIClient {
	/**
	 * Get CSRF token from various sources
	 * @returns {string} CSRF token
	 */
	getCSRFToken() {
		// Try meta tag first (most reliable)
		const metaToken = document.querySelector('meta[name="csrf-token"]');
		if (metaToken) {
			return metaToken.getAttribute("content");
		}

		// Fallback to input field
		const inputToken = document.querySelector('[name="csrfmiddlewaretoken"]');
		if (inputToken) {
			return inputToken.value;
		}

		// Last resort: try cookie
		const cookieToken = this.getCookie("csrftoken");
		if (cookieToken) {
			return cookieToken;
		}

		console.error("CSRF token not found");
		return "";
	}

	/**
	 * Get cookie value by name
	 * @param {string} name - Cookie name
	 * @returns {string|null} Cookie value
	 */
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

	/**
	 * Make API request with consistent error handling and CSRF
	 * @param {string} url - Request URL
	 * @param {Object} options - Fetch options
	 * @param {Object} loadingState - Loading state management object
	 * @returns {Promise<Object>} Response data
	 */
	async request(url, options = {}, loadingState = null) {
		// Set loading state
		if (loadingState) {
			loadingState.setLoading(true);
		}

		// Prepare headers
		const headers = {
			"X-Requested-With": "XMLHttpRequest",
			...options.headers,
		};

		// Add CSRF token for non-GET requests
		if (options.method && options.method !== "GET") {
			headers["X-CSRFToken"] = this.getCSRFToken();
		}

		try {
			const response = await fetch(url, {
				...options,
				headers,
			});

			// Handle non-OK responses
			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new APIError(
					`HTTP ${response.status}: ${response.statusText}`,
					response.status,
					errorData,
				);
			}

			// Parse response
			const contentType = response.headers.get("content-type");
			if (contentType?.includes("application/json")) {
				return await response.json();
			}
			return await response.text();
		} catch (error) {
			// Handle network errors
			if (error instanceof APIError) {
				throw error;
			}
			throw new APIError(`Network error: ${error.message}`, 0, {});
		} finally {
			// Clear loading state
			if (loadingState) {
				loadingState.setLoading(false);
			}
		}
	}

	/**
	 * Make GET request
	 * @param {string} url - Request URL
	 * @param {Object} params - Query parameters
	 * @param {Object} loadingState - Loading state management
	 * @returns {Promise<Object>} Response data
	 */
	async get(url, params = {}, loadingState = null) {
		const urlObj = new URL(url, window.location.origin);
		for (const [key, value] of Object.entries(params)) {
			if (value !== null && value !== undefined) {
				urlObj.searchParams.append(key, value);
			}
		}

		return this.request(urlObj.toString(), { method: "GET" }, loadingState);
	}

	/**
	 * Make POST request
	 * @param {string} url - Request URL
	 * @param {Object} data - Request data
	 * @param {Object} loadingState - Loading state management
	 * @returns {Promise<Object>} Response data
	 */
	async post(url, data = {}, loadingState = null) {
		const formData = new FormData();
		for (const [key, value] of Object.entries(data)) {
			if (value !== null && value !== undefined) {
				formData.append(key, value);
			}
		}

		return this.request(
			url,
			{
				method: "POST",
				body: formData,
			},
			loadingState,
		);
	}

	/**
	 * Make PATCH request
	 * @param {string} url - Request URL
	 * @param {Object} data - Request data
	 * @param {Object} loadingState - Loading state management
	 * @returns {Promise<Object>} Response data
	 */
	async patch(url, data = {}, loadingState = null) {
		const formData = new FormData();
		for (const [key, value] of Object.entries(data)) {
			if (value !== null && value !== undefined) {
				formData.append(key, value);
			}
		}

		return this.request(
			url,
			{
				method: "PATCH",
				body: formData,
			},
			loadingState,
		);
	}

	/**
	 * Make PUT request
	 * @param {string} url - Request URL
	 * @param {Object} data - Request data
	 * @param {Object} loadingState - Loading state management
	 * @returns {Promise<Object>} Response data
	 */
	async put(url, data = {}, loadingState = null) {
		const formData = new FormData();
		for (const [key, value] of Object.entries(data)) {
			if (value !== null && value !== undefined) {
				formData.append(key, value);
			}
		}

		return this.request(
			url,
			{
				method: "PUT",
				body: formData,
			},
			loadingState,
		);
	}
};

/**
 * Custom API Error class
 */
class APIError extends Error {
	constructor(message, status, data) {
		super(message);
		this.name = "APIError";
		this.status = status;
		this.data = data;
	}
}

/**
 * Loading State Manager
 */
class LoadingStateManager {
	constructor(element) {
		this.element = element;
		this.originalContent = element ? element.innerHTML : "";
		this.isLoading = false;
	}

	setLoading(loading) {
		if (this.isLoading === loading) return;

		this.isLoading = loading;

		if (!this.element) return;

		if (loading) {
			this.element.disabled = true;
			this.element.innerHTML =
				'<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Loading...';
		} else {
			this.element.disabled = false;
			this.element.innerHTML = this.originalContent;
		}
	}
}

/**
 * List Refresh Manager
 * Handles refreshing list pages and extracting data from HTML responses
 */
class ListRefreshManager {
	/**
	 * Refresh a list page and extract data
	 * @param {string} url - URL to fetch
	 * @param {Object} options - Options for data extraction
	 * @returns {Promise<Object>} Refreshed data and HTML
	 */
	async refreshList(url, options = {}) {
		const {
			extractData = true,
			updateTable = true,
			updateModals = true,
			modalSelector = ".modal[data-item-uuid][data-item-type]",
			tableSelector = ".table-and-pagination",
			mainSelector = "main",
		} = options;

		// Fetch fresh HTML
		const apiClient = new APIClient();
		const html = await apiClient.get(url);

		const result = { html };

		// Extract data if requested
		if (extractData) {
			result.data = this.extractDataFromHTML(html, {
				modalSelector,
				extractSharedUsers: true,
			});
		}

		// Update table if requested
		if (updateTable) {
			this.updateTableContent(html, {
				tableSelector,
				mainSelector,
			});
		}

		return result;
	}

	/**
	 * Extract data from HTML response
	 * @param {string} html - HTML response
	 * @param {Object} options - Extraction options
	 * @returns {Object} Extracted data
	 */
	extractDataFromHTML(html, options = {}) {
		const {
			modalSelector = ".modal[data-item-uuid][data-item-type]",
			extractSharedUsers = true,
		} = options;

		const tempDiv = document.createElement("div");
		tempDiv.innerHTML = html;

		// Find all modals in the fresh HTML
		const modals = tempDiv.querySelectorAll(modalSelector);
		const items = [];

		for (const modal of modals) {
			const itemUuid = modal.getAttribute("data-item-uuid");
			const itemType = modal.getAttribute("data-item-type");

			const item = {
				uuid: itemUuid,
				item_type: itemType,
			};

			// Extract shared users if requested
			if (extractSharedUsers) {
				const sharedUsers = this.extractSharedUsersFromModal(modal, itemUuid);
				item.shared_users = sharedUsers;
				item.owner_name = sharedUsers.find((u) => u.isOwner)?.name || "Owner";
				item.owner_email = sharedUsers.find((u) => u.isOwner)?.email || "";
			}

			items.push(item);
		}

		return { results: items };
	}

	/**
	 * Extract shared users from a modal element
	 * @param {Element} modal - Modal element
	 * @param {string} itemUuid - Item UUID
	 * @returns {Array} Array of shared users
	 */
	extractSharedUsersFromModal(modal, itemUuid) {
		const usersWithAccessSection = modal.querySelector(
			`#users-with-access-section-${itemUuid}`,
		);
		const sharedUsers = [];

		if (usersWithAccessSection) {
			const userRows = usersWithAccessSection.querySelectorAll("tbody tr");

			for (const [index, row] of userRows.entries()) {
				const nameElement = row.querySelector("h5");
				const emailElement = row.querySelector("small.text-muted");
				// Only select the permission dropdown, not the member count badge
				const permissionElement = row.querySelector(".access-level-dropdown");

				if (nameElement && emailElement) {
					const user = {
						index: index,
						name: nameElement.textContent.trim(),
						email: emailElement.textContent.trim(),
						permission_level: permissionElement
							? permissionElement.textContent.trim().toLowerCase()
							: window.PermissionLevels.VIEWER,
						isOwner: index === 0,
						type: nameElement.querySelector(".bi-people-fill")
							? "group"
							: "user",
					};
					sharedUsers.push(user);
				}
			}
		}

		return sharedUsers;
	}

	/**
	 * Update table content with fresh HTML
	 * @param {string} html - Fresh HTML
	 * @param {Object} options - Update options
	 */
	updateTableContent(html, options = {}) {
		const { tableSelector = ".table-and-pagination", mainSelector = "main" } =
			options;

		const tempDiv = document.createElement("div");
		tempDiv.innerHTML = html;

		// Update only the table content
		const mainContent = document.querySelector(mainSelector);
		const newMainContent = tempDiv.querySelector(mainSelector);

		if (mainContent && newMainContent) {
			const tableContainer = mainContent.querySelector(tableSelector);
			const newTableContainer = newMainContent.querySelector(tableSelector);

			if (tableContainer && newTableContainer) {
				tableContainer.innerHTML = newTableContainer.innerHTML;
			}
		}
	}

	/**
	 * Update modals with fresh shared users data
	 * @param {Array} items - Items with shared users data
	 * @param {Function} updateCallback - Callback to update individual modal
	 */
	updateModalsWithData(items, updateCallback) {
		for (const item of items) {
			const modal = document.getElementById(`share-modal-${item.uuid}`);
			if (modal && updateCallback) {
				updateCallback(modal, item);
			}
		}
	}
}

// Create instances and make them available globally
window.APIClient = new APIClient();
window.APIError = APIError;
window.LoadingStateManager = LoadingStateManager;
window.ListRefreshManager = new ListRefreshManager();

// Export for ES6 modules (Jest testing)
export { APIClient, APIError, LoadingStateManager, ListRefreshManager };
