/**
 * Centralized HTML Injection Manager
 * Handles safe DOM manipulation with XSS protection
 */
class HTMLInjectionManager {
	/**
	 * Escape HTML to prevent XSS attacks
	 * @param {string} text - Text to escape
	 * @returns {string} Escaped HTML
	 */
	static escapeHtml(text) {
		if (!text) return "";
		const div = document.createElement("div");
		div.textContent = text;
		return div.innerHTML;
	}

	/**
	 * Safely inject HTML into a container
	 * @param {Element|string} container - Container element or selector
	 * @param {string} htmlString - HTML string to inject
	 * @param {Object} options - Injection options
	 * @param {boolean} options.escape - Whether to escape HTML (default: true)
	 * @param {string} options.method - Injection method: 'innerHTML', 'append', 'prepend' (default: 'innerHTML')
	 */
	static injectHTML(container, htmlString, options = {}) {
		const { escapeHtml = true, method = "innerHTML" } = options;

		const element =
			typeof container === "string"
				? document.querySelector(container)
				: container;

		if (!element) {
			console.error("Container element not found");
			return;
		}

		const safeHtml = escapeHtml
			? HTMLInjectionManager.escapeHtml(htmlString)
			: htmlString;

		switch (method) {
			case "innerHTML":
				element.innerHTML = safeHtml;
				break;
			case "append":
				element.insertAdjacentHTML("beforeend", safeHtml);
				break;
			case "prepend":
				element.insertAdjacentHTML("afterbegin", safeHtml);
				break;
			default:
				console.error(`Unknown injection method: ${method}`);
		}
	}

	/**
	 * Create a table row with safe data
	 * @param {Object} data - Row data
	 * @param {string} template - HTML template with placeholders
	 * @param {Object} options - Options for data processing
	 * @returns {string} Safe HTML string
	 */
	static createTableRow(data, template, options = {}) {
		const { escapeHtml = true, dateFormat = "en-US" } = options;

		// Process data for safe injection
		const processedData = {};
		for (const [key, value] of Object.entries(data)) {
			if (value === null || value === undefined) {
				processedData[key] = "-";
			} else if (value instanceof Date) {
				processedData[key] = value.toLocaleDateString(dateFormat, {
					month: "2-digit",
					day: "2-digit",
					year: "numeric",
				});
			} else if (typeof value === "string" && escapeHtml) {
				processedData[key] = HTMLInjectionManager.escapeHtml(value);
			} else {
				processedData[key] = value;
			}
		}

		// Replace placeholders in template
		let html = template;
		for (const [key, value] of Object.entries(processedData)) {
			const placeholder = new RegExp(`{{${key}}}`, "g");
			html = html.replace(placeholder, value);
		}

		return html;
	}

	/**
	 * Create modal content with safe data
	 * @param {Object} data - Modal data
	 * @param {string} template - HTML template
	 * @param {Object} options - Options for data processing
	 * @returns {string} Safe HTML string
	 */
	static createModalContent(data, template, options = {}) {
		return HTMLInjectionManager.createTableRow(data, template, options);
	}

	/**
	 * Create user chip HTML
	 * @param {Object} user - User data
	 * @param {Object} options - Options
	 * @returns {string} Safe HTML string
	 */
	static createUserChip(user, options = {}) {
		const {
			showPermissionSelect = true,
			showRemoveButton = true,
			permissionLevels = ["viewer", "contributor", "co-owner"],
		} = options;

		const isGroup = user.email?.startsWith("group:");
		const displayName = HTMLInjectionManager.escapeHtml(
			isGroup ? user.name : user.name || user.email,
		);
		const displayEmail = isGroup
			? `Group • ${user.member_count || 0} members`
			: HTMLInjectionManager.escapeHtml(user.email);
		const icon = isGroup ? "bi-people-fill" : "bi-person-fill";

		let permissionSelect = "";
		if (showPermissionSelect) {
			const options = permissionLevels
				.map(
					(level) =>
						`<option value="${level}" ${user.permission_level === level ? "selected" : ""}>${level.charAt(0).toUpperCase() + level.slice(1)}</option>`,
				)
				.join("");
			permissionSelect = `
				<select class="form-select permission-select" data-user-email="${HTMLInjectionManager.escapeHtml(user.email)}">
					${options}
				</select>
			`;
		}

		const removeButton = showRemoveButton
			? '<span class="remove-chip">&times;</span>'
			: "";

		return `
			<div class="user-chip">
				<div class="user-info">
					<i class="bi ${icon}"></i>
					<div>
						<div class="user-name">${displayName}</div>
						<div class="user-email">${displayEmail}</div>
					</div>
				</div>
				${permissionSelect}
				${removeButton}
			</div>
		`;
	}

