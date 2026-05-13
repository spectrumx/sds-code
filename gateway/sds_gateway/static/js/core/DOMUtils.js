/**
 * DOM Utility Functions
 * Provides basic DOM manipulation utilities (show, hide, showAlert)
 *
 * NOTE: This class does NOT generate HTML from user data.
 * All HTML containing server data should be rendered server-side using Django templates.
 *
 * Available methods:
 * - formatFileSize(bytes) - Format file size
 * - show(element, displayClass) - Show element with CSS class
 * - hide(element, displayClass) - Hide element with CSS class
 * - showAlert(message, type) - Show Bootstrap toast notification
 */
class DOMUtils {
	/**
	 * Format file size
	 * @param {number} bytes - File size in bytes
	 * @returns {string} Formatted file size
	 */
	formatFileSize(bytes) {
		const n = Number(bytes);
		if (!Number.isFinite(n) || n < 0) return "0 bytes";
		if (n === 0) return "0 bytes";
		const units = ["bytes", "KB", "MB", "GB"];
		let i = 0;
		let v = n;
		while (v >= 1024 && i < units.length - 1) {
			v /= 1024;
			i++;
		}
		return `${i === 0 ? v : v.toFixed(2)} ${units[i]}`;
	}

	/**
	 * Show element using CSS classes
	 * @param {Element|string} element - Element or selector to show
	 * @param {string} displayClass - CSS display class to add (default: "display-block")
	 */
	show(element, displayClass = "display-block") {
		const el =
			typeof element === "string" ? document.querySelector(element) : element;
		if (!el) {
			console.warn("Element not found for show():", element);
			return;
		}

		el.classList.remove("display-none", "d-none");
		el.classList.add(displayClass);
	}

	/**
	 * Hide element using CSS classes
	 * @param {Element|string} element - Element or selector to hide
	 * @param {string} displayClass - CSS display class to remove (default: "display-block")
	 */
	hide(element, displayClass = "display-block") {
		const el =
			typeof element === "string" ? document.querySelector(element) : element;
		if (!el) {
			console.warn("Element not found for hide():", element);
			return;
		}

		el.classList.remove(displayClass);
		el.classList.add("display-none");
	}

	/**
	 * Escape text for safe HTML interpolation (textContent round-trip).
	 * @param {string} text
	 * @returns {string}
	 */
	escapeHtml(text) {
		if (!text) return "";
		const div = document.createElement("div");
		div.textContent = text;
		return div.innerHTML;
	}

	formatDate(dateString) {
		if (!dateString) return "<div>-</div>";

		let date;
		if (typeof dateString === "string") {
			date = new Date(dateString);
		} else {
			date = new Date(dateString);
		}

		if (!date || Number.isNaN(date.getTime())) {
			return "<div>-</div>";
		}

		const month = String(date.getMonth() + 1).padStart(2, "0");
		const day = String(date.getDate()).padStart(2, "0");
		const year = date.getFullYear();
		const hours = date.getHours();
		const minutes = String(date.getMinutes()).padStart(2, "0");
		const seconds = String(date.getSeconds()).padStart(2, "0");
		const ampm = hours >= 12 ? "PM" : "AM";
		const displayHours = hours % 12 || 12;

		return `<div>${month}/${day}/${year}</div><small class="text-muted">${displayHours}:${minutes}:${seconds} ${ampm}</small>`;
	}

	formatDateForModal(dateString) {
		if (!dateString || dateString === "None") {
			return "N/A";
		}

		try {
			const date = new Date(dateString);
			if (Number.isNaN(date.getTime())) {
				return "N/A";
			}

			const year = date.getFullYear();
			const month = String(date.getMonth() + 1).padStart(2, "0");
			const day = String(date.getDate()).padStart(2, "0");
			const dateFormatted = `${year}-${month}-${day}`;

			const hours = String(date.getHours()).padStart(2, "0");
			const minutes = String(date.getMinutes()).padStart(2, "0");
			const seconds = String(date.getSeconds()).padStart(2, "0");
			const timezone = date
				.toLocaleTimeString("en-US", { timeZoneName: "short" })
				.split(" ")[1];
			const timeFormatted = `${hours}:${minutes}:${seconds} ${timezone}`;

			return `<span class="bg-transparent pe-2">${dateFormatted}</span><span class="text-muted bg-transparent">${timeFormatted}</span>`;
		} catch (error) {
			console.error("Error formatting capture date:", error);
			return "N/A";
		}
	}

	formatDateSimple(dateString) {
		try {
			const date = new Date(dateString);
			return date.toString() !== "Invalid Date"
				? date.toLocaleDateString("en-US", {
						month: "2-digit",
						day: "2-digit",
						year: "numeric",
					})
				: "";
		} catch (_e) {
			return "";
		}
	}

