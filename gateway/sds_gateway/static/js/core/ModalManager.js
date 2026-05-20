/**
 * Capture detail modal and related API calls.
 * Migrated from deprecated/components.js.
 */

class ModalManager {
	constructor(config) {
		this.modalId = config.modalId;
		this.modal = document.getElementById(this.modalId);
		this.modalTitle = config.modalTitleId
			? document.getElementById(config.modalTitleId)
			: this.modal?.querySelector(".modal-title");
		this.modalBody = config.modalBodyId
			? document.getElementById(config.modalBodyId)
			: this.modal?.querySelector(".modal-body");

		if (this.modal && window.bootstrap) {
			this.bootstrapModal = new bootstrap.Modal(this.modal);
		}
	}

	show(title, content) {
		if (!this.modal) return;

		if (this.modalTitle) {
			this.modalTitle.textContent = title;
		}

		if (this.modalBody) {
			this.modalBody.innerHTML = content;
		}

		if (this.bootstrapModal) {
			this.bootstrapModal.show();
		}
	}

	hide() {
		if (this.bootstrapModal) {
			this.bootstrapModal.hide();
		}
	}

	/**
	 * @param {HTMLElement} startEl
	 * @param {string[]} selectors
	 * @returns {HTMLElement | null}
	 */
	static findDelegateTarget(startEl, selectors) {
		if (!startEl || !selectors?.length) return null;
		for (const sel of selectors) {
			if (startEl.matches?.(sel)) return startEl;
			const closest = startEl.closest?.(sel);
			if (closest) return closest;
		}
		return null;
	}

	/**
	 * @param {HTMLElement} startEl
	 * @returns {{ cfg: object, target: HTMLElement } | null}
	 */
	static resolveDetailsModalFromTrigger(startEl) {
		const registry = window.DetailsModalAssetRegistry;
		if (!registry || !startEl) return null;
		for (const key of Object.keys(registry)) {
			const cfg = registry[key];
			const selectors = cfg.delegateClickSelectors || [];
			const target = ModalManager.findDelegateTarget(startEl, selectors);
			if (target) return { cfg, target };
		}
		return null;
	}

	openCaptureModal(linkElement) {
		return this.openDetailsFromTrigger(linkElement);
	}

	/**
	 * Load details modal body from server (registry-driven).
	 * @param {HTMLElement} startEl
	 */
	async openDetailsFromTrigger(startEl) {
		const resolved = ModalManager.resolveDetailsModalFromTrigger(startEl);
		if (!resolved) return;

		const { cfg, target } = resolved;
		const uuid = cfg.resolveUuidFromTrigger(target);
		if (!uuid || uuid === "null" || uuid === "undefined") {
			console.warn("No valid UUID for details modal:", target);
			return;
		}

		const shell =
			typeof cfg.resolveShell === "function" ? cfg.resolveShell() : null;
		if (!shell?.modal || !shell.bodyEl) {
			console.warn("Details modal shell not found:", cfg.assetType, uuid);
			return;
		}

		const { modal, titleEl, bodyEl } = shell;
		this.modalTitle = titleEl || null;
		this.modalBody = bodyEl;

		if (cfg.assetType === "capture") {
			const visualizeBtn = document.getElementById("visualize-btn");
			visualizeBtn?.classList.add("d-none");
		}

		const loadingTitle = cfg.loadingTitle || "Loading...";
		if (titleEl) {
			titleEl.textContent = loadingTitle;
		}
		bodyEl.innerHTML = `
				<div class="d-flex justify-content-center py-4">
					<div class="spinner-border text-primary" role="status">
						<span class="visually-hidden">${loadingTitle}</span>
					</div>
				</div>`;

		const bsModal = ModalManager.getOrCreateBootstrapModal(modal);
		if (bsModal) {
			bsModal.show();
		}

		try {
			const response = await fetch(cfg.buildDetailsUrl(uuid), {
				credentials: "same-origin",
				headers: { Accept: "application/json" },
			});
			if (!response.ok) {
				throw new Error(`HTTP error ${response.status}`);
			}
			const data = await response.json();

			this._nameEditIsEditing = false;

			if (titleEl) {
				titleEl.textContent = data.title || loadingTitle;
			}
			bodyEl.innerHTML = data.html || "";

			const meta = data.meta || {};

			if (cfg.assetType === "capture") {
				this.currentCaptureData = {
					uuid: meta.uuid || uuid,
					name: meta.name || "",
					topLevelDir: meta.top_level_dir || "",
					captureType: meta.capture_type || "",
				};

				ModalManager.ensureDelegatedCaptureNameEditing(this, modal);
				this.setupVisualizeFromMeta(meta);
				await this.loadCaptureFilesSummary(cfg, uuid);
			}

			if (typeof cfg.afterInject === "function") {
				cfg.afterInject({ modal, meta, uuid, cfg });
			}
		} catch (error) {
			console.error("Error opening details modal:", error);
			const errTitle = "Error";
			const errBody =
				cfg.assetType === "capture"
					? "Error displaying capture details"
					: "Error displaying dataset details";
			if (titleEl) {
				titleEl.textContent = errTitle;
			}
			bodyEl.innerHTML = `<p class="text-danger mb-0">${errBody}</p>`;
		}
	}

