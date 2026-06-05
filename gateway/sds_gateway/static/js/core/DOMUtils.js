/**
 * DOM Utility Functions
 * Provides basic DOM manipulation utilities
 *
 * NOTE: This class does NOT generate HTML from user data.
 * All HTML containing server data should be rendered server-side using Django templates.
 *
 * Available methods:
 * - formatFileSize(bytes) - Format file size
 * - toggleHidden(element, hidden) - Toggle Bootstrap d-none on an element
 * - show(element, displayClass) - Show element with CSS class
 * - hide(element, displayClass) - Hide element with CSS class
 * - showMessage(message, opts) - User-visible messages (toast / inline) via Django template
 * - showVisualizationPanel(message, detailLine, opts) - Spectrogram/waterfall status panel
 * - hideVisualizationPanel(target) - Hide visualization status/error panel
 * - logError(error, triggeredBy) - Log error to console
 * - getUserFriendlyErrorMessage(error) - Get user-friendly error message
 * - initIconDropdowns(root) - Initialize icon dropdowns
 * - renderContent(container, options) - Render content using Django template
 * - renderTable(container, rows, options) - Render table rows using Django template
 * - renderSelectOptions(selectElement, choices, currentValue) - Render select options using Django template
 * - renderPagination(container, pagination) - Render pagination using Django template
 * - renderDropdown(options) - Render dropdown menu using Django template
 */
class DOMUtils {
    /**
     * Format file size
     * @param {number} bytes - File size in bytes
     * @returns {string} Formatted file size
     */
    formatFileSize(bytes) {
        const n = Number(bytes)
        if (!Number.isFinite(n) || n < 0) return "0 bytes"
        if (n === 0) return "0 bytes"
        const units = ["bytes", "KB", "MB", "GB"]
        let i = 0
        let v = n
        while (v >= 1024 && i < units.length - 1) {
            v /= 1024
            i++
        }
        return `${i === 0 ? v : v.toFixed(2)} ${units[i]}`
    }

    /**
     * Show or hide an element via Bootstrap d-none.
     * @param {Element|string|null} element
     * @param {boolean} hidden
     */
    toggleHidden(element, hidden) {
        const el =
            typeof element === "string"
                ? document.querySelector(element)
                : element
        if (!el) return
        el.classList.toggle("d-none", Boolean(hidden))
    }

    /**
     * Indeterminate progress bar via loading.html (format progress).
     * @param {Element|string} container
     * @param {string} [text]
     * @returns {Promise<boolean>}
     */
    async renderProgress(container, text = "Working…") {
        return this.renderLoading(container, text, { format: "progress" })
    }

    /**
     * Show element using CSS classes
     * @param {Element|string} element - Element or selector to show
     * @param {string} displayClass - CSS display class to add (default: "display-block")
     */
    show(element, displayClass = "display-block") {
        const el =
            typeof element === "string"
                ? document.querySelector(element)
                : element
        if (!el) {
            console.warn("Element not found for show():", element)
            return
        }

        el.classList.remove("display-none", "d-none")
        el.classList.add(displayClass)
    }

    /**
     * Hide element using CSS classes
     * @param {Element|string} element - Element or selector to hide
     * @param {string} displayClass - CSS display class to remove (default: "display-block")
     */
    hide(element, displayClass = "display-block") {
        const el =
            typeof element === "string"
                ? document.querySelector(element)
                : element
        if (!el) {
            console.warn("Element not found for hide():", element)
            return
        }

        el.classList.remove(displayClass)
        el.classList.add("display-none")
    }

    /**
     * Remove alert elements inside a container (e.g. modal body).
     * @param {Element|string} target
     */
    clearAlerts(target) {
        const el =
            typeof target === "string" ? document.querySelector(target) : target
        if (!el) return
        for (const alert of el.querySelectorAll(".alert")) {
            alert.remove()
        }
    }

    formatDate(dateString) {
        if (!dateString) return "<div>-</div>"

        let date
        if (typeof dateString === "string") {
            date = new Date(dateString)
        } else {
            date = new Date(dateString)
        }

        if (!date || Number.isNaN(date.getTime())) {
            return "<div>-</div>"
        }

        const month = String(date.getMonth() + 1).padStart(2, "0")
        const day = String(date.getDate()).padStart(2, "0")
        const year = date.getFullYear()
        const hours = date.getHours()
        const minutes = String(date.getMinutes()).padStart(2, "0")
        const seconds = String(date.getSeconds()).padStart(2, "0")
        const ampm = hours >= 12 ? "PM" : "AM"
        const displayHours = hours % 12 || 12

        return `<div>${month}/${day}/${year}</div><small class="text-muted">${displayHours}:${minutes}:${seconds} ${ampm}</small>`
    }