	/**
	 * Deduped error surface: console + optional toast (no legacy globals).
	 * @param {string} message
	 * @param {string} context
	 * @param {Error|null} error
	 */
	showError(message, context = "", error = null) {
		if (!this._notificationDedup) {
			this._notificationDedup = new Set();
		}
		const messageKey = `${context}:${message}`;
		if (this._notificationDedup.has(messageKey)) {
			if (error) {
				console.error(`[${context}]`, error);
			}
			return;
		}
		this._notificationDedup.add(messageKey);

		if (error) {
			console.error(`[${context}]`, {
				message: error.message,
				stack: error.stack,
				userMessage: message,
			});
		} else {
			console.warn(`[${context}]`, message);
		}

		void this.showAlert(message, "error");
	}

	getUserFriendlyErrorMessage(error, _context = "") {
		if (!error) return "An unexpected error occurred";

		if (error.name === "TypeError" && error.message.includes("Cannot read")) {
			return "Configuration error: Some components are not properly loaded";
		}
		if (error.name === "ReferenceError") {
			return "Component error: Required functionality is not available";
		}

		return error.message || "An unexpected error occurred";
	}

	/**
	 * Show global toast notification
	 * Renders toast using Django template toast.html
	 * @param {string} message - Toast message
	 * @param {string} type - Toast type (success, error, warning, info)
	 */
	async showAlert(message, type = "success") {
		const toastContainer = document.getElementById("toast-container");
		if (!toastContainer) {
			console.warn("Toast container not found");
			return;
		}

		const toastId = `toast-${Date.now()}-${Math.floor(Math.random() * 1000)}`;

		try {
			// Render toast using Django template
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template: "users/components/toast.html",
					context: {
						message: message,
						type: type,
					},
				},
				null,
				true,
			); // true = send as JSON

			if (!response.html) {
				console.error("No HTML returned from toast template");
				return;
			}

			// Create a temporary container to parse the HTML
			const tempDiv = document.createElement("div");
			tempDiv.innerHTML = response.html;
			const toastDiv = tempDiv.firstElementChild;

			if (!toastDiv) {
				console.error("Failed to parse toast HTML");
				return;
			}

			// Set unique ID for the toast
			toastDiv.id = toastId;

			// Append to toast container
			toastContainer.appendChild(toastDiv);

			// Initialize and show Bootstrap toast
			if (!window.bootstrap || !bootstrap.Toast) {
				console.error("Bootstrap not available");
				return;
			}