	_showDetailsLoadingState() {
		if (this.modalTitle) {
			this.modalTitle.textContent = "Loading...";
		}
		if (this.modalBody) {
			this.modalBody.innerHTML = `
				<div class="d-flex justify-content-center py-4">
					<div class="spinner-border text-primary" role="status">
						<span class="visually-hidden">Loading capture details...</span>
					</div>
				</div>`;
		}
	}

	/**
	 * Configure visualize header button from server meta.
	 * @param {{ visualize_enabled?: boolean, uuid?: string, capture_type?: string }} meta
	 */
	setupVisualizeFromMeta(meta) {
		const visualizeBtn = document.getElementById("visualize-btn");
		if (!visualizeBtn || !meta) return;

		if (meta.visualize_enabled) {
			visualizeBtn.classList.remove("d-none");
			visualizeBtn.dataset.captureUuid = meta.uuid || "";
			visualizeBtn.dataset.captureType = meta.capture_type || "";
			visualizeBtn.onclick = () => {
				if (window.visualizationModalInstance) {
					window.visualizationModalInstance.openWithCaptureData(
						meta.uuid,
						meta.capture_type,
					);
				}
			};
		} else {
			visualizeBtn.classList.add("d-none");
		}
	}

	/**
	 * One delegated listener on the asset details modal for name edit.
	 * @param {ModalManager} modalManager
	 * @param {HTMLElement} [modalEl] capture modal root (defaults to modalManager.modal)
	 */
	static ensureDelegatedCaptureNameEditing(modalManager, modalEl) {
		const modal = modalEl || modalManager.modal;
		if (!modal) {
			return;
		}
		if (
			modal.dataset.nameDelegationWired === "1" &&
			!modal.querySelector("#capture-name-input")
		) {
			delete modal.dataset.nameDelegationWired;
		}
		if (modal.dataset.nameDelegationWired === "1") {
			return;
		}
		modal.dataset.nameDelegationWired = "1";

		const getControls = () => ({
			nameInput: modal.querySelector("#capture-name-input"),
			editBtn: modal.querySelector("#edit-name-btn"),
			saveBtn: modal.querySelector("#save-name-btn"),
			cancelBtn: modal.querySelector("#cancel-name-btn"),
		});

		const stopEditing = (controls) => {
			if (!controls.nameInput) return;
			controls.nameInput.disabled = true;
			controls.editBtn?.classList.remove("d-none");
			controls.saveBtn?.classList.add("d-none");
			controls.cancelBtn?.classList.add("d-none");
		};

		const startEditing = (controls, originalName) => {
			if (!controls.nameInput) return;
			controls.nameInput.disabled = false;
			controls.nameInput.focus();
			controls.nameInput.select();
			controls.editBtn?.classList.add("d-none");
			controls.saveBtn?.classList.remove("d-none");
			controls.cancelBtn?.classList.remove("d-none");
			return originalName;
		};

		modalManager._nameEditOriginal = "";
		modalManager._nameEditIsEditing = false;

		modal.addEventListener("click", async (e) => {
			const controls = getControls();
			if (!controls.nameInput || !controls.editBtn) return;

			const t = e.target;

			if (t.closest("#edit-name-btn")) {
				e.preventDefault();
				if (!modalManager._nameEditIsEditing) {
					modalManager._nameEditOriginal = controls.nameInput.value;
					startEditing(controls, modalManager._nameEditOriginal);
					modalManager._nameEditIsEditing = true;
				}
				return;
			}

			if (t.closest("#cancel-name-btn")) {
				e.preventDefault();
				controls.nameInput.value = modalManager._nameEditOriginal;
				stopEditing(controls);
				modalManager._nameEditIsEditing = false;
				return;
			}

			if (t.closest("#save-name-btn")) {
				e.preventDefault();
				const newName = controls.nameInput.value.trim();
				const uuid = controls.nameInput.getAttribute("data-uuid");
				if (!uuid) return;

				controls.editBtn.disabled = true;
				controls.saveBtn.disabled = true;
				controls.cancelBtn.disabled = true;
				controls.saveBtn.innerHTML =
					'<span class="spinner-border spinner-border-sm"></span>';

				try {
					await modalManager.updateCaptureName(uuid, newName);
					modalManager._nameEditOriginal = newName;
					stopEditing(controls);
					modalManager._nameEditIsEditing = false;
					modalManager.updateTableNameDisplay(uuid, newName);
					if (modalManager.modalTitle && modalManager.currentCaptureData) {
						modalManager.currentCaptureData.name = newName;
						modalManager.modalTitle.textContent =
							newName ||
							modalManager.currentCaptureData.topLevelDir ||
							"Unnamed Capture";
					}
					modalManager.showSuccessMessage("Capture name updated successfully!");
				} catch (err) {
					console.error("Error updating capture name:", err);
					modalManager.showErrorMessage(
						"Failed to update capture name. Please try again.",
					);
					controls.nameInput.value = modalManager._nameEditOriginal;
				} finally {
					controls.editBtn.disabled = false;
					controls.saveBtn.disabled = false;
					controls.cancelBtn.disabled = false;
					controls.saveBtn.innerHTML = '<i class="bi bi-check-lg"></i>';
				}
			}
		});

		modal.addEventListener("keypress", (e) => {
			if (e.target.id !== "capture-name-input") return;
			if (e.key === "Enter" && !e.target.disabled) {
				const saveBtn = modal.querySelector("#save-name-btn");
				saveBtn?.click();
			}
		});

		modal.addEventListener("keydown", (e) => {
			if (e.target.id !== "capture-name-input") return;
			if (e.key === "Escape" && !e.target.disabled) {
				const controls = getControls();
				controls.nameInput.value = modalManager._nameEditOriginal;
				stopEditing(controls);
				modalManager._nameEditIsEditing = false;
			}
		});
	}

