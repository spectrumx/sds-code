/**
 * DOM Utility Functions
 * Provides basic DOM manipulation utilities (show, hide, toggle)
 * 
 * NOTE: This class does NOT generate HTML from user data.
 * All HTML containing server data should be rendered server-side using Django templates.
 * 
 * See: gateway/sds_gateway/users/html_utils.py for server-side HTML generation
 * See: gateway/docs/SECURITY-IMPROVEMENTS.md for security rationale
 */
class DOMUtils {
	/**
	 * Show element using CSS classes
	 * @param {Element|string} element - Element or selector to show
	 * @param {string} displayClass - CSS display class to add (default: "display-block")
	 */
	show(element, displayClass = "display-block") {
		const el =
			typeof element === "string" ? document.querySelector(element) : element;
		if (!el) {
			console.warn(`Element not found for show():`, element);
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
			console.warn(`Element not found for hide():`, element);
			return;
		}

		el.classList.remove(displayClass);
		el.classList.add("display-none");
	}

	/**
	 * Toggle element visibility
	 * @param {Element|string} element - Element or selector to toggle
	 * @param {string} displayClass - CSS display class (default: "display-block")
	 */
	toggle(element, displayClass = "display-block") {
		const el =
			typeof element === "string" ? document.querySelector(element) : element;
		if (!el) {
			console.warn(`Element not found for toggle():`, element);
			return;
		}

		if (
			el.classList.contains("display-none") ||
			el.classList.contains("d-none")
		) {
			this.show(el, displayClass);
		} else {
			this.hide(el, displayClass);
		}
	}

	/**
	 * Add CSS class to element
	 * @param {Element|string} element - Element or selector
	 * @param {string} className - Class name to add
	 */
	addClass(element, className) {
		const el =
			typeof element === "string" ? document.querySelector(element) : element;
		if (!el) {
			console.warn(`Element not found for addClass():`, element);
			return;
		}
		el.classList.add(className);
	}

	/**
	 * Remove CSS class from element
	 * @param {Element|string} element - Element or selector
	 * @param {string} className - Class name to remove
	 */
	removeClass(element, className) {
		const el =
			typeof element === "string" ? document.querySelector(element) : element;
		if (!el) {
			console.warn(`Element not found for removeClass():`, element);
			return;
		}
		el.classList.remove(className);
	}

	/**
	 * Toggle CSS class on element
	 * @param {Element|string} element - Element or selector
	 * @param {string} className - Class name to toggle
	 */
	toggleClass(element, className) {
		const el =
			typeof element === "string" ? document.querySelector(element) : element;
		if (!el) {
			console.warn(`Element not found for toggleClass():`, element);
			return;
		}
		el.classList.toggle(className);
	}

	/**
	 * Check if element has CSS class
	 * @param {Element|string} element - Element or selector
	 * @param {string} className - Class name to check
	 * @returns {boolean}
	 */
	hasClass(element, className) {
		const el =
			typeof element === "string" ? document.querySelector(element) : element;
		if (!el) {
			console.warn(`Element not found for hasClass():`, element);
			return false;
		}
		return el.classList.contains(className);
	}

	/**
	 * Enable/disable element
	 * @param {Element|string} element - Element or selector
	 * @param {boolean} enabled - Whether element should be enabled
	 */
	setEnabled(element, enabled) {
		const el =
			typeof element === "string" ? document.querySelector(element) : element;
		if (!el) {
			console.warn(`Element not found for setEnabled():`, element);
			return;
		}
		el.disabled = !enabled;
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
		toastBody.textContent = message; // textContent auto-escapes!

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
}

// Create global instance
window.DOMUtils = new DOMUtils();

// Also expose showAlert as global function for convenience
window.showAlert = window.DOMUtils.showAlert.bind(window.DOMUtils);

// Export for ES6 modules
export { DOMUtils };

