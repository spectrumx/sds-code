/**
 * Base class for UI managers: shared services, toast helpers, lifecycle hooks.
 */
BaseManager = class {
    constructor() {
        this.showMessage = window.DOMUtils?.showMessage
        this.getCSRFToken = window.APIClient?.getCSRFToken
        this.logError = window.DOMUtils?.logError
        this.getUserFriendlyErrorMessage =
            window.DOMUtils?.getUserFriendlyErrorMessage

        this.successMessage = (message) =>
            this.showMessage?.(message, {
                variant: "success",
                placement: "toast",
                presentation: "toast",
            })

        this.errorMessage = (message) =>
            this.showMessage?.(message, {
                variant: "danger",
                placement: "toast",
                presentation: "toast",
            })

        this.warningMessage = (message) =>
            this.showMessage?.(message, {
                variant: "warning",
                placement: "toast",
                presentation: "toast",
            })

        this.infoMessage = (message) =>
            this.showMessage?.(message, {
                variant: "info",
                placement: "toast",
                presentation: "toast",
            })

        if (!this.checkBrowserSupport()) {
            void window.DOMUtils?.showMessage(
                "Your browser doesn't support required features. Please use a modern browser.",
                {
                    variant: "danger",
                    placement: "toast",
                    log: true,
                    error: new Error("Browser compatibility check failed"),
                    triggeredBy: document.body,
                },
            )
            return
        }
    }

    /**
     * Override in subclasses that require feature detection (e.g. uploads).
     * @returns {boolean}
     */
    checkBrowserSupport() {
        return true
    }

    /**
     * Normalize semantic type and show a toast via {@link DOMUtils.showMessage}.
     * @param {string} message
     * @param {string} [type]
     */
    showToast(message, type = "success") {
        const variant =
            type === "danger" || type === "error"
                ? "danger"
                : type === "warning" || type === "success" || type === "info"
                  ? type
                  : "info"
        if (this.showMessage) {
            void this.showMessage(message, {
                variant,
                placement: "toast",
                presentation: "toast",
            })
        } else if (window.DOMUtils?.showMessage) {
            void window.DOMUtils.showMessage(message, {
                variant,
                placement: "toast",
                presentation: "toast",
            })
        } else {
            console.error("DOMUtils.showMessage not available")
        }
    }

    /**
     * Danger toast with optional error logging (uses {@link DOMUtils.showMessage} options).
     * @param {string} message
     * @param {Element|string|null} [contextOrTrigger] - element for log context
     * @param {Error|null} [error]
     */
    showErrorToast(message, contextOrTrigger = null, error = null) {
        const triggeredBy =
            contextOrTrigger instanceof Element ? contextOrTrigger : null
        const opts = {
            variant: "danger",
            placement: "toast",
            presentation: "toast",
            log: Boolean(error),
            error: error || null,
            triggeredBy,
        }
        if (this.showMessage) {
            void this.showMessage(message, opts)
        } else if (window.DOMUtils?.showMessage) {
            void window.DOMUtils.showMessage(message, opts)
        }
    }

    /**
     * Server-rendered message inside a container ({@link DOMUtils.showMessage} replace).
     * @param {string} message
     * @param {Element|string|null} target
     * @param {object} [opts]
     * @param {string} [opts.variant='danger']
     * @param {string} [opts.presentation='alert']
     * @param {object} [opts.templateContext]
     * @returns {Promise<boolean|void>}
     */
    showMessageInTarget(message, target, opts = {}) {
        const {
            variant = "danger",
            presentation = "alert",
            templateContext = {},
        } = opts
        const el =
            typeof target === "string" ? document.querySelector(target) : target
        if (!el) {
            return Promise.resolve(false)
        }
        const alertType =
            variant === "error" || variant === "danger"
                ? "danger"
                : variant === "success" ||
                    variant === "warning" ||
                    variant === "info"
                  ? variant
                  : "danger"
        const show = this.showMessage || window.DOMUtils?.showMessage
        if (!show) {
            return Promise.resolve(false)
        }
        const fn =
            show === window.DOMUtils?.showMessage
                ? window.DOMUtils.showMessage.bind(window.DOMUtils)
                : show.bind(this)
        return fn(message, {
            variant: alertType === "danger" ? "danger" : variant,
            placement: "replace",
            target: el,
            presentation,
            templateContext: {
                ...(presentation === "alert" ? { alert_type: alertType } : {}),
                ...templateContext,
            },
        })
    }

    initialize() {
        this.initializeEventListeners()
    }

    initializeEventListeners() {
        // Subclasses override
    }

    addEventListener(element, event, handler) {
        element.addEventListener(event, handler)
    }

    removeEventListener(element, event, handler) {
        element.removeEventListener(event, handler)
    }

    cleanup() {
        // Subclasses override
    }
}

if (typeof window !== "undefined") {
    window.BaseManager = BaseManager
}
if (typeof module !== "undefined" && module.exports) {
    module.exports = { BaseManager }
}
