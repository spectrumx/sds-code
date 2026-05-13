/**
 * Base page controller: consistent lifecycle + cleanup.
 * Intended for per-page controllers (captures/files/datasets) to extend.
 */
class PageController {
	constructor() {
		this._bindings = [];
		this._initialized = false;
	}

	/**
	 * Bind an event listener and track it for cleanup.
	 * @param {EventTarget|null} target
	 * @param {string} eventName
	 * @param {Function} handler
	 * @param {boolean|AddEventListenerOptions} [options]
	 */
	bind(target, eventName, handler, options) {
		if (!target?.addEventListener) return;
		target.addEventListener(eventName, handler, options);
		this._bindings.push({ target, eventName, handler, options });
	}

	/**
	 * Remove all tracked listeners.
	 */
	unbindAll() {
		for (const b of this._bindings) {
			try {
				b.target?.removeEventListener?.(b.eventName, b.handler, b.options);
			} catch (_) {}
		}
		this._bindings = [];
	}

	/**
	 * Initialize controller once. Subclasses should override the individual hooks.
	 */
	init() {
		if (this._initialized) return;
		this._initialized = true;

		this.cacheElements();
		this.initializeComponents();
		this.initializeEventHandlers();
		this.initializeFromURL();
	}

	/**
	 * Shared list-page bootstrap (dataset list, capture list, etc.).
	 * @param {{ pageLifecycleConfig?: object, listRefreshConfig?: object }} opts
	 */
	static initListPage(opts = {}) {
		if (typeof window === "undefined") return;
		const { pageLifecycleConfig, listRefreshConfig } = opts;
		if (pageLifecycleConfig && window.PageLifecycleManager) {
			window.pageLifecycleManager = new window.PageLifecycleManager(
				pageLifecycleConfig,
			);
		}
		if (listRefreshConfig && window.ListRefreshManager) {
			window.listRefreshManager = new window.ListRefreshManager(
				listRefreshConfig,
			);
		}
	}

	// Hooks (override in subclasses)
	cacheElements() {}
	initializeComponents() {}
	initializeEventHandlers() {}
	initializeFromURL() {}

	/**
	 * Cleanup hook (override). Must call super.destroy().
	 */
	destroy() {
		this.unbindAll();
	}
}

if (typeof window !== "undefined") {
	window.PageController = PageController;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { PageController };
}