    formatDateForModal(dateString) {
        if (!dateString || dateString === "None") {
            return "N/A"
        }

        try {
            const date = new Date(dateString)
            if (Number.isNaN(date.getTime())) {
                return "N/A"
            }

            const year = date.getFullYear()
            const month = String(date.getMonth() + 1).padStart(2, "0")
            const day = String(date.getDate()).padStart(2, "0")
            const dateFormatted = `${year}-${month}-${day}`

            const hours = String(date.getHours()).padStart(2, "0")
            const minutes = String(date.getMinutes()).padStart(2, "0")
            const seconds = String(date.getSeconds()).padStart(2, "0")
            const timezone = date
                .toLocaleTimeString("en-US", { timeZoneName: "short" })
                .split(" ")[1]
            const timeFormatted = `${hours}:${minutes}:${seconds} ${timezone}`

            return `<span class="bg-transparent pe-2">${dateFormatted}</span><span class="text-muted bg-transparent">${timeFormatted}</span>`
        } catch (error) {
            console.error("Error formatting capture date:", error)
            return "N/A"
        }
    }

    formatDateSimple(dateString) {
        try {
            const date = new Date(dateString)
            return date.toString() !== "Invalid Date"
                ? date.toLocaleDateString("en-US", {
                      month: "2-digit",
                      day: "2-digit",
                      year: "numeric",
                  })
                : ""
        } catch (_e) {
            return ""
        }
    }

    /**
     * Unified user-visible messaging (server-rendered HTML).
     * @param {string} message
     * @param {object} [opts]
     * @param {'success'|'error'|'warning'|'info'|'danger'} [opts.variant='info'] - danger maps like Bootstrap
     * @param {'toast'|'replace'|'append'} [opts.placement='toast']
     * @param {Element|string|null} [opts.target] - for replace/append (selector or element)
     * @param {'toast'|'inline'|'alert'|'list'|'table'|'visualization_panel'} [opts.presentation='toast'] - must match template branches
     * @param {object} [opts.templateContext] - extra keys passed to Django (error_list, colspan, icon, …)
     * @param {Error|null} [opts.error] - error object to log
     * @param {Element|string|null} [opts.triggeredBy] - element to log error for
     * @param {boolean} [opts.log] - log error to console
     * @param {boolean} [opts.autoRemove] - for ephemeral modal alerts (timeout ms in opts.autoRemoveMs)
     * @param {number} [opts.autoRemoveMs] - timeout ms for auto removal of ephemeral modal alerts
     */
    async showMessage(message, opts = {}) {
        try {
            const {
                variant = "info",
                placement = "toast",
                target = null,
                presentation = placement === "toast" ? "toast" : "alert",
                templateContext = {},
                error = null,
                triggeredBy = null,
                log = false,
                autoRemove = false,
                autoRemoveMs = 4000,
            } = opts

            const type =
                variant === "danger" || variant === "error" ? "error" : variant

            if (log && error) {
                this.logError(error, triggeredBy)
            }

            const context = {
                message: message ?? "",
                type,
                presentation, // toast | inline | alert | list | table
                ...templateContext,
            }

            const response = await window.APIClient.post(
                "/users/render-html/",
                {
                    template: "users/components/message.html",
                    context,
                },
                null,
                true,
            )

            if (!response?.html) {
                console.error("showMessage: no HTML from render-html")
                return false
            }

            const wrap = document.createElement("div")
            wrap.innerHTML = response.html
            const node = wrap.firstElementChild
            if (!node) {
                console.error("showMessage: failed to parse message HTML")
                return false
            }

            if (placement === "toast") {
                const toastHost = document.getElementById("toast-container")
                const BS = window.bootstrap
                if (!toastHost || !BS?.Toast) {
                    console.error(
                        "showMessage: toast container or Bootstrap Toast not available",
                    )
                    return false
                }
                node.id =
                    node.id ||
                    `toast-${Date.now()}-${Math.random().toString(16).slice(2)}`
                toastHost.appendChild(node)
                const t = new BS.Toast(node)
                t.show()
                node.addEventListener("hidden.bs.toast", () => node.remove())
                return true
            }

            const el =
                typeof target === "string"
                    ? document.querySelector(target)
                    : target
            if (!el) {
                console.warn("showMessage: target not found:", target)
                return false
            }

            if (placement === "append") {
                el.insertBefore(node, el.firstChild)
            } else if (placement === "replace") {
                el.innerHTML = ""
                el.appendChild(node)
            }

            if (autoRemove && presentation === "alert") {
                setTimeout(() => node.remove(), autoRemoveMs)
            }
            return true
        } catch (err) {
            console.error("showMessage failed:", err)
            return false
        }
    }

