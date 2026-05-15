BaseManager = class {
	constructor() {
		// Check browser compatibility before proceeding
		if (!this.checkBrowserSupport()) {
			this.showMessage(
				"Your browser doesn't support required features. Please use a modern browser.",
				{
					variant: "danger",
					placement: "toast",
					log: true,
					error: new Error("Browser compatibility check failed"),
					triggeredBy: document.body,
				},
			);
			return;
		}

		// initialize method dependencies for easy use
		this.openModal = window.ModalManager?.showModalElement;
		this.closeModal = window.ModalManager?.hideModalElement;
		this.showMessage = window.DOMUtils?.showMessage;
		this.getCSRFToken = window.APIClient?.getCSRFToken;
		this.logError = window.DOMUtils?.logError;
		this.getUserFriendlyErrorMessage =
			window.DOMUtils?.getUserFriendlyErrorMessage;
	}

	initialize() {
		this.initializeEventListeners();
	}

	initializeEventListeners() {
		// add event listeners here
	}

	addEventListener(element, event, handler) {
		element.addEventListener(event, handler);
	}

	removeEventListener(element, event, handler) {
		element.removeEventListener(event, handler);
	}

	cleanup() {
		// add cleanup code here
	}
};