	/**
	 * Create error message HTML
	 * @param {Object|Array|string} errors - Error data
	 * @param {Object} options - Options
	 * @returns {string} Safe HTML string
	 */
	static createErrorMessage(errors, options = {}) {
		const { showFieldNames = true } = options;

		let errorHtml = '<ul class="mb-0 list-unstyled">';

		if (Array.isArray(errors)) {
			for (const error of errors) {
				errorHtml += `<li>${HTMLInjectionManager.escapeHtml(error)}</li>`;
			}
		} else if (typeof errors === "object" && errors !== null) {
			for (const [field, messages] of Object.entries(errors)) {
				const fieldName =
					showFieldNames && field !== "non_field_errors"
						? `<strong>${HTMLInjectionManager.escapeHtml(field)}:</strong> `
						: "";

				if (Array.isArray(messages)) {
					for (const message of messages) {
						errorHtml += `<li>${fieldName}${HTMLInjectionManager.escapeHtml(message)}</li>`;
					}
				} else if (typeof messages === "string") {
					errorHtml += `<li>${fieldName}${HTMLInjectionManager.escapeHtml(messages)}</li>`;
				}
			}
		} else if (typeof errors === "string") {
			errorHtml += `<li>${HTMLInjectionManager.escapeHtml(errors)}</li>`;
		}

		errorHtml += "</ul>";
		return errorHtml;
	}

	/**
	 * Create loading spinner HTML
	 * @param {string} text - Loading text
	 * @param {Object} options - Options
	 * @returns {string} HTML string
	 */
	static createLoadingSpinner(text = "Loading...", options = {}) {
		const { size = "sm", color = "" } = options;
		const sizeClass = size === "sm" ? "spinner-border-sm" : "";
		const colorClass = color ? `text-${color}` : "";

		return `<span class="spinner-border ${sizeClass} me-2 ${colorClass}" role="status" aria-hidden="true"></span>${text}`;
	}

	/**
	 * Create badge HTML
	 * @param {string} text - Badge text
	 * @param {string} type - Badge type (success, danger, warning, info, primary, secondary)
	 * @param {Object} options - Options
	 * @returns {string} HTML string
	 */
	static createBadge(text, type = "primary", options = {}) {
		const { size = "", customClass = "" } = options;
		const sizeClass = size ? `badge-${size}` : "";

		return `<span class="badge bg-${type} ${sizeClass} ${customClass}">${HTMLInjectionManager.escapeHtml(text)}</span>`;
	}

	/**
	 * Create button HTML
	 * @param {string} text - Button text
	 * @param {Object} options - Options
	 * @returns {string} HTML string
	 */
	static createButton(text, options = {}) {
		const {
			type = "button",
			variant = "primary",
			size = "",
			disabled = false,
			icon = "",
			loading = false,
			customClass = "",
			attributes = {},
		} = options;

		const sizeClass = size ? `btn-${size}` : "";
		const disabledAttr = disabled ? "disabled" : "";
		const iconHtml = icon ? `<i class="bi ${icon} me-1"></i>` : "";
		const loadingHtml = loading
			? HTMLInjectionManager.createLoadingSpinner()
			: "";

		const attrs = Object.entries(attributes)
			.map(
				([key, value]) => `${key}="${HTMLInjectionManager.escapeHtml(value)}"`,
			)
			.join(" ");

		return `
			<button type="${type}" class="btn btn-${variant} ${sizeClass} ${customClass}" ${disabledAttr} ${attrs}>
				${loadingHtml}${iconHtml}${HTMLInjectionManager.escapeHtml(text)}
			</button>
		`;
	}

	/**
	 * Create pagination HTML
	 * @param {Object} pagination - Pagination data
	 * @param {Object} options - Options
	 * @returns {string} HTML string
	 */
	static createPagination(pagination, options = {}) {
		const { showArrows = true, maxPages = 5 } = options;

		if (pagination.num_pages <= 1) return "";

		let html = '<ul class="pagination justify-content-center">';

		// Previous button
		if (pagination.has_previous && showArrows) {
			html += `
				<li class="page-item">
					<a class="page-link" href="#" data-page="${pagination.number - 1}" aria-label="Previous">
						<span aria-hidden="true">&laquo;</span>
					</a>
				</li>
			`;
		}

		// Page numbers
		const startPage = Math.max(1, pagination.number - Math.floor(maxPages / 2));
		const endPage = Math.min(pagination.num_pages, startPage + maxPages - 1);

		for (let i = startPage; i <= endPage; i++) {
			const activeClass = i === pagination.number ? "active" : "";
			html += `
				<li class="page-item ${activeClass}">
					<a class="page-link" href="#" data-page="${i}">${i}</a>
				</li>
			`;
		}

		// Next button
		if (pagination.has_next && showArrows) {
			html += `
				<li class="page-item">
					<a class="page-link" href="#" data-page="${pagination.number + 1}" aria-label="Next">
						<span aria-hidden="true">&raquo;</span>
					</a>
				</li>
			`;
		}

		html += "</ul>";
		return html;
	}