    /**
     * Server-rendered message in #visualizationErrorDisplay (or custom target).
     * @param {string} message
     * @param {string|null} [detailLine]
     * @param {object} [opts]
     * @param {Element|string} [opts.target='#visualizationErrorDisplay']
     * @param {'success'|'error'|'warning'|'info'|'danger'} [opts.variant='info']
     * @param {() => void} [opts.beforeShow]
     */
    async showVisualizationPanel(message, detailLine = null, opts = {}) {
        const {
            target = "#visualizationErrorDisplay",
            variant = "info",
            beforeShow,
        } = opts

        const el =
            typeof target === "string" ? document.querySelector(target) : target
        if (!el) {
            console.warn("showVisualizationPanel: target not found:", target)
            return false
        }

        beforeShow?.()

        const ok = await this.showMessage(message ?? "", {
            variant,
            placement: "replace",
            target: el,
            presentation: "visualization_panel",
            templateContext: { detail_line: detailLine || "" },
        })

        if (ok) {
            el.classList.remove("d-none")
        }
        return ok
    }

    /**
     * @param {Element|string} [target='#visualizationErrorDisplay']
     */
    hideVisualizationPanel(target = "#visualizationErrorDisplay") {
        const el =
            typeof target === "string" ? document.querySelector(target) : target
        if (el) {
            el.classList.add("d-none")
        }
    }

    logError(error, triggeredBy = null) {
        console.error(
            triggeredBy ? triggeredBy : "",
            this.getUserFriendlyErrorMessage(error),
        )
    }

    getUserFriendlyErrorMessage(error, context = "") {
        if (!error) return "An unexpected error occurred"

        if (
            error.name === "TypeError" &&
            error.message.includes("Cannot read")
        ) {
            return "Configuration error: Some components are not properly loaded"
        }
        if (error.name === "TypeError" && error.message.includes("JSON")) {
            return "Invalid response format: Please try again or contact support"
        }
        if (error.name === "ReferenceError") {
            return "Component error: Required functionality is not available"
        }
        if (error.name === "NetworkError" || error.message.includes("fetch")) {
            return "Network error: Please check your connection and try again"
        }
        if (
            error.message.includes("403") ||
            error.message.includes("Forbidden")
        ) {
            return "Access denied: You don't have permission to perform this action"
        }
        if (
            error.message.includes("404") ||
            error.message.includes("Not Found")
        ) {
            const fileContext =
                context === "upload-handler" ||
                context === "file-preview" ||
                String(context).includes("upload")
            return fileContext
                ? "Resource not found: The requested file or directory may have been moved or deleted"
                : "Resource not found: The requested asset may have been moved or deleted"
        }
        if (
            error.message.includes("500") ||
            error.message.includes("Internal Server Error")
        ) {
            return "Server error: Please try again later or contact support"
        }

        return error.message || "An unexpected error occurred"
    }