	/**
	 * @deprecated Use setupVisualizeFromMeta
	 */
	setupVisualizeButton(captureData) {
		this.setupVisualizeFromMeta({
			visualize_enabled: captureData.captureType === "drf",
			uuid: captureData.uuid,
			capture_type: captureData.captureType,
		});
	}

	/**
	 * Update capture name via API
	 */
	async updateCaptureName(uuid, newName) {
		const response = await fetch(`/api/v1/assets/captures/${uuid}/`, {
			method: "PATCH",
			headers: {
				"Content-Type": "application/json",
				"X-CSRFToken": this.getCSRFToken(),
			},
			body: JSON.stringify({ name: newName }),
		});

		if (!response.ok) {
			const errorData = await response.json();
			throw new Error(errorData.detail || "Failed to update capture name");
		}

		return response.json();
	}

	/**
	 * Update the table display with the new name
	 */
	updateTableNameDisplay(uuid, newName) {
		// Find all elements with this UUID and update their display
		const captureLinks = document.querySelectorAll(`[data-uuid="${uuid}"]`);

		for (const link of captureLinks) {
			// Update data attribute
			link.dataset.name = newName;

			// Update display text if it's a capture link
			if (link.classList.contains("capture-link")) {
				link.textContent = newName || "Unnamed Capture";
				link.setAttribute(
					"aria-label",
					`View details for capture ${newName || uuid}`,
				);
				link.setAttribute("title", `View capture details: ${newName || uuid}`);
			}
		}
	}

