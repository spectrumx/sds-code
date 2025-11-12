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
		if (bytes === 0) return "0 Bytes";
		const k = 1024;
		const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
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
	 * Show global toast notification
	 * @param {string} message - Toast message
	 * @param {string} type - Toast type (success, error, warning, info)
	 */
	showAlert(message, type = "success") {
		const toastContainer = document.getElementById("toast-container");
		if (!toastContainer) {
			console.warn("Toast container not found");
			return;
		}

		const toastId = `toast-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
		const bgClass =
			type === "success"
				? "bg-success text-white"
				: type === "error"
					? "bg-danger text-white"
					: type === "warning"
						? "bg-warning text-dark"
						: "bg-info text-white";

		// Create toast element
		const toastDiv = document.createElement("div");
		toastDiv.id = toastId;
		toastDiv.className = `toast align-items-center ${bgClass}`;
		toastDiv.setAttribute("role", "alert");
		toastDiv.setAttribute("aria-live", "assertive");
		toastDiv.setAttribute("aria-atomic", "true");
		toastDiv.setAttribute("data-bs-delay", "3500");

		// Create toast content
		const toastContent = document.createElement("div");
		toastContent.className = "d-flex";

		const toastBody = document.createElement("div");
		toastBody.className = "toast-body";
		toastBody.textContent = message;

		const closeButton = document.createElement("button");
		closeButton.type = "button";
		closeButton.className = "btn-close btn-close-white me-2 m-auto";
		closeButton.setAttribute("data-bs-dismiss", "toast");
		closeButton.setAttribute("aria-label", "Close");

		toastContent.appendChild(toastBody);
		toastContent.appendChild(closeButton);
		toastDiv.appendChild(toastContent);
		toastContainer.appendChild(toastDiv);

		// Show toast
		if (!window.bootstrap || !bootstrap.Toast) {
			console.error("Bootstrap not available");
			return;
		}

		const toast = new bootstrap.Toast(toastDiv);
		toast.show();
		toastDiv.addEventListener("hidden.bs.toast", () => toastDiv.remove());
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
			// Fallback based on format
			if (context.format === "table") {
				el.innerHTML = `<tr><td colspan="${context.colspan || 5}" class="text-center text-danger">${message}</td></tr>`;
			} else if (context.format === "alert") {
				el.innerHTML = `<div class="alert alert-danger">${message}</div>`;
			} else if (context.format === "list") {
				el.innerHTML = `<ul class="mb-0 list-unstyled"><li class="text-danger">${message}</li></ul>`;
			} else {
				el.innerHTML = `<span class="text-danger">${message}</span>`;
			}
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
			// Fallback
			const sizeClass = context.size === "sm" ? "spinner-border-sm" : "";
			el.innerHTML = `<span class="spinner-border ${sizeClass} text-${context.color}" role="status"><span class="visually-hidden">${text}</span></span> ${text}`;
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
			// Fallback
			const iconHtml = options.icon
				? `<i class="bi bi-${options.icon}${options.color ? ` text-${options.color}` : ""}"></i>`
				: "";
			const textHtml = options.text || "";
			const spacing =
				options.spacing !== false && iconHtml && textHtml ? " " : "";
			el.innerHTML =
				options.icon_position === "right"
					? `${textHtml}${spacing}${iconHtml}`
					: `${iconHtml}${spacing}${textHtml}`;
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

		const context = {
			rows: rows,
			empty_message: options.empty_message || "No items found",
			empty_colspan: options.colspan || options.empty_colspan || 5,
			...options,
		};

		try {
			const response = await window.APIClient.post(
				"/users/render-html/",
				{
					template: "users/components/table_rows.html",
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
			console.error("Error rendering table template:", error);
			// Fallback
			el.innerHTML = `<tr><td colspan="${context.empty_colspan}" class="text-center text-muted">${context.empty_message}</td></tr>`;
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
			// Fallback
			el.innerHTML = formattedChoices
				.map(
					(choice) =>
						`<option value="${choice.value}"${choice.selected ? " selected" : ""}>${choice.label}</option>`,
				)
				.join("");
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
			// Fallback: show nothing rather than broken pagination
			el.innerHTML = "";
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
			// Fallback to basic dropdown
			const items = context.items
				.map((item) => {
					const icon = item.icon
						? `<i class="bi bi-${item.icon} me-1"></i>`
						: "";
					return `<li><button type="button" class="dropdown-item">${icon}${item.label}</button></li>`;
				})
				.join("");
			return `<div class="dropdown"><button class="btn ${context.button_class} dropdown-toggle" type="button" data-bs-toggle="dropdown"><i class="bi bi-${context.button_icon}"></i></button><ul class="dropdown-menu">${items}</ul></div>`;
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
