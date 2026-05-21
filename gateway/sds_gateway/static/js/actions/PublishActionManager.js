/**
 * Publish Action Manager
 * Handles all publish-related actions
 */
class PublishActionManager extends ModalManager {
	/**
	 * Initialize publish action manager
	 * @param {Object} config - Configuration object
	 */
	constructor(config) {
		super();
		this.config = config || {};
		this.initializeEventListeners();
	}

	/**
	 * Cached DOM refs for a publish modal by dataset UUID.
	 * @param {string} datasetUuid
	 * @returns {{
	 *   publishToggle: HTMLElement | null,
	 *   visibilitySection: HTMLElement | null,
	 *   privateOption: HTMLElement | null,
	 *   publicOption: HTMLElement | null,
	 *   publicWarning: HTMLElement | null,
	 *   publishBtn: HTMLElement | null,
	 *   statusBadge: HTMLElement | null,
	 * }}
	 */
	_getPublishModalElements(datasetUuid) {
		return {
			publishToggle: document.getElementById(
				`publish-dataset-toggle-${datasetUuid}`,
			),
			visibilitySection: document.getElementById(
				`visibility-toggle-section-${datasetUuid}`,
			),
			privateOption: document.getElementById(`private-option-${datasetUuid}`),
			publicOption: document.getElementById(`public-option-${datasetUuid}`),
			publicWarning: document.getElementById(
				`public-warning-message-${datasetUuid}`,
			),
			publishBtn: document.getElementById(`publishDatasetBtn-${datasetUuid}`),
			statusBadge: document.getElementById(
				`current-status-badge-${datasetUuid}`,
			),
		};
	}

	/**
	 * Initialize event listeners for all publish modals on the page
	 */
	initializeEventListeners() {
		const publishModals = document.querySelectorAll(
			'[id^="publish-dataset-modal-"]',
		);

		for (const modal of publishModals) {
			const datasetUuid = modal.getAttribute("data-dataset-uuid");
			if (!datasetUuid) continue;

			const {
				publishToggle,
				visibilitySection,
				privateOption,
				publicOption,
				publicWarning,
				publishBtn,
				statusBadge,
			} = this._getPublishModalElements(datasetUuid);

			if (statusBadge && !statusBadge.hasAttribute("data-initial-text")) {
				statusBadge.setAttribute("data-initial-text", statusBadge.textContent);
				statusBadge.setAttribute("data-initial-class", statusBadge.className);
			}

			this.setupModalReset(modal, datasetUuid);

			if (publishToggle) {
				publishToggle.addEventListener("change", () => {
					this.handlePublishToggleChange(
						publishToggle,
						visibilitySection,
						statusBadge,
					);
				});
			}

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

		for (const btn of document.querySelectorAll(".publish-dataset-btn")) {
			const datasetUuid = btn.getAttribute("data-dataset-uuid");
			if (!datasetUuid) continue;

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

	openPublishModal(datasetUuid) {
		const modalId = `publish-dataset-modal-${datasetUuid}`;
		const modal = document.getElementById(modalId);
		if (!modal) {
			console.warn(
				`Publish modal not found for dataset ${datasetUuid}. The modal may not be available for this dataset.`,
			);
			this.showToast(
				"Publish functionality is not available for this dataset.",
				"error",
			);
			return;
		}

		this.openModal(modalId);
	}

	handlePublishToggleChange(publishToggle, visibilitySection, statusBadge) {
		if (publishToggle.checked) {
			if (statusBadge) {
				statusBadge.textContent = "Final";
				statusBadge.className = "badge bg-success";
			}
			if (visibilitySection) {
				visibilitySection.classList.remove("d-none");
			}
		} else {
			if (statusBadge) {
				statusBadge.textContent = "Draft";
				statusBadge.className = "badge bg-secondary";
			}
			if (visibilitySection) {
				visibilitySection.classList.add("d-none");
			}
		}
	}

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

			const data = {
				status: status,
				is_public: isPublic,
			};

			const { publishBtn } = this._getPublishModalElements(datasetUuid);
			if (publishBtn) {
				publishBtn.disabled = true;
				publishBtn.innerHTML =
					'<span class="spinner-border spinner-border-sm me-2"></span>Publishing...';
			}

			const url = `/users/publish-dataset/${datasetUuid}/`;
			const response = await window.APIClient.post(url, data);

			if (response.success) {
				this.showToast(
					response.message || "Dataset published successfully.",
					"success",
				);

				const modalId = `publish-dataset-modal-${datasetUuid}`;
				this.closeModal(modalId);

				setTimeout(() => {
					window.location.reload();
				}, 1000);
			} else {
				this.showToast(
					response.error || "An error occurred while publishing the dataset.",
					"error",
				);

				if (publishBtn) {
					publishBtn.disabled = false;
					publishBtn.innerHTML = "Publish";
				}
			}
		} catch (error) {
			console.error("Error publishing dataset:", error);
			this.showToast(
				error.message || "An error occurred while publishing the dataset.",
				"error",
			);

			const { publishBtn: pb } = this._getPublishModalElements(datasetUuid);
			if (pb) {
				pb.disabled = false;
				pb.innerHTML = "Publish";
			}
		}
	}

	setupModalReset(modal, datasetUuid) {
		modal.addEventListener("hidden.bs.modal", () => {
			this.resetModalState(datasetUuid);
		});
	}

	resetModalState(datasetUuid) {
		const {
			publishToggle,
			visibilitySection,
			privateOption,
			publicOption,
			publicWarning,
			statusBadge,
			publishBtn,
		} = this._getPublishModalElements(datasetUuid);

		if (publishToggle) {
			publishToggle.checked = publishToggle.defaultChecked;
		}

		if (privateOption) {
			privateOption.checked = privateOption.defaultChecked;
		}

		if (publicOption) {
			publicOption.checked = publicOption.defaultChecked;
		}

		if (visibilitySection && publishToggle) {
			if (publishToggle.defaultChecked) {
				visibilitySection.classList.remove("d-none");
			} else {
				visibilitySection.classList.add("d-none");
			}
		}

		if (publicWarning && publicOption) {
			if (publicOption.defaultChecked) {
				publicWarning.classList.remove("d-none");
			} else {
				publicWarning.classList.add("d-none");
			}
		}

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

		if (publishBtn) {
			publishBtn.disabled = false;
			publishBtn.innerHTML = "Publish";
		}
	}
}

window.PublishActionManager = PublishActionManager;

if (typeof module !== "undefined" && module.exports) {
	module.exports = { PublishActionManager };
}
