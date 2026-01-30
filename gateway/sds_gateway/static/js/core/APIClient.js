// PermissionLevels is now available globally

/**
 * Centralized API Client for all fetch operations
 * Handles CSRF tokens, error handling, and loading states consistently
 */
class APIClient {
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
	 * @param {boolean} asJson - Whether to send as JSON (default: false, sends as form data)
	 * @returns {Promise<Object>} Response data
	 */
	async post(url, data = {}, loadingState = null, asJson = false) {
		if (asJson) {
			return this.request(
				url,
				{
					method: "POST",
					body: JSON.stringify(data),
					headers: {
						"Content-Type": "application/json",
					},
				},
				loadingState,
			);
		}

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
}

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
 * DatasetListManager - Handles dataset list table loading and updates
 */
class ListRefreshManager {
	/**
	 * Initialize dataset list manager
	 * @param {Object} config - Configuration object
	 * @param {string} config.containerSelector - Selector for the container element (default: '#dynamic-table-container')
	 * @param {string} config.url - Base URL for dataset list endpoint (default: '/users/dataset-list/')
	 */
	constructor(config = {}) {
		this.containerSelector = config.containerSelector;
		this.url = config.url;
		this.itemType = config.itemType;
		this.container = document.querySelector(this.containerSelector);
	}

	/**
	 * Load dataset list table via AJAX GET request
	 * @param {Object} params - Query parameters
	 * @param {number} params.page - Page number (default: 1)
	 * @param {string} params.sort_by - Sort field: 'name' | 'created_at' | 'updated_at' | 'authors' (default: 'created_at')
	 * @param {string} params.sort_order - Sort order: 'asc' | 'desc' (default: 'desc')
	 * @param {Object} options - Additional options
	 * @param {boolean} options.showLoading - Show loading state (default: true)
	 * @param {Function} options.onSuccess - Callback on success
	 * @param {Function} options.onError - Callback on error
	 * @returns {Promise<string>} HTML content of the table
	 */
	async loadTable(params = {}, options = {}) {
		const { page = 1, sort_by = "created_at", sort_order = "desc" } = params;

		const { showLoading = true, onSuccess = null, onError = null } = options;

		// Validate container exists
		if (!this.container) {
			const error = new Error(`Container not found: ${this.containerSelector}`);
			console.error(error.message);
			if (onError) {
				onError(error);
			}
			throw error;
		}

		// Show loading state if requested
		if (showLoading) {
			await window.DOMUtils?.renderLoading(
				this.container,
				"Loading datasets...",
				{ format: "spinner", size: "sm" },
			).catch(() => {
				// Fallback if DOMUtils is not available
				this.container.innerHTML =
					'<div class="text-center py-3"><span class="spinner-border spinner-border-sm me-2"></span>Loading...</div>';
			});
		}

		try {
			// Make GET request with query parameters
			const html = await window.APIClient.get(this.url, {
				page: page,
				sort_by: sort_by,
				sort_order: sort_order,
			});

			// Update container with HTML response
			if (typeof html === "string") {
				this.container.innerHTML = html;

				// Re-initialize any necessary event listeners after update
				this._reinitializeEventListeners();

				// Call success callback if provided
				if (onSuccess) {
					onSuccess(html);
				}

				return html;
			}
			throw new Error("Invalid response format: expected HTML string");
		} catch (error) {
			console.error(`Error loading ${this.itemType} list table:`, error);

			// Show error state
			await window.DOMUtils?.renderError(
				this.container,
				`Failed to load ${this.itemType} list. Please try again.`,
				{ format: "alert" },
			).catch(() => {
				// Fallback if DOMUtils is not available
				this.container.innerHTML = `<div class="alert alert-danger">Failed to load ${this.itemType} list. Please refresh the page.</div>`;
			});

			// Call error callback if provided
			if (onError) {
				onError(error);
			}

			throw error;
		}
	}

	/**
	 * Re-initialize event listeners after table update
	 * This ensures modals, dropdowns, and other interactive elements work after AJAX updates
	 */
	_reinitializeEventListeners() {
		// Re-initialize Bootstrap dropdowns
		if (typeof bootstrap !== "undefined" && bootstrap.Dropdown) {
			window.DOMUtils.initializeListDropdowns();
		}

		// Re-initialize tooltips if Bootstrap tooltips are available
		if (typeof bootstrap !== "undefined" && bootstrap.Tooltip) {
			for (const element of document.querySelectorAll(
				'[data-bs-toggle="tooltip"]',
			)) {
				// Dispose existing tooltip if any
				const existing = bootstrap.Tooltip.getInstance(element);
				if (existing) {
					existing.dispose();
				}

				// Create new tooltip instance
				new bootstrap.Tooltip(element);
			}
		}

		// Trigger page lifecycle manager re-initialization if available
		if (window.pageLifecycleManager) {
			// The PageLifecycleManager should handle modal re-initialization
			// You may need to call a refresh method if it exists
			if (typeof window.pageLifecycleManager.refresh === "function") {
				window.pageLifecycleManager.refresh();
			}
		}
	}
}

// Create instances and make them available globally
window.APIClient = new APIClient();
window.APIError = APIError;
window.LoadingStateManager = LoadingStateManager;
window.ListRefreshManager = ListRefreshManager;

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		APIClient,
		APIError,
		LoadingStateManager,
	};
}
