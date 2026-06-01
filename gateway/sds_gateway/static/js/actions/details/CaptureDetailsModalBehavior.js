/**
 * Capture-specific asset details modal behavior (name edit, visualize button).
 */
class CaptureDetailsModalBehavior {
    /**
     * @param {{ modal: HTMLElement, meta: object, uuid: string }} ctx
     */
    static afterInject(ctx) {
        const { modal, meta } = ctx
        const visualizeBtn = document.getElementById("visualize-btn")
        visualizeBtn?.classList.add("d-none")

        CaptureDetailsModalBehavior.setupVisualizeFromMeta(meta)
        CaptureDetailsModalBehavior.ensureDelegatedCaptureNameEditing(modal)
    }

    /**
     * @param {{ visualize_enabled?: boolean, uuid?: string, capture_type?: string }} meta
     */
    static setupVisualizeFromMeta(meta) {
        const visualizeBtn = document.getElementById("visualize-btn")
        if (!visualizeBtn || !meta) return

        if (meta.visualize_enabled) {
            visualizeBtn.classList.remove("d-none")
            visualizeBtn.dataset.captureUuid = meta.uuid || ""
            visualizeBtn.dataset.captureType = meta.capture_type || ""
            visualizeBtn.onclick = (e) => {
                e?.preventDefault?.()
                if (
                    !window.visualizationModalInstance &&
                    window.VisualizationModal
                ) {
                    window.visualizationModalInstance =
                        new window.VisualizationModal()
                }
                if (window.visualizationModalInstance) {
                    window.visualizationModalInstance.openWithCaptureData(
                        meta.uuid,
                        meta.capture_type,
                    )
                }
            }
        } else {
            visualizeBtn.classList.add("d-none")
        }
    }