			const toast = new bootstrap.Toast(toastDiv);
			toast.show();
			toastDiv.addEventListener("hidden.bs.toast", () => toastDiv.remove());
		} catch (error) {
			console.error("Error rendering toast template:", error);
		}
	}

	/**
	 * Show modal loading state
	 * @param {string} modalId - Modal ID
	 */
	async showModalLoading(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const modalBody = modal.querySelector(".modal-body");
		if (modalBody) {
			// Store original content before showing loading
			if (!modalBody.dataset.originalContent) {
				modalBody.dataset.originalContent = modalBody.innerHTML;
			}

			await this.renderLoading(modalBody, "Loading modal...", {
				format: "modal",
			});
		}
	}

	/**
	 * Clear modal loading state and restore original content
	 * @param {string} modalId - Modal ID
	 */
	clearModalLoading(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const modalBody = modal.querySelector(".modal-body");
		if (modalBody?.dataset.originalContent) {
			// Restore original content
			modalBody.innerHTML = modalBody.dataset.originalContent;
			// Clean up the stored content
			delete modalBody.dataset.originalContent;
		}
	}

	/**
	 * Show modal error
	 * @param {string} modalId - Modal ID
	 * @param {string} message - Error message
	 */
	async showModalError(modalId, message) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const modalBody = modal.querySelector(".modal-body");
		if (modalBody) {
			await this.renderError(modalBody, message, {
				format: "alert",
				alert_type: "danger",
				icon: "exclamation-triangle",
			});
		}

		// Show modal even with error
		this.openModal(modalId);
	}

	/**
	 * Open modal
	 * @param {string} modalId - Modal ID
	 */
	openModal(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		// Check if modal instance already exists
		let bootstrapModal = bootstrap.Modal.getInstance(modal);

		// If instance exists but is in a bad state (no _config), dispose and recreate
		if (
			bootstrapModal &&
			(!bootstrapModal._config || !bootstrapModal._config.backdrop)
		) {
			try {
				bootstrapModal.dispose();
				bootstrapModal = null;
			} catch (_e) {
				// If disposal fails, force remove the instance
				bootstrapModal = null;
			}
		}

		// If no instance exists, create one with default config
		if (!bootstrapModal) {
			bootstrapModal = new bootstrap.Modal(modal, {
				backdrop: true,
				keyboard: true,
				focus: true,
			});
		}

		bootstrapModal.show();
	}

	/**
	 * Close modal
	 * @param {string} modalId - Modal ID
	 */
	closeModal(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;

		const bootstrapModal = bootstrap.Modal.getInstance(modal);
		if (!bootstrapModal) return;

		bootstrapModal.hide();
	}

	/**
	 * Bootstrap icon action menus: dispose/recreate instances; global listeners once.
	 * @param {ParentNode} [root]
	 */
	initIconDropdowns(root = document) {
		if (typeof bootstrap === "undefined" || !bootstrap.Dropdown) {
			return;
		}

		if (!this._iconDropdownShowDelegated) {
			this._iconDropdownShowDelegated = true;
			document.addEventListener("show.bs.dropdown", (e) => {
				const toggle = e.target?.closest?.(".btn-icon-dropdown");
				if (!toggle) return;
				const dropdownMenu = toggle.nextElementSibling;
				if (dropdownMenu?.classList.contains("dropdown-menu")) {
					document.body.appendChild(dropdownMenu);
				}
			});
		}

		if (!this._dropdownStopRowClickBound) {
			this._dropdownStopRowClickBound = true;
			document.addEventListener("click", (event) => {
				if (
					event.target.closest(".dropdown") ||
					event.target.closest(".btn-icon-dropdown") ||
					event.target.closest(".dropdown-toggle") ||
					event.target.closest(".dropdown-menu")
				) {
					event.stopPropagation();
				}
			});
		}

		for (const toggle of root.querySelectorAll(".btn-icon-dropdown")) {
			const existing = bootstrap.Dropdown.getInstance(toggle);
			if (existing) {
				existing.dispose();
			}
			new bootstrap.Dropdown(toggle, {
				container: "body",
				boundary: "viewport",
				popperConfig: {
					modifiers: [
						{
							name: "preventOverflow",
							options: {
								boundary: "viewport",
							},
						},
					],
				},
			});
		}
	}

	/**
	 * @param {ParentNode} [root]
	 */
	initializeListDropdowns(root = document) {
		this.initIconDropdowns(root);
	}

	/**
	 * Render error using Django template
	 * @param {Element|string} container - Container element or selector
	 * @param {string} message - Error message
	 * @param {Object} options - Additional options (format, colspan, error_list, etc.)
	 * @returns {Promise<boolean>} Success status
	 */
	async renderError(container, message, options = {}) {
		const el =
			typeof container === "string"
				? document.querySelector(container)
				: container;
		if (!el) {
			console.warn("Container not found for renderError:", container);
			return false;
		}

		const context = {
			message: message,
			format: options.format || "inline",
			...options,
		};

		try {
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template: "users/components/error.html",
					context: context,
				},
				null,
				true,
			); // true = send as JSON

			if (response.html) {
				el.innerHTML = response.html;
				return true;
			}
			return false;
		} catch (error) {
			console.error("Error rendering error template:", error);
			return false;
		}
	}

	/**
	 * Render loading state using Django template
	 * @param {Element|string} container - Container element or selector
	 * @param {string} text - Loading message
	 * @param {Object} options - Additional options (format, size, color)
	 * @returns {Promise<boolean>} Success status
	 */
	async renderLoading(container, text = "Loading...", options = {}) {
		const el =
			typeof container === "string"
				? document.querySelector(container)
				: container;
		if (!el) {
			console.warn("Container not found for renderLoading:", container);
			return false;
		}

		const context = {
			text: text,
			format: options.format || "spinner",
			size: options.size || "md",
			color: options.color || "primary",
			...options,
		};

		try {
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template: "users/components/loading.html",
					context: context,
				},
				null,
				true,
			); // true = send as JSON

			if (response.html) {
				el.innerHTML = response.html;
				return true;
			}
			return false;
		} catch (error) {
			console.error("Error rendering loading template:", error);
			return false;
		}
	}

	/**
	 * Render icon and/or text content using Django template
	 * @param {Element|string} container - Container element or selector
	 * @param {Object} options - Options (icon, text, color, icon_position, spacing)
	 * @returns {Promise<boolean>} Success status
	 */
	async renderContent(container, options = {}) {
		const el =
			typeof container === "string"
				? document.querySelector(container)
				: container;
		if (!el) {
			console.warn("Container not found for renderContent:", container);
			return false;
		}

		try {
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template: "users/components/content.html",
					context: options,
				},
				null,
				true,
			); // true = send as JSON

			if (response.html) {
				el.innerHTML = response.html;
				return true;
			}
			return false;
		} catch (error) {
			console.error("Error rendering content template:", error);
			return false;
		}
	}

	/**
	 * Render table rows using Django template
	 * @param {Element|string} container - Container element or selector (tbody)
	 * @param {Array} rows - Array of row objects with cells
	 * @param {Object} options - Additional options (empty_message, colspan)
	 * @returns {Promise<boolean>} Success status
	 */
	async renderTable(container, rows, options = {}) {
		const el =
			typeof container === "string"
				? document.querySelector(container)
				: container;
		if (!el) {
			console.warn("Container not found for renderTable:", container);
			return false;
		}

		const {
			template = "users/components/table_rows.html",
			empty_message = "No items found",
			colspan,
			empty_colspan,
			...rest
		} = options;

		const context = {
			rows: rows,
			empty_message,
			empty_colspan: colspan || empty_colspan || 5,
			...rest,
		};

		try {
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template,
					context,
				},
				null,
				true,
			); // true = send as JSON

			if (response.html) {
				el.innerHTML = response.html;
				return true;
			}
			return false;
		} catch (error) {
			console.error("Error rendering table template:", error);
			return false;
		}
	}

	/**
	 * Render select options using Django template
	 * @param {Element|string} selectElement - Select element or selector
	 * @param {Array} choices - Array of [value, label] tuples or objects with value/label
	 * @param {string} currentValue - Currently selected value
	 * @returns {Promise<boolean>} Success status
	 */
	async renderSelectOptions(selectElement, choices, currentValue = null) {
		const el =
			typeof selectElement === "string"
				? document.querySelector(selectElement)
				: selectElement;
		if (!el) {
			console.warn(
				"Select element not found for renderSelectOptions:",
				selectElement,
			);
			return false;
		}

		// Normalize choices to object format
		const formattedChoices = choices.map((choice) => {
			if (Array.isArray(choice)) {
				// [value, label] tuple format
				return {
					value: choice[0],
					label: choice[1],
					selected: currentValue !== null && choice[0] === currentValue,
				};
			}
			// Already object format
			return {
				...choice,
				selected: currentValue !== null && choice.value === currentValue,
			};
		});

		try {
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template: "users/components/select_options.html",
					context: { choices: formattedChoices },
				},
				null,
				true,
			); // true = send as JSON

			if (response.html) {
				el.innerHTML = response.html;
				return true;
			}
			return false;
		} catch (error) {
			console.error("Error rendering select options template:", error);
			return false;
		}
	}

	/**
	 * Render pagination using Django template
	 * @param {Element|string} container - Container element or selector
	 * @param {Object} pagination - Pagination data
	 * @returns {Promise<boolean>} Success status
	 */
	async renderPagination(container, pagination) {
		const el =
			typeof container === "string"
				? document.querySelector(container)
				: container;
		if (!el) {
			console.warn("Container not found for renderPagination:", container);
			return false;
		}

		// Don't show pagination if only 1 page or no pages
		if (!pagination || pagination.num_pages <= 1) {
			el.innerHTML = "";
			return true;
		}

		// Normalize pagination data for template
		const startPage = Math.max(1, pagination.number - 2);
		const endPage = Math.min(pagination.num_pages, pagination.number + 2);

		const pages = [];
		for (let i = startPage; i <= endPage; i++) {
			pages.push({
				number: i,
				is_current: i === pagination.number,
			});
		}

		const context = {
			show: true,
			has_previous: pagination.has_previous,
			previous_page: pagination.number - 1,
			has_next: pagination.has_next,
			next_page: pagination.number + 1,
			pages: pages,
		};

		try {
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template: "users/components/pagination.html",
					context: context,
				},
				null,
				true,
			); // true = send as JSON

			if (response.html) {
				el.innerHTML = response.html;
				return true;
			}
			return false;
		} catch (error) {
			console.error("Error rendering pagination template:", error);
			return false;
		}
	}

	/**
	 * Render dropdown menu using Django template
	 * @param {Object} options - Dropdown configuration
	 * @returns {Promise<string|null>} HTML string or null on error
	 */
	async renderDropdown(options = {}) {
		const context = {
			button_icon: options.button_icon || "three-dots-vertical",
			button_class: options.button_class || "btn-sm btn-light",
			button_label: options.button_label || "Actions",
			items: options.items || [],
		};

		try {
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template: "users/components/dropdown_menu.html",
					context: context,
				},
				null,
				true,
			); // true = send as JSON

			if (response.html) {
				return response.html;
			}
			return null;
		} catch (error) {
			console.error("Error rendering dropdown template:", error);
			return null;
		}
	}
}

// Create global instance
window.DOMUtils = new DOMUtils();

// Also expose showAlert as global function for convenience
window.showAlert = window.DOMUtils.showAlert.bind(window.DOMUtils);

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
	module.exports = { DOMUtils };
}