	/**
	 * Clear existing alert messages from the modal
	 */
	clearAlerts() {
		const modalBody = document.getElementById("asset-details-modal-body");
		if (modalBody) {
			const existingAlerts = modalBody.querySelectorAll(".alert");
			for (const alert of existingAlerts) {
				alert.remove();
			}
		}
	}

	/**
	 * Show success message
	 */
	showSuccessMessage(message) {
		this.showModalAlert("success", message, 3000);
	}

	/**
	 * Show error message
	 */
	showErrorMessage(message) {
		this.showModalAlert("danger", message, 5000);
	}

	/**
	 * @param {"success"|"danger"} variant
	 * @param {string} message
	 * @param {number} autoDismissMs
	 */
	async showModalAlert(variant, message, autoDismissMs) {
		this.clearAlerts();

		const modalBody = document.getElementById("asset-details-modal-body");
		if (!modalBody || !window.DOMUtils?.showMessage) {
			return false;
		}

		const alertType = variant === "success" ? "success" : "danger";
		const icon =
			variant === "success" ? "check-circle" : "exclamation-triangle";

		return window.DOMUtils.showMessage(message, {
			variant,
			placement: "append",
			target: modalBody,
			presentation: "alert",
			templateContext: {
				alert_type: alertType,
				icon,
				dismissible: true,
			},
			autoRemove: true,
			autoRemoveMs: autoDismissMs,
		});
	}

