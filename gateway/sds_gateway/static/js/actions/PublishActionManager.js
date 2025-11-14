/**
 * Publish Action Manager
 * Handles all publish-related actions
 */
class PublishActionManager {
	/**
	 * Initialize publish action manager
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		this.config = config || {};
		this.initializeEventListeners();
	}

	/**
	 * Initialize event listeners for all publish modals on the page
	 */
	initializeEventListeners() {
		// Find all publish modals
		const publishModals = document.querySelectorAll(
			'[id^="publish-dataset-modal-"]',
		);

		for (const modal of publishModals) {
			const datasetUuid = modal.getAttribute("data-dataset-uuid");
			if (!datasetUuid) continue;

			// Explicitly initialize Bootstrap modal to avoid auto-initialization issues
			if (window.bootstrap && !bootstrap.Modal.getInstance(modal)) {
				new bootstrap.Modal(modal, {
					backdrop: true,
					keyboard: true,
					focus: true,
				});
			}

			// Get elements for this specific modal
			const publishToggle = document.getElementById(
				`publish-dataset-toggle-${datasetUuid}`,
			);
			const visibilitySection = document.getElementById(
				`visibility-toggle-section-${datasetUuid}`,
			);
			const privateOption = document.getElementById(
				`private-option-${datasetUuid}`,
			);
			const publicOption = document.getElementById(
				`public-option-${datasetUuid}`,
			);
			const publicWarning = document.getElementById(
				`public-warning-message-${datasetUuid}`,
			);
			const publishBtn = document.getElementById(
				`publishDatasetBtn-${datasetUuid}`,
			);
			const statusBadge = document.getElementById(
				`current-status-badge-${datasetUuid}`,
			);

			// Store initial status badge text (only once)
			if (statusBadge && !statusBadge.hasAttribute("data-initial-text")) {
				statusBadge.setAttribute("data-initial-text", statusBadge.textContent);
				statusBadge.setAttribute("data-initial-class", statusBadge.className);
			}

			// Setup reset on modal close
			this.setupModalReset(modal, datasetUuid);

			// Handle publish toggle change
			if (publishToggle) {
				publishToggle.addEventListener("change", () => {
					this.handlePublishToggleChange(
						publishToggle,
						visibilitySection,
						statusBadge,
					);
				});
			}

			// Handle visibility toggle changes
			if (publicOption) {
				publicOption.addEventListener("change", () => {
					if (publicOption.checked && publicWarning) {
						publicWarning.classList.remove("d-none");
					}
				});
			}

			if (privateOption) {
				privateOption.addEventListener("change", () => {
					if (privateOption.checked && publicWarning) {
						publicWarning.classList.add("d-none");
					}
				});
			}

			// Handle publish button click
			if (publishBtn) {
				publishBtn.addEventListener("click", () => {
					this.handlePublish(
						datasetUuid,
						statusBadge,
						publishToggle,
						privateOption,
						publicOption,
					);
				});
			}
		}

		// Handle publish button clicks in dropdown (open modal)
		for (const btn of document.querySelectorAll(".publish-dataset-btn")) {
			const datasetUuid = btn.getAttribute("data-dataset-uuid");
			if (!datasetUuid) continue;

			// Only attach handler if modal exists
			const modalId = `publish-dataset-modal-${datasetUuid}`;
			const modal = document.getElementById(modalId);
			if (!modal) {
				console.warn(
					`Publish button found but modal not found for dataset ${datasetUuid}. Button will be disabled.`,
				);
				btn.disabled = true;
				btn.classList.add("disabled");
				continue;
			}

			btn.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();
				this.openPublishModal(datasetUuid);
			});
		}
	}

	/**
	 * Open publish modal for a specific dataset
	 * @param {string} datasetUuid - Dataset UUID
	 */
	openPublishModal(datasetUuid) {
		const modalId = `publish-dataset-modal-${datasetUuid}`;
		const modal = document.getElementById(modalId);
		if (!modal) {
			console.warn(
				`Publish modal not found for dataset ${datasetUuid}. The modal may not be available for this dataset.`,
			);
			// Show a user-friendly message
			this.showNotification(
				"Publish functionality is not available for this dataset.",
				"error",
			);
			return;
		}

		// Get or create Bootstrap modal instance
		if (!window.bootstrap) {
			console.error("Bootstrap is not available");
			return;
		}

		let bootstrapModal = bootstrap.Modal.getInstance(modal);
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
	 * Handle publish toggle change
	 * @param {HTMLElement} publishToggle - The publish toggle checkbox
	 * @param {HTMLElement} visibilitySection - The visibility section element
	 * @param {HTMLElement} statusBadge - The status badge element
	 * @param {string} datasetUuid - Dataset UUID
	 */
	handlePublishToggleChange(publishToggle, visibilitySection, statusBadge) {
		if (publishToggle.checked) {
			// Publishing - set status to final and show visibility options
			if (statusBadge) {
				statusBadge.textContent = "Final";
				statusBadge.className = "badge bg-success";
			}
			if (visibilitySection) {
				visibilitySection.classList.remove("d-none");
			}
		} else {
			// Not publishing - set status to draft and hide visibility options
			if (statusBadge) {
				statusBadge.textContent = "Draft";
				statusBadge.className = "badge bg-secondary";
			}
			if (visibilitySection) {
				visibilitySection.classList.add("d-none");
			}
		}
	}

	/**
	 * Handle publish button click
	 * @param {string} datasetUuid - Dataset UUID
	 * @param {HTMLElement} statusBadge - The status badge element
	 * @param {HTMLElement} publishToggle - The publish toggle checkbox
	 * @param {HTMLElement} privateOption - The private option radio button
	 * @param {HTMLElement} publicOption - The public option radio button
	 */
	async handlePublish(
		datasetUuid,
		statusBadge,
		publishToggle,
		privateOption,
		publicOption,
	) {
		if (!window.APIClient) {
			console.error("APIClient not available");
			return;
		}

		try {
			const status = publishToggle?.checked
				? "final"
				: statusBadge?.textContent?.toLowerCase() || "draft";
			const isPublic = publicOption?.checked
				? "true"
				: privateOption?.checked
					? "false"
					: "false";

			// Prepare data
			const data = {
				status: status,
				is_public: isPublic,
			};

			// Show loading state
			const publishBtn = document.getElementById(
				`publishDatasetBtn-${datasetUuid}`,
			);
			if (publishBtn) {
				publishBtn.disabled = true;
				publishBtn.innerHTML =
					'<span class="spinner-border spinner-border-sm me-2"></span>Publishing...';
			}

			// Make API call
			const url = `/users/publish-dataset/${datasetUuid}/`;
			const response = await window.APIClient.post(url, data);

			if (response.success) {
				// Show success message
				this.showNotification(
					response.message || "Dataset published successfully.",
					"success",
				);

				// Close modal
				const modal = document.getElementById(
					`publish-dataset-modal-${datasetUuid}`,
				);
				if (modal) {
					const bsModal = bootstrap.Modal.getInstance(modal);
					if (bsModal) {
						bsModal.hide();
					}
				}

				// Reload page after a short delay to show updated status
				setTimeout(() => {
					window.location.reload();
				}, 1000);
			} else {
				// Show error message
				this.showNotification(
					response.error || "An error occurred while publishing the dataset.",
					"error",
				);

				// Restore button
				if (publishBtn) {
					publishBtn.disabled = false;
					publishBtn.innerHTML = "Publish";
				}
			}
		} catch (error) {
			console.error("Error publishing dataset:", error);
			this.showNotification(
				error.message || "An error occurred while publishing the dataset.",
				"error",
			);

			// Restore button
			const publishBtn = document.getElementById(
				`publishDatasetBtn-${datasetUuid}`,
			);
			if (publishBtn) {
				publishBtn.disabled = false;
				publishBtn.innerHTML = "Publish";
			}
		}
	}

	/**
	 * Setup modal reset functionality
	 * @param {HTMLElement} modal - The modal element
	 * @param {string} datasetUuid - Dataset UUID
	 */
	setupModalReset(modal, datasetUuid) {
		// Reset form elements when modal is hidden
		modal.addEventListener("hidden.bs.modal", () => {
			this.resetModalState(datasetUuid);
		});
	}

	/**
	 * Reset modal state by resetting form elements to their default state
	 * @param {string} datasetUuid - Dataset UUID
	 */
	resetModalState(datasetUuid) {
		const publishToggle = document.getElementById(
			`publish-dataset-toggle-${datasetUuid}`,
		);
		const visibilitySection = document.getElementById(
			`visibility-toggle-section-${datasetUuid}`,
		);
		const privateOption = document.getElementById(
			`private-option-${datasetUuid}`,
		);
		const publicOption = document.getElementById(
			`public-option-${datasetUuid}`,
		);
		const publicWarning = document.getElementById(
			`public-warning-message-${datasetUuid}`,
		);
		const statusBadge = document.getElementById(
			`current-status-badge-${datasetUuid}`,
		);
		const publishBtn = document.getElementById(
			`publishDatasetBtn-${datasetUuid}`,
		);

		// Reset form elements to their default state (as rendered in template)
		if (publishToggle) {
			// Reset to default checked state from template
			publishToggle.checked = publishToggle.defaultChecked;
		}

		if (privateOption) {
			privateOption.checked = privateOption.defaultChecked;
		}

		if (publicOption) {
			publicOption.checked = publicOption.defaultChecked;
		}

		// Reset visibility section based on default publish toggle state
		if (visibilitySection && publishToggle) {
			if (publishToggle.defaultChecked) {
				visibilitySection.classList.remove("d-none");
			} else {
				visibilitySection.classList.add("d-none");
			}
		}

		// Reset public warning based on default public option state
		if (publicWarning && publicOption) {
			if (publicOption.defaultChecked) {
				publicWarning.classList.remove("d-none");
			} else {
				publicWarning.classList.add("d-none");
			}
		}

		// Reset status badge to initial text from template
		if (statusBadge) {
			const initialText = statusBadge.getAttribute("data-initial-text");
			const initialClass = statusBadge.getAttribute("data-initial-class");
			if (initialText) {
				statusBadge.textContent = initialText;
			}
			if (initialClass) {
				statusBadge.className = initialClass;
			}
		}

		// Reset publish button
		if (publishBtn) {
			publishBtn.disabled = false;
			publishBtn.innerHTML = "Publish";
		}
	}

	/**
	 * Show notification toast
	 * @param {string} message - Message to display
	 * @param {string} type - Type of notification (success, error, info)
	 */
	showNotification(message, type = "info") {
		// Use existing notification system if available
		if (typeof showAlert === "function") {
			showAlert(message, type);
		} else if (typeof window.showAlert === "function") {
			window.showAlert(message, type);
		} else {
			// Fallback to alert
			alert(message);
		}
	}
}