	/**
	 * Create notification HTML
	 * @param {string} message - Notification message
	 * @param {string} type - Notification type (success, danger, warning, info, primary, secondary)
	 * @param {Object} options - Options
	 * @returns {string} HTML string
	 */
	static createNotification(message, type = "info", options = {}) {
		const {
			dismissible = true,
			icon = true,
			containerId = "formErrors",
			customClass = "",
		} = options;

		const iconMap = {
			success: "bi-check-circle-fill",
			danger: "bi-exclamation-triangle-fill",
			warning: "bi-exclamation-triangle",
			info: "bi-info-circle-fill",
			primary: "bi-info-circle-fill",
			secondary: "bi-info-circle-fill",
		};

		const iconClass = icon ? iconMap[type] || iconMap.info : "";
		const dismissibleHtml = dismissible
			? '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>'
			: "";

		return `
			<div class="alert alert-${type} bg-${type}-subtle text-${type} mb-4 form-error-container ${customClass}" role="alert">
				<div class="d-flex align-items-center">
					${iconClass ? `<i class="bi ${iconClass} me-2"></i>` : ""}
					<div class="error-content">
						<ul class="mb-0 list-unstyled">
							<li>${HTMLInjectionManager.escapeHtml(message)}</li>
						</ul>
					</div>
				</div>
				${dismissibleHtml}
			</div>
		`;
	}

	/**
	 * Show notification in the DOM
	 * @param {string} message - Notification message
	 * @param {string} type - Notification type
	 * @param {Object} options - Options
	 */
	static showNotification(message, type = "info", options = {}) {
		const {
			containerId = "formErrors",
			autoHide = true,
			autoHideDelay = 5000,
			scrollTo = true,
			replace = true,
		} = options;

		const container = document.getElementById(containerId);
		if (!container) {
			console.error(
				`Notification container with ID '${containerId}' not found`,
			);
			return;
		}

		const notificationHtml = HTMLInjectionManager.createNotification(
			message,
			type,
			options,
		);

		if (replace) {
			// Replace existing content
			container.innerHTML = notificationHtml;
		} else {
			// Append to existing content
			container.insertAdjacentHTML("beforeend", notificationHtml);
		}

		// Show the notification
		container.classList.remove("d-none");

		// Scroll to notification if requested
		if (scrollTo) {
			container.scrollIntoView({ behavior: "smooth", block: "start" });
		}

		// Auto-hide if requested
		if (autoHide) {
			setTimeout(() => {
				HTMLInjectionManager.hideNotification(containerId);
			}, autoHideDelay);
		}
	}

	/**
	 * Hide notification
	 * @param {string} containerId - Container ID
	 */
	static hideNotification(containerId = "formErrors") {
		const container = document.getElementById(containerId);
		if (container) {
			container.classList.add("d-none");
		}
	}

	/**
	 * Clear all notifications
	 * @param {string} containerId - Container ID
	 */
	static clearNotifications(containerId = "formErrors") {
		const container = document.getElementById(containerId);
		if (container) {
			container.innerHTML = "";
			container.classList.add("d-none");
		}
	}

	/**
	 * Show toast notification (global showAlert function)
	 * @param {string} message - Toast message
	 * @param {string} type - Toast type (success, error, warning, info)
	 */
	static showAlert(message, type = "success") {
		const toastContainer = document.getElementById("toast-container");
		if (!toastContainer) return;

		const toastId = `toast-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
		const bgClass =
			type === "success"
				? "bg-success text-white"
				: type === "error"
					? "bg-danger text-white"
					: type === "warning"
						? "bg-warning text-dark"
						: "bg-info text-white";

		const toastHtml = `
			<div id="${toastId}" class="toast align-items-center ${bgClass}" role="alert" aria-live="assertive" aria-atomic="true" data-bs-delay="3500">
				<div class="d-flex">
					<div class="toast-body">${HTMLInjectionManager.escapeHtml(message)}</div>
					<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
				</div>
			</div>
		`;

		HTMLInjectionManager.injectHTML(toastContainer, toastHtml, {
			escape: false,
		});
		const toastElem = document.getElementById(toastId);
		const toast = new bootstrap.Toast(toastElem);
		toast.show();
		toastElem.addEventListener("hidden.bs.toast", () => toastElem.remove());
	}
}

// Make class available globally
window.HTMLInjectionManager = HTMLInjectionManager;

// Make showAlert available as a global function
window.showAlert = HTMLInjectionManager.showAlert;