	/**
	 * Load files summary HTML from server (registry-driven).
	 * @param {{ buildFilesSummaryUrl?: (uuid: string) => string }} cfg
	 * @param {string} captureUuid
	 */
	async loadCaptureFilesSummary(cfg, captureUuid) {
		const placeholder = document.getElementById("files-section-placeholder");
		if (!placeholder || !cfg?.buildFilesSummaryUrl) {
			return;
		}
		try {
			const response = await fetch(cfg.buildFilesSummaryUrl(captureUuid), {
				credentials: "same-origin",
				headers: { Accept: "application/json" },
			});
			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}
			const data = await response.json();
			placeholder.innerHTML = data.html || "";
		} catch (error) {
			console.error("Error loading capture files:", error);
			await window.DOMUtils?.showMessage?.(
				"Error loading files information",
				{
					variant: "warning",
					placement: "replace",
					target: placeholder,
					presentation: "alert",
					templateContext: {
						alert_type: "warning",
						icon: "exclamation-triangle",
					},
				},
			);
		}
	}

	/**
	 * @deprecated Use loadCaptureFilesSummary with registry config
	 */
	async loadCaptureFiles(captureUuid) {
		const cfg = window.DetailsModalAssetRegistry?.capture;
		if (cfg) {
			await this.loadCaptureFilesSummary(cfg, captureUuid);
		}
	}

	/**
	 * Format file metadata for display
	 */
	formatFileMetadata(file) {
		const metadata = [];

		// Primary file information - most useful for users
		if (file.size) {
			metadata.push(
				`<strong>Size:</strong> ${window.DOMUtils.formatFileSize(file.size)} (${file.size.toLocaleString()} bytes)`,
			);
		}

		if (file.media_type) {
			metadata.push(
				`<strong>Media Type:</strong> ${window.DOMUtils.escapeHtml(file.media_type)}`,
			);
		}

		if (file.created_at) {
			metadata.push(`<strong>Created:</strong> ${file.created_at}`);
		}

		if (file.updated_at) {
			metadata.push(`<strong>Updated:</strong> ${file.updated_at}`);
		}

		// File properties and attributes
		if (file.name) {
			metadata.push(
				`<strong>Name:</strong> ${window.DOMUtils.escapeHtml(file.name)}`,
			);
		}

		if (file.directory || file.relative_path) {
			metadata.push(
				`<strong>Directory:</strong> ${window.DOMUtils.escapeHtml(file.directory || file.relative_path)}`,
			);
		}

		// Removed permissions display
		// if (file.permissions) {
		// 	metadata.push(`<strong>Permissions:</strong> <span style="color: #005a9c; font-family: monospace;">${window.DOMUtils.escapeHtml(file.permissions)}</span>`);
		// }

		if (file.owner?.username) {
			metadata.push(
				`<strong>Owner:</strong> ${window.DOMUtils.escapeHtml(file.owner.username)}`,
			);
		}

		if (file.expiration_date) {
			metadata.push(
				`<strong>Expires:</strong> ${new Date(file.expiration_date).toLocaleDateString()}`,
			);
		}

		if (file.bucket_name) {
			metadata.push(
				`<strong>Storage Bucket:</strong> ${window.DOMUtils.escapeHtml(file.bucket_name)}`,
			);
		}

		// Removed checksum display
		// if (file.sum_blake3) {
		// 	metadata.push(`<strong>Checksum:</strong> <span style="color: #005a9c; font-family: monospace;">${window.DOMUtils.escapeHtml(file.sum_blake3)}</span>`);
		// }

		// Associated resources
		// TODO: Refactor this to handle multiple associations
		if (file.capture?.name) {
			metadata.push(
				`<strong>Associated Capture:</strong> ${window.DOMUtils.escapeHtml(file.capture.name)}`,
			);
		}

		if (file.dataset?.name) {
			metadata.push(
				`<strong>Associated Dataset:</strong> ${window.DOMUtils.escapeHtml(file.dataset.name)}`,
			);
		}

		// Additional metadata if available
		if (file.metadata && typeof file.metadata === "object") {
			for (const [key, value] of Object.entries(file.metadata)) {
				if (value !== null && value !== undefined) {
					const formattedKey = key
						.replace(/_/g, " ")
						.replace(/\b\w/g, (l) => l.toUpperCase());
					let formattedValue;

					// Format different types of values
					if (typeof value === "boolean") {
						formattedValue = value ? "Yes" : "No";
					} else if (typeof value === "number") {
						formattedValue = value.toLocaleString();
					} else if (typeof value === "object") {
						formattedValue = `<span style="color: #005a9c; font-family: monospace;">${JSON.stringify(value, null, 2)}</span>`;
					} else {
						formattedValue = window.DOMUtils.escapeHtml(String(value));
					}

					metadata.push(`<strong>${formattedKey}:</strong> ${formattedValue}`);
				}
			}
		}

		if (metadata.length === 0) {
			return '<p class="text-muted mb-0">No metadata available for this file.</p>';
		}

		return `<div class="metadata-list">${metadata.join("<br>")}</div>`;
	}

	/**
	 * Get CSRF token for API requests
	 */
	getCSRFToken() {
		if (window.APIClient) {
			try {
				return new window.APIClient().getCSRFToken();
			} catch (_) {}
		}
		const token = document.querySelector("[name=csrfmiddlewaretoken]");
		return token ? token.value : "";
	}

	/**
	 * Load and display file metadata for a specific file in the modal
	 */
	async loadFileMetadata(fileUuid, fileName) {
		const fileMetadataSection = document.getElementById(
			`file-metadata-${fileUuid}`,
		);
		const metadataContent =
			fileMetadataSection?.querySelector(".metadata-content");

		if (!fileMetadataSection || !metadataContent) return;

		// Toggle visibility
		if (fileMetadataSection.style.display === "none") {
			fileMetadataSection.style.display = "block";

			// Check if metadata is already loaded
			if (metadataContent.innerHTML.includes("Click to load metadata...")) {
				// Show loading state
				metadataContent.innerHTML = `
					<div class="d-flex justify-content-center py-2">
						<div class="spinner-border spinner-border-sm me-2" role="status">
							<span class="visually-hidden">Loading...</span>
						</div>
						<span class="text-muted">Loading metadata...</span>
					</div>
				`;

				try {
					const response = await fetch(`/api/v1/assets/files/${fileUuid}/`, {
						method: "GET",
						headers: {
							"Content-Type": "application/json",
							"X-CSRFToken": this.getCSRFToken(),
						},
					});

					if (!response.ok) {
						throw new Error(`HTTP error! status: ${response.status}`);
					}

					const fileData = await response.json();

					// Format and display the metadata
					const formattedMetadata = this.formatFileMetadata(fileData);
					metadataContent.innerHTML = formattedMetadata;
				} catch (error) {
					console.error("Error loading file metadata:", error);
					metadataContent.innerHTML = `
						<div class="alert alert-warning mb-0">
							<i class="bi bi-exclamation-triangle me-2"></i>
							Failed to load metadata for ${window.DOMUtils.escapeHtml(fileName)}.
							<br><small>Error: ${window.DOMUtils.escapeHtml(error.message)}</small>
						</div>
					`;
				}
			}
		} else {
			fileMetadataSection.style.display = "none";
		}
	}

	/**
	 * Delegated document clicks → details modals (capture + dataset registry).
	 * @param {ModalManager} modalManager
	 * @returns {() => void} cleanup
	 */
	static attachDocumentDetailsClickDelegation(modalManager) {
		const handler = (e) => {
			if (
				e.target.matches('[data-bs-toggle="dropdown"]') ||
				e.target.closest('[data-bs-toggle="dropdown"]')
			) {
				return;
			}
			const resolved = ModalManager.resolveDetailsModalFromTrigger(e.target);
			if (!resolved) return;
			e.preventDefault();
			const { target } = resolved;
			void modalManager?.openDetailsFromTrigger?.(target);
		};
		document.addEventListener("click", handler);
		return () => {
			document.removeEventListener("click", handler);
			if (typeof document !== "undefined" && document.body) {
				document.body.dataset.detailsAssetClickWired = "";
			}
		};
	}

	/**
	 * Coordinator ModalManager for registry-driven details (capture singleton or noop shell).
	 */
	static getOrCreateDetailsClickCoordinator() {
		if (typeof window !== "undefined" && window.filesCaptureModalManager) {
			return window.filesCaptureModalManager;
		}
		if (typeof window !== "undefined" && !window.detailsModalClickCoordinator) {
			window.detailsModalClickCoordinator = new ModalManager({
				modalId: "asset-details-modal",
				modalBodyId: "asset-details-modal-body",
				modalTitleId: "asset-details-modal-label",
			});
		}
		return typeof window !== "undefined"
			? window.detailsModalClickCoordinator
			: null;
	}

	/**
	 * Single global document delegation for DetailsModalAssetRegistry (idempotent).
	 * @returns {() => void} cleanup
	 */
	static ensureDetailsModalClickDelegation() {
		if (
			typeof document === "undefined" ||
			document.body?.dataset?.detailsAssetClickWired === "1"
		) {
			return () => {};
		}
		document.body.dataset.detailsAssetClickWired = "1";
		const mgr = ModalManager.getOrCreateDetailsClickCoordinator();
		if (!mgr) {
			return () => {};
		}
		return ModalManager.attachDocumentDetailsClickDelegation(mgr);
	}

	/**
	 * @deprecated Use attachDocumentDetailsClickDelegation
	 */
	static attachDocumentCaptureClickDelegation(modalManager) {
		return ModalManager.attachDocumentDetailsClickDelegation(modalManager);
	}

	/**
	 * Files browser: capture modal + delegated row clicks + per-modal ShareActionManager.
	 * @param {{ permissions: object }} options
	 * @returns {() => void} cleanup
	 */
	static initFilesPageCaptureModals(options) {
		const permConfig = options?.permissions;
		const bound = [];

		const modalManager = new ModalManager({
			modalId: "asset-details-modal",
			modalBodyId: "asset-details-modal-body",
			modalTitleId: "asset-details-modal-label",
		});
		window.filesCaptureModalManager = modalManager;

		const detachClicks = ModalManager.ensureDetailsModalClickDelegation();

		if (!permConfig || !window.PermissionsManager || !window.ShareActionManager) {
			return () => {
				detachClicks?.();
			};
		}

		const permissionsManager = new window.PermissionsManager(permConfig);

		const uuidRegex =
			/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
		const validTypes = new Set(["capture", "dataset", "file"]);

		for (const modal of document.querySelectorAll(".modal[data-item-uuid]")) {
			const itemUuid = modal.getAttribute("data-item-uuid");
			const itemType = modal.getAttribute("data-item-type");
			if (!itemUuid || !itemType || !uuidRegex.test(itemUuid) || !validTypes.has(itemType)) {
				continue;
			}

			const shareManager = new window.ShareActionManager({
				itemUuid,
				itemType,
				permissions: permissionsManager,
			});
			modal.shareActionManager = shareManager;

			const onHidden = () => {
				modal.shareActionManager?.clearSelections?.();
			};
			modal.addEventListener("hidden.bs.modal", onHidden);
			bound.push({ modal, onHidden });
		}

		return () => {
			detachClicks?.();
			for (const { modal, onHidden } of bound) {
				modal.removeEventListener("hidden.bs.modal", onHidden);
			}
		};
	}

	/**
	 * Dispose/recreate Bootstrap Modal instances (dataset list full refresh).
	 * @param {ParentNode} [root]
	 */
	static prepareBootstrapModalInstances(root = document) {
		if (!window.bootstrap) return;
		for (const modal of root.querySelectorAll(".modal")) {
			const existingInstance = bootstrap.Modal.getInstance(modal);
			if (existingInstance) {
				try {
					existingInstance.dispose();
				} catch (e) {
					console.warn("Failed to dispose modal instance:", e);
				}
			}
			new bootstrap.Modal(modal, {
				backdrop: true,
				keyboard: true,
				focus: true,
			});
		}
	}

	/**
	 * @param {HTMLElement} element
	 * @param {object} [options] Bootstrap Modal options
	 * @returns {object | null}
	 */
	static getOrCreateBootstrapModal(element, options = {}) {
		if (!element || !window.bootstrap?.Modal) return null;
		let inst = bootstrap.Modal.getInstance(element);
		if (!inst) inst = new bootstrap.Modal(element, options);
		return inst;
	}

	/**
	 * @param {HTMLElement} element
	 * @param {object} [options]
	 * @returns {object | null}
	 */
	static openModalElement(element, options = {}) {
		const inst = ModalManager.getOrCreateBootstrapModal(element, options);
		if (inst) inst.show();
		return inst;
	}

	/** @param {HTMLElement | null} element */
	static hideModalElement(element) {
		if (!element || !window.bootstrap?.Modal) return;
		const inst = bootstrap.Modal.getInstance(element);
		if (inst) inst.hide();
	}

	/**
	 * Share managers for list modals (dataset + capture).
	 * @param {Element} modal
	 * @param {PermissionsManager|null} permissions
	 * @param {unknown[]} managersOut
	 * @param {string} contextLabel - log context when UUID/permissions missing
	 * @returns {string|null} data-item-uuid when wired, else null
	 */
	static _wireShareManagerForListModal(modal, permissions, managersOut, contextLabel) {
		const itemUuid = modal.getAttribute("data-item-uuid");
		const itemType = modal.getAttribute("data-item-type");

		if (!itemUuid || !permissions) {
			console.warn(
				`No item UUID or permissions found for ${contextLabel}: ${modal}`,
			);
			return null;
		}

		if (window.ShareActionManager) {
			const shareManager = new window.ShareActionManager({
				permissions,
				itemUuid: itemUuid,
				itemType: itemType,
			});
			managersOut.push(shareManager);
			modal.shareActionManager = shareManager;
		}
		return itemUuid;
	}

	/**
	 * Share / versioning / details managers for dataset modals (list + edit pages).
	 * @param {PermissionsManager|null} permissions
	 * @param {unknown[]} managersOut
	 */
	static wireDatasetListModals(permissions, managersOut) {
		ModalManager.prepareBootstrapModalInstances(document);

		const datasetModals = document.querySelectorAll(
			".modal[data-item-type='dataset']",
		);

		for (const modal of datasetModals) {
			const itemUuid = ModalManager._wireShareManagerForListModal(
				modal,
				permissions,
				managersOut,
				"dataset modal",
			);
			if (!itemUuid) continue;

			if (window.VersioningActionManager && !modal.versioningActionManager) {
				const versioningManager = new window.VersioningActionManager({
					permissions,
					datasetUuid: itemUuid,
				});
				managersOut.push(versioningManager);
				modal.versioningActionManager = versioningManager;
			}
		}
	}

	/**
	 * Share managers for capture modals (capture list HTML refresh).
	 * @param {PermissionsManager|null} permissions
	 * @param {unknown[]} managersOut
	 */
	static wireCaptureListModals(permissions, managersOut) {
		const captureModals = document.querySelectorAll(
			".modal[data-item-type='capture']",
		);

		for (const modal of captureModals) {
			ModalManager._wireShareManagerForListModal(
				modal,
				permissions,
				managersOut,
				"capture modal",
			);
		}
	}
}

if (typeof window !== "undefined") {
	window.ModalManager = ModalManager;
}
if (typeof module !== "undefined" && module.exports) {
	module.exports = { ModalManager };
}