    /**
     * @param {HTMLElement} modalEl
     */
    static ensureDelegatedCaptureNameEditing(modalEl) {
        const modal = modalEl
        if (!modal) return

        if (
            modal.dataset.nameDelegationWired === "1" &&
            !modal.querySelector("#capture-name-input")
        ) {
            delete modal.dataset.nameDelegationWired
        }
        if (modal.dataset.nameDelegationWired === "1") {
            return
        }
        modal.dataset.nameDelegationWired = "1"

        const state = { original: "", isEditing: false }

        const getControls = () => ({
            nameInput: modal.querySelector("#capture-name-input"),
            editBtn: modal.querySelector("#edit-name-btn"),
            saveBtn: modal.querySelector("#save-name-btn"),
            cancelBtn: modal.querySelector("#cancel-name-btn"),
        })

        const stopEditing = (controls) => {
            if (!controls.nameInput) return
            controls.nameInput.disabled = true
            controls.editBtn?.classList.remove("d-none")
            controls.saveBtn?.classList.add("d-none")
            controls.cancelBtn?.classList.add("d-none")
        }

        const startEditing = (controls) => {
            if (!controls.nameInput) return
            controls.nameInput.disabled = false
            controls.nameInput.focus()
            controls.nameInput.select()
            controls.editBtn?.classList.add("d-none")
            controls.saveBtn?.classList.remove("d-none")
            controls.cancelBtn?.classList.remove("d-none")
        }

        const titleEl =
            document.getElementById("asset-details-modal-label") ||
            modal.querySelector(".modal-title")

        modal.addEventListener("click", async (e) => {
            const controls = getControls()
            if (!controls.nameInput || !controls.editBtn) return

            const t = e.target

            if (t.closest("#edit-name-btn")) {
                e.preventDefault()
                if (!state.isEditing) {
                    state.original = controls.nameInput.value
                    startEditing(controls)
                    state.isEditing = true
                }
                return
            }

            if (t.closest("#cancel-name-btn")) {
                e.preventDefault()
                controls.nameInput.value = state.original
                stopEditing(controls)
                state.isEditing = false
                return
            }

            if (t.closest("#save-name-btn")) {
                e.preventDefault()
                const newName = controls.nameInput.value.trim()
                const uuid = controls.nameInput.getAttribute("data-uuid")
                if (!uuid) return

                controls.editBtn.disabled = true
                controls.saveBtn.disabled = true
                controls.cancelBtn.disabled = true
                controls.saveBtn.innerHTML =
                    '<span class="spinner-border spinner-border-sm"></span>'

                try {
                    await CaptureDetailsModalBehavior.updateCaptureName(
                        uuid,
                        newName,
                    )
                    state.original = newName
                    stopEditing(controls)
                    state.isEditing = false
                    CaptureDetailsModalBehavior.updateTableNameDisplay(
                        uuid,
                        newName,
                    )
                    if (titleEl) {
                        titleEl.textContent = newName || "Unnamed Capture"
                    }
                    const modalBody = document.getElementById(
                        "asset-details-modal-body",
                    )
                    if (modalBody && window.DOMUtils?.showMessage) {
                        window.DOMUtils.clearAlerts?.(modalBody)
                        await window.DOMUtils.showMessage(
                            "Capture name updated successfully!",
                            {
                                variant: "success",
                                placement: "append",
                                target: modalBody,
                                presentation: "alert",
                                templateContext: {
                                    alert_type: "success",
                                    icon: "check-circle",
                                    dismissible: true,
                                },
                                autoRemove: true,
                                autoRemoveMs: 3000,
                            },
                        )
                    }
                } catch (err) {
                    console.error("Error updating capture name:", err)
                    const modalBody = document.getElementById(
                        "asset-details-modal-body",
                    )
                    if (modalBody && window.DOMUtils?.showMessage) {
                        window.DOMUtils.clearAlerts?.(modalBody)
                        await window.DOMUtils.showMessage(
                            "Failed to update capture name. Please try again.",
                            {
                                variant: "danger",
                                placement: "append",
                                target: modalBody,
                                presentation: "alert",
                                templateContext: {
                                    alert_type: "danger",
                                    icon: "exclamation-triangle",
                                    dismissible: true,
                                },
                                autoRemove: true,
                                autoRemoveMs: 5000,
                            },
                        )
                    }
                    controls.nameInput.value = state.original
                } finally {
                    controls.editBtn.disabled = false
                    controls.saveBtn.disabled = false
                    controls.cancelBtn.disabled = false
                    controls.saveBtn.innerHTML =
                        '<i class="bi bi-check-lg"></i>'
                }
            }
        })

        modal.addEventListener("keypress", (e) => {
            if (e.target.id !== "capture-name-input") return
            if (e.key === "Enter" && !e.target.disabled) {
                modal.querySelector("#save-name-btn")?.click()
            }
        })

        modal.addEventListener("keydown", (e) => {
            if (e.target.id !== "capture-name-input") return
            if (e.key === "Escape" && !e.target.disabled) {
                const controls = getControls()
                controls.nameInput.value = state.original
                stopEditing(controls)
                state.isEditing = false
            }
        })
    }

    static async updateCaptureName(uuid, newName) {
        const response = await fetch(`/api/v1/assets/captures/${uuid}/`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": new window.APIClient().getCSRFToken(),
            },
            body: JSON.stringify({ name: newName }),
        })

        if (!response.ok) {
            const errorData = await response.json()
            throw new Error(errorData.detail || "Failed to update capture name")
        }

        return response.json()
    }

    static updateTableNameDisplay(uuid, newName) {
        for (const link of document.querySelectorAll(`[data-uuid="${uuid}"]`)) {
            link.dataset.name = newName
            if (link.classList.contains("capture-link")) {
                link.textContent = newName || "Unnamed Capture"
                link.setAttribute(
                    "aria-label",
                    `View details for capture ${newName || uuid}`,
                )
                link.setAttribute(
                    "title",
                    `View capture details: ${newName || uuid}`,
                )
            }
        }
    }
}

if (typeof window !== "undefined") {
    window.CaptureDetailsModalBehavior = CaptureDetailsModalBehavior
}
if (typeof module !== "undefined" && module.exports) {
    module.exports = { CaptureDetailsModalBehavior }
}