    /**
     * Bootstrap icon action menus: dispose/recreate instances; global listeners once.
     * @param {ParentNode} [root]
     */
    initIconDropdowns(root = document) {
        if (typeof bootstrap === "undefined" || !bootstrap.Dropdown) {
            return
        }

        if (!this._iconDropdownShowDelegated) {
            this._iconDropdownShowDelegated = true
            document.addEventListener("show.bs.dropdown", (e) => {
                const toggle = e.target?.closest?.(".btn-icon-dropdown")
                if (!toggle) return
                const dropdownMenu = toggle.nextElementSibling
                if (dropdownMenu?.classList.contains("dropdown-menu")) {
                    document.body.appendChild(dropdownMenu)
                }
            })
        }

        if (!this._dropdownStopRowClickBound) {
            this._dropdownStopRowClickBound = true
            document.addEventListener("click", (event) => {
                if (
                    event.target.closest(".dropdown") ||
                    event.target.closest(".btn-icon-dropdown") ||
                    event.target.closest(".dropdown-toggle") ||
                    event.target.closest(".dropdown-menu")
                ) {
                    event.stopPropagation()
                }
            })
        }

        for (const toggle of root.querySelectorAll(".btn-icon-dropdown")) {
            const existing = bootstrap.Dropdown.getInstance(toggle)
            if (existing) {
                existing.dispose()
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
            })
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
                : container
        if (!el) {
            console.warn("Container not found for renderLoading:", container)
            return false
        }

        const context = {
            text: text,
            format: options.format || "spinner",
            size: options.size || "md",
            color: options.color || "primary",
            ...options,
        }

        try {
            const response = await window.APIClient.post(
                "/users/render-html/",
                {
                    template: "users/components/loading.html",
                    context: context,
                },
                null,
                true,
            ) // true = send as JSON

            if (response.html) {
                el.innerHTML = response.html
                return true
            }
            return false
        } catch (error) {
            console.error("Error rendering loading template:", error)
            return false
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
                : container
        if (!el) {
            console.warn("Container not found for renderContent:", container)
            return false
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
            ) // true = send as JSON

            if (response.html) {
                el.innerHTML = response.html
                return true
            }
            return false
        } catch (error) {
            console.error("Error rendering content template:", error)
            return false
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
                : container
        if (!el) {
            console.warn("Container not found for renderTable:", container)
            return false
        }

        const {
            template = "users/components/table_rows.html",
            empty_message = "No items found",
            colspan,
            empty_colspan,
            ...rest
        } = options

        const context = {
            rows: rows,
            empty_message,
            empty_colspan: colspan || empty_colspan || 5,
            ...rest,
        }

        try {
            const response = await window.APIClient.post(
                "/users/render-html/",
                {
                    template,
                    context,
                },
                null,
                true,
            ) // true = send as JSON

            if (response.html) {
                el.innerHTML = response.html
                return true
            }
            return false
        } catch (error) {
            console.error("Error rendering table template:", error)
            return false
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
                : selectElement
        if (!el) {
            console.warn(
                "Select element not found for renderSelectOptions:",
                selectElement,
            )
            return false
        }

        // Normalize choices to object format
        const formattedChoices = choices.map((choice) => {
            if (Array.isArray(choice)) {
                // [value, label] tuple format
                return {
                    value: choice[0],
                    label: choice[1],
                    selected:
                        currentValue !== null && choice[0] === currentValue,
                }
            }
            // Already object format
            return {
                ...choice,
                selected:
                    currentValue !== null && choice.value === currentValue,
            }
        })

        try {
            const response = await window.APIClient.post(
                "/users/render-html/",
                {
                    template: "users/components/select_options.html",
                    context: { choices: formattedChoices },
                },
                null,
                true,
            ) // true = send as JSON

            if (response.html) {
                el.innerHTML = response.html
                return true
            }
            return false
        } catch (error) {
            console.error("Error rendering select options template:", error)
            return false
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
                : container
        if (!el) {
            console.warn("Container not found for renderPagination:", container)
            return false
        }

        // Don't show pagination if only 1 page or no pages
        if (!pagination || pagination.num_pages <= 1) {
            el.innerHTML = ""
            return true
        }

        // Normalize pagination data for template
        const startPage = Math.max(1, pagination.number - 2)
        const endPage = Math.min(pagination.num_pages, pagination.number + 2)

        const pages = []
        for (let i = startPage; i <= endPage; i++) {
            pages.push({
                number: i,
                is_current: i === pagination.number,
            })
        }

        const context = {
            show: true,
            has_previous: pagination.has_previous,
            previous_page: pagination.number - 1,
            has_next: pagination.has_next,
            next_page: pagination.number + 1,
            pages: pages,
        }

        try {
            const response = await window.APIClient.post(
                "/users/render-html/",
                {
                    template: "users/components/pagination.html",
                    context: context,
                },
                null,
                true,
            ) // true = send as JSON

            if (response.html) {
                el.innerHTML = response.html
                return true
            }
            return false
        } catch (error) {
            console.error("Error rendering pagination template:", error)
            return false
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
        }

        try {
            const response = await window.APIClient.post(
                "/users/render-html/",
                {
                    template: "users/components/dropdown_menu.html",
                    context: context,
                },
                null,
                true,
            ) // true = send as JSON

            if (response.html) {
                return response.html
            }
            return null
        } catch (error) {
            console.error("Error rendering dropdown template:", error)
            return null
        }
    }
}

// Create global instance
window.DOMUtils = new DOMUtils()

window.showMessage = window.DOMUtils.showMessage.bind(window.DOMUtils)

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
    module.exports = { DOMUtils }
}
