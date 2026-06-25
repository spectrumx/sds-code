/**
 * Dataset Editing Handler
 * Handles dataset editing workflow with pending changes management
 */
class DatasetEditingHandler extends BaseManager {
    /**
     * Initialize dataset editing handler
     * @param {Object} config - Configuration object
     */
    constructor(config) {
        super()
        this.datasetUuid = config.datasetUuid
        this.permissions = config.permissions // PermissionsManager instance
        this.currentUserId = config.currentUserId

        // Current assets in dataset
        this.currentCaptures = new Map()
        this.currentFiles = new Map()

        // Pending changes
        this.pendingCaptures = new Map() // key: captureId, value: {action: 'add'|'remove', data: {...}}
        this.pendingFiles = new Map() // key: fileId, value: {action: 'add'|'remove', data: {...}}

        // Search handlers
        this.capturesSearchHandler = null
        this.filesSearchHandler = null

        // Properties that SearchHandler expects from formHandler
        this.selectedCaptures = new Set()
        this.selectedFiles = new Set()

        // Store initial data
        this.initialCaptures = config.initialCaptures || []
        this.initialFiles = config.initialFiles || []

        this.initializeEventListeners()
        this.initializeAuthorsManagement()

        // Load current assets if no initial data provided
        if (!this.initialCaptures.length && !this.initialFiles.length) {
            this.loadCurrentAssets()
        }
    }

    /**
     * Initialize event listeners
     */
    initializeEventListeners() {
        // Initialize search handlers if they exist
        if (window.AssetSearchHandler) {
            this.capturesSearchHandler = new window.AssetSearchHandler({
                searchFormId: "captures-search-form",
                searchButtonId: "search-captures",
                clearButtonId: "clear-captures-search",
                tableBodyId: "captures-table-body",
                paginationContainerId: "captures-pagination",
                type: "captures",
                formHandler: this,
                isEditMode: true,
            })

            this.filesSearchHandler = new window.AssetSearchHandler({
                searchFormId: "files-search-form",
                searchButtonId: "search-files",
                clearButtonId: "clear-files-search",
                tableBodyId: "file-tree-root",
                paginationContainerId: "files-pagination",
                confirmFileSelectionId: "confirm-file-selection",
                type: "files",
                formHandler: this,
                isEditMode: true,
                apiEndpoint: window.location.pathname,
            })

            // Initialize captures search to show initial state
            if (
                this.capturesSearchHandler &&
                typeof this.capturesSearchHandler.initializeCapturesSearch ===
                    "function"
            ) {
                this.capturesSearchHandler.initializeCapturesSearch()
            }

            // Populate initial data now that handlers are ready
            this.populateFromInitialData(
                this.initialCaptures,
                this.initialFiles,
            )

            this.initializeFileBrowserModal()
        }

        const datasetForm = document.getElementById("datasetForm")
        if (datasetForm && !datasetForm.dataset.enterSubmitGuardBound) {
            datasetForm.dataset.enterSubmitGuardBound = "true"
            datasetForm.addEventListener("submit", (e) => {
                e.preventDefault()
            })
            datasetForm.addEventListener("keypress", (e) => {
                if (e.key !== "Enter") {
                    return
                }
                if (e.target instanceof HTMLTextAreaElement) {
                    return
                }
                e.preventDefault()
            })
        }
    }

    /**
     * Set search handler reference
     * @param {Object} searchHandler - Search handler instance
     * @param {string} type - Handler type (captures or files)
     */
    setSearchHandler(searchHandler, type) {
        if (type === "captures") {
            this.capturesSearchHandler = searchHandler
            // Defer population until SearchHandler is fully ready
            Promise.resolve().then(() => {
                this.populateSearchHandlerWithInitialData()
            })
        } else if (type === "files") {
            this.filesSearchHandler = searchHandler
            this.filesSearchHandler?.syncCommittedFileSelectionUI?.()
        }
    }

    /**
     * Populate search handler with initial data
     */
    populateSearchHandlerWithInitialData() {
        // Populate the SearchHandler with initial captures if available
        if (
            this.capturesSearchHandler?.selectedCaptures &&
            this.capturesSearchHandler.selectedCaptureDetails &&
            this.initialCaptures &&
            this.initialCaptures.length > 0
        ) {
            for (const capture of this.initialCaptures) {
                this.capturesSearchHandler.selectedCaptures.add(
                    capture.id.toString(),
                )
                this.capturesSearchHandler.selectedCaptureDetails.set(
                    capture.id.toString(),
                    capture,
                )
            }
        }
        // Also populate the DatasetEditingHandler's selectedCaptures set
        if (this.initialCaptures && this.initialCaptures.length > 0) {
            for (const capture of this.initialCaptures) {
                this.selectedCaptures.add(capture.id.toString())
            }
        }
    }

    /**
     * Populate from initial data
     * @param {Array} initialCaptures - Initial captures data
     * @param {Array} initialFiles - Initial files data
     */
    populateFromInitialData(initialCaptures, initialFiles) {
        // Populate current captures in the side panel table
        this.currentCaptures.clear()
        this.populateCurrentCapturesList(initialCaptures)

        // Use the existing SearchHandler to populate captures in the main table
        if (this.capturesSearchHandler?.selectedCaptures) {
            if (initialCaptures && initialCaptures.length > 0) {
                for (const capture of initialCaptures) {
                    this.capturesSearchHandler.selectedCaptures.add(
                        capture.id.toString(),
                    )
                    this.capturesSearchHandler.selectedCaptureDetails.set(
                        capture.id.toString(),
                        capture,
                    )
                }
            }
        }

        // Also populate the DatasetEditingHandler's selectedCaptures set
        if (initialCaptures && initialCaptures.length > 0) {
            for (const captureId of initialCaptures) {
                this.selectedCaptures.add(captureId.toString())
            }
        }

        // Populate current files
        this.currentFiles.clear()
        this.populateCurrentFilesList(initialFiles)

        // Use the existing SearchHandler to populate files for the file browser
        if (this.filesSearchHandler) {
            this.filesSearchHandler?.syncCommittedFileSelectionUI?.()
        }

        // Add event listeners for remove buttons
        this.addRemoveButtonListeners()
    }

    /**
     * Initialize file browser modal handlers
     */
    initializeFileBrowserModal() {
        window.AuthorsManager?.bindFileTreeModalHandlers(this)
    }

    /**
     * Handle file modal show
     */
    onFileModalShow() {
        if (window.AuthorsManager?.refreshFileTreeModal(this)) {
            this.syncAllPendingFileRemovalStylesInTree()
        }
    }

    /**
     * Handle file modal hide
     */
    onFileModalHide() {
        this.filesSearchHandler?.clearModalFileSelections()
    }

    /**
     * Populate current captures list
     * @param {Array} captures - Captures data
     */
    async populateCurrentCapturesList(captures) {
        const currentCapturesList = document.getElementById(
            "current-captures-list",
        )
        const currentCapturesCount = document.querySelector(
            ".current-captures-count",
        )

        if (!currentCapturesList) return

        if (captures && captures.length > 0) {
            // Normalize for generic table_rows template
            const rows = captures.map((capture) => {
                this.currentCaptures.set(capture.id, capture)
                // Permission logic: co-owners can remove anyone's captures, contributors can only remove their own
                const isOwnedByCurrentUser =
                    capture.owner_id === this.currentUserId
                const canRemoveThisCapture =
                    this.permissions.canRemoveAnyAssets() ||
                    (this.permissions.canRemoveAsset(capture) &&
                        isOwnedByCurrentUser)

                return {
                    css_class: !canRemoveThisCapture ? "readonly-row" : "",
                    data_attrs: { "capture-id": capture.id },
                    cells: [
                        { kind: "text", value: capture.type },
                        { kind: "text", value: capture.directory },
                        {
                            kind: "text",
                            value:
                                capture.owner?.name ||
                                capture.owner?.email ||
                                "Unknown",
                        },
                    ],
                    actions: canRemoveThisCapture
                        ? [
                              {
                                  label: "Remove",
                                  css_class: "btn-danger",
                                  extra_class: "mark-for-removal-btn",
                                  data_attrs: {
                                      "capture-id": capture.id,
                                      "capture-type": "capture",
                                  },
                              },
                          ]
                        : [{ html: '<span class="text-muted">N/A</span>' }],
                }
            })

            // Render using DOMUtils
            const success = await window.DOMUtils.renderTable(
                currentCapturesList,
                rows,
                {
                    empty_message: "No captures in dataset",
                    empty_colspan: 4,
                },
            )

            if (!success) {
                await window.DOMUtils.showMessage("Error loading captures", {
                    variant: "danger",
                    placement: "replace",
                    target: currentCapturesList,
                    presentation: "table",
                    templateContext: { colspan: 4 },
                })
            }

            if (currentCapturesCount) {
                currentCapturesCount.textContent = captures.length
            }

            // Re-attach event listeners for remove buttons
            this.addRemoveButtonListeners()
        } else {
            currentCapturesList.innerHTML =
                '<tr><td colspan="4" class="text-center text-muted">No captures in dataset</td></tr>'
            if (currentCapturesCount) {
                currentCapturesCount.textContent = "0"
            }
        }
    }

    /**
     * Populate current files list
     * @param {Array} files - Files data
     */
    async populateCurrentFilesList(files) {
        // Use the existing selected-files-table from file_browser.html
        const selectedFilesTable = document.getElementById(
            "selected-files-table",
        )
        const selectedFilesBody = selectedFilesTable?.querySelector("tbody")
        const selectedFilesDisplay = document.getElementById(
            "selected-files-display",
        )

        if (!selectedFilesBody) return

        if (files && files.length > 0) {
            // Normalize for generic table_rows template
            const rows = files.map((file) => {
                this.currentFiles.set(file.id, file)

                // Permission logic: co-owners can remove anyone's files, contributors can only remove their own
                const isOwnedByCurrentUser =
                    file.owner_id === this.currentUserId
                const canRemoveThisFile =
                    this.permissions.canRemoveAnyAssets() ||
                    (this.permissions.canRemoveAsset(file) &&
                        isOwnedByCurrentUser)

                return {
                    css_class: !canRemoveThisFile ? "readonly-row" : "",
                    data_attrs: { "file-id": file.id },
                    cells: [
                        { kind: "text", value: file.name },
                        { kind: "text", value: file.media_type },
                        { kind: "text", value: file.relative_path },
                        { kind: "text", value: file.size },
                        {
                            kind: "text",
                            value:
                                file.owner?.name ||
                                file.owner?.email ||
                                "Unknown",
                        },
                    ],
                    actions: canRemoveThisFile
                        ? [
                              {
                                  label: "Remove",
                                  css_class: "btn-danger",
                                  extra_class: "mark-for-removal-btn",
                                  data_attrs: {
                                      "file-id": file.id,
                                      "file-type": "file",
                                  },
                              },
                          ]
                        : [{ html: '<span class="text-muted">N/A</span>' }],
                }
            })

            // Render using DOMUtils
            const success = await window.DOMUtils.renderTable(
                selectedFilesBody,
                rows,
                {
                    empty_message: "No files in dataset",
                    empty_colspan: 6,
                },
            )

            if (!success) {
                await window.DOMUtils.showMessage("Error loading files", {
                    variant: "danger",
                    placement: "replace",
                    target: selectedFilesBody,
                    presentation: "table",
                    templateContext: { colspan: 6 },
                })
            }

            // Update the display input
            if (selectedFilesDisplay) {
                selectedFilesDisplay.value = `${files.length} file(s) selected`
            }

            // Re-attach event listeners for remove buttons
            this.addRemoveButtonListeners()
        } else {
            selectedFilesBody.innerHTML =
                '<tr><td colspan="6" class="text-center text-muted">No files in dataset</td></tr>'
            if (selectedFilesDisplay) {
                selectedFilesDisplay.value = "0 file(s) selected"
            }
        }
    }

    /**
     * Load current assets from API
     */
    async loadCurrentAssets() {
        if (!this.datasetUuid) return

        try {
            const data = await window.APIClient.get(
                `/users/dataset-details/?dataset_uuid=${this.datasetUuid}`,
            )
            this.populateFromInitialData(data.captures || [], data.files || [])
        } catch (error) {
            console.error("Error loading current assets:", error)
        }
    }

    /**
     * Add remove button listeners
     */
    addRemoveButtonListeners() {
        const removeButtons = document.querySelectorAll(".mark-for-removal-btn")
        for (const button of removeButtons) {
            button.addEventListener("click", (e) => {
                e.preventDefault()
                const captureId = button.dataset.captureId
                const fileId = button.dataset.fileId
                if (captureId) {
                    this.markCaptureForRemoval(captureId)
                } else if (fileId) {
                    this.markFileForRemoval(fileId)
                }
            })
        }
    }

    /**
     * Sync strikethrough / checkbox on the capture search results row (step 2).
     * @param {string} captureId
     * @param {boolean} markedForRemoval
     */
    syncCaptureSearchRowRemovalStyle(captureId, markedForRemoval) {
        const searchRow = document.querySelector(
            `#captures-table-body tr[data-capture-id="${captureId}"]`,
        )
        if (!searchRow) return

        if (markedForRemoval) {
            searchRow.classList.add("marked-for-removal")
            const checkbox = searchRow.querySelector('input[type="checkbox"]')
            if (checkbox) {
                checkbox.checked = true
            }
            return
        }

        searchRow.classList.remove("marked-for-removal")
        const checkbox = searchRow.querySelector('input[type="checkbox"]')
        if (checkbox) {
            const idStr = captureId.toString()
            checkbox.checked =
                this.currentCaptures.has(captureId) ||
                this.currentCaptures.has(idStr) ||
                this.selectedCaptures.has(idStr)
        }
    }

    /**
     * Sync strikethrough / checkbox on a file-tree row (modal browser).
     * @param {string} fileId
     * @param {boolean} markedForRemoval
     */
    syncFileSearchRowRemovalStyle(fileId, markedForRemoval) {
        const id = String(fileId)
        const searchRow = document.querySelector(
            `#file-tree-root li[data-file-id="${id}"]`,
        )
        if (!searchRow) {
            return
        }

        if (markedForRemoval) {
            searchRow.classList.add("marked-for-removal")
            const checkbox = searchRow.querySelector('input[type="checkbox"]')
            if (checkbox) {
                checkbox.checked = true
            }
            return
        }

        searchRow.classList.remove("marked-for-removal")
        const checkbox = searchRow.querySelector('input[type="checkbox"]')
        if (checkbox) {
            checkbox.checked = false
        }
    }

    /**
     * Re-apply pending removal styling after the file tree is rebuilt.
     */
    syncAllPendingFileRemovalStylesInTree() {
        for (const [fileId, change] of this.pendingFiles.entries()) {
            if (change.action === "remove") {
                this.syncFileSearchRowRemovalStyle(fileId, true)
            }
        }
    }

    /**
     * Mark capture for removal
     * @param {string} captureId - Capture ID to mark for removal
     */
    markCaptureForRemoval(captureId) {
        const capture =
            this.currentCaptures.get(captureId) ||
            this.capturesSearchHandler?.selectedCaptureDetails.get(captureId)
        if (!capture) return

        // Check if user has permission to remove this specific capture
        const isOwnedByCurrentUser = capture.owner_id === this.currentUserId
        const canRemoveThisCapture =
            this.permissions.canRemoveAnyAssets() ||
            (this.permissions.canRemoveAsset(capture) && isOwnedByCurrentUser)

        if (!canRemoveThisCapture) {
            console.warn(
                `User does not have permission to remove capture ${captureId}`,
            )
            return
        }

        // Add to pending removals
        this.pendingCaptures.set(captureId, {
            action: "remove",
            data: capture,
        })

        // Update visual state of current captures list
        this.updateCurrentCapturesList()

        this.syncCaptureSearchRowRemovalStyle(captureId, true)

        this.updatePendingCapturesList()

        // Update review display
        if (window.updateReviewDatasetDisplay) {
            window.updateReviewDatasetDisplay()
        }
    }

    /**
     * @param {string} fileId
     * @returns {Object|undefined}
     */
    getCurrentFile(fileId) {
        const id = String(fileId)
        return this.currentFiles.get(fileId) ?? this.currentFiles.get(id)
    }

    /**
     * @param {string} fileId
     * @returns {{ action: string, data: Object }|undefined}
     */
    getPendingFileChange(fileId) {
        const id = String(fileId)
        return this.pendingFiles.get(fileId) ?? this.pendingFiles.get(id)
    }

    /**
     * Mark file for removal
     * @param {string} fileId - File ID to mark for removal
     */
    markFileForRemoval(fileId) {
        const id = String(fileId)
        const file = this.getCurrentFile(id)

        if (!file) {
            console.warn(`File ${fileId} not found for removal`)
            return
        }

        // Check if user has permission to remove this specific file
        const isOwnedByCurrentUser = file.owner_id === this.currentUserId
        const canRemoveThisFile =
            this.permissions.canRemoveAnyAssets() ||
            (this.permissions.canRemoveAsset(file) && isOwnedByCurrentUser)

        if (!canRemoveThisFile) {
            console.warn(
                `User does not have permission to remove file ${fileId}`,
            )
            return
        }

        this.pendingFiles.set(id, {
            action: "remove",
            data: file,
        })

        this.updateCurrentFilesList()

        this.syncFileSearchRowRemovalStyle(id, true)

        void this.updatePendingFilesList()
        this.filesSearchHandler?.syncCommittedFileSelectionUI?.()

        if (window.updateReviewDatasetDisplay) {
            window.updateReviewDatasetDisplay()
        }
    }

    /**
     * Add capture to pending additions
     * @param {string} captureId - Capture ID
     * @param {Object} captureData - Capture data
     */
    addCaptureToPending(captureId, captureData) {
        // Check if already in current captures
        if (this.currentCaptures.has(captureId)) {
            return // Already in dataset
        }

        // Check if already in pending additions
        if (
            this.pendingCaptures.has(captureId) &&
            this.pendingCaptures.get(captureId).action === "add"
        ) {
            return // Already marked for addition
        }

        // Add to pending additions
        this.pendingCaptures.set(captureId, {
            action: "add",
            data: captureData,
        })

        // Also add to selectedCaptures set so it shows as checked in search results
        this.selectedCaptures.add(captureId.toString())

        this.updatePendingCapturesList()

        // Update review display
        if (window.updateReviewDatasetDisplay) {
            window.updateReviewDatasetDisplay()
        }
    }

    /**
     * Add file to pending additions
     * @param {string} fileId - File ID
     * @param {Object} fileData - File data
     * @param {{ refreshUi?: boolean }} [options]
     */
    addFileToPending(fileId, fileData, options = {}) {
        const { refreshUi = true } = options
        const id = String(fileId)
        if (this.getCurrentFile(id)) {
            return
        }

        const pending = this.getPendingFileChange(id)
        if (pending?.action === "add") {
            return
        }

        this.pendingFiles.set(id, {
            action: "add",
            data: fileData,
        })

        if (!refreshUi) {
            return
        }

        void this.updatePendingFilesList()
        this.filesSearchHandler?.syncCommittedFileSelectionUI?.()

        if (window.updateReviewDatasetDisplay) {
            window.updateReviewDatasetDisplay()
        }
    }

    /**
     * Update pending captures list
     */
    async updatePendingCapturesList() {
        const pendingList = document.getElementById("pending-captures-list")
        const pendingCount = document.querySelector(".pending-changes-count")
        if (!pendingList) return

        await window.DatasetPendingChanges.renderPendingTable(this, {
            listElement: pendingList,
            countElement: pendingCount,
            entries: Array.from(this.pendingCaptures.entries()),
            valueKey: "type",
            entityAttr: "capture",
            emptyMessage: "No pending capture changes",
        })
    }

    /**
     * Update pending files list
     */
    async updatePendingFilesList() {
        const pendingList = document.getElementById("pending-files-list")
        const pendingCount = document.querySelector(
            ".pending-files-changes-count",
        )
        if (!pendingList) return

        await window.DatasetPendingChanges.renderPendingTable(this, {
            listElement: pendingList,
            countElement: pendingCount,
            entries: Array.from(this.pendingFiles.entries()),
            valueKey: "name",
            entityAttr: "file",
            emptyMessage: "No pending file changes",
        })
    }

    /**
     * Add cancel button listeners
     */
    addCancelButtonListeners() {
        const cancelButtons = document.querySelectorAll(".cancel-change")
        for (const button of cancelButtons) {
            button.addEventListener("click", (e) => {
                e.preventDefault()
                const captureId = button.dataset.captureId
                const fileId = button.dataset.fileId
                const changeType = button.dataset.changeType

                if (changeType === "capture" && captureId) {
                    this.cancelCaptureChange(captureId)
                } else if (changeType === "file" && fileId) {
                    this.cancelFileChange(fileId)
                }
            })
        }
    }

    /**
     * Cancel capture change
     * @param {string} captureId - Capture ID
     */
    cancelCaptureChange(captureId) {
        const change = this.pendingCaptures.get(captureId)
        if (!change) return

        this.pendingCaptures.delete(captureId)

        if (change.action === "remove") {
            this.updateCurrentCapturesList()
            this.syncCaptureSearchRowRemovalStyle(captureId, false)
        } else if (change.action === "add") {
            this.selectedCaptures.delete(captureId.toString())
            this.syncCaptureSearchRowRemovalStyle(captureId, false)
        }

        this.updatePendingCapturesList()

        // Update review display
        if (window.updateReviewDatasetDisplay) {
            window.updateReviewDatasetDisplay()
        }
    }

    /**
     * Cancel file change
     * @param {string} fileId - File ID
     */
    cancelFileChange(fileId) {
        const id = String(fileId)
        const change = this.getPendingFileChange(id)
        if (!change) return

        this.pendingFiles.delete(id)
        for (const key of [fileId, id]) {
            if (key !== id) {
                this.pendingFiles.delete(key)
            }
        }

        if (change.action === "remove") {
            this.updateCurrentFilesList()
            this.syncFileSearchRowRemovalStyle(id, false)
        } else if (change.action === "add") {
            this.filesSearchHandler?.deleteModalSelectedFile?.(fileId)
            this.filesSearchHandler?.syncFileCheckboxVisual?.(fileId, false)
        }

        this.updatePendingFilesList()
        this.filesSearchHandler?.syncCommittedFileSelectionUI?.()

        if (window.updateReviewDatasetDisplay) {
            window.updateReviewDatasetDisplay()
        }
    }

    /**
     * Get pending changes
     * @returns {Object} Pending changes object
     */
    getPendingChanges() {
        return {
            captures: Array.from(this.pendingCaptures.entries()),
            files: Array.from(this.pendingFiles.entries()),
        }
    }

    /**
     * Check if there are any pending changes
     * @returns {boolean} Whether there are pending changes
     */
    hasChanges() {
        return this.pendingCaptures.size > 0 || this.pendingFiles.size > 0
    }

    /**
     * Handle file removal (override for edit mode)
     * @param {string} fileId - File ID to remove
     */
    handleFileRemoval(fileId) {
        // In edit mode: mark for removal instead of actually removing
        this.markFileForRemoval(fileId)
    }

    /**
     * Handle capture removal (override for edit mode)
     * @param {string} captureId - Capture ID to remove
     */
    handleCaptureRemoval(captureId) {
        // In edit mode: mark for removal instead of actually removing
        this.markCaptureForRemoval(captureId)
    }

    /**
     * Remove all current dataset files the user may mark for removal (edit mode).
     */
    removeAllFileSelections() {
        let removedCount = 0
        for (const [fileId, file] of this.currentFiles.entries()) {
            if (this.permissions.canRemoveAsset(file)) {
                this.markFileForRemoval(fileId)
                removedCount++
            }
        }

        if (removedCount > 0) {
            const removeAllFilesButton = document.getElementById(
                "remove-all-selected-files-button",
            )
            if (removeAllFilesButton) {
                removeAllFilesButton.disabled = true
                removeAllFilesButton.classList.add("disabled-element")
            }
        }
    }

    /**
     * Update current files list visual state
     * This method only updates the visual state of existing files (e.g., marking for removal)
     * It does NOT add new files - those should only appear in pending changes
     */
    updateCurrentFilesList() {
        const selectedFilesTable = document.getElementById(
            "selected-files-table",
        )
        const selectedFilesBody = selectedFilesTable?.querySelector("tbody")
        if (!selectedFilesBody) return

        // Update visual state of existing rows based on pending changes
        const rows = selectedFilesBody.querySelectorAll("tr[data-file-id]")
        for (const row of rows) {
            const fileId = row.dataset.fileId
            const pendingChange = this.getPendingFileChange(fileId)

            if (pendingChange && pendingChange.action === "remove") {
                // Mark as pending removal
                row.classList.add("marked-for-removal")
                const removeButton = row.querySelector(".mark-for-removal-btn")
                if (removeButton) {
                    removeButton.disabled = true
                    removeButton.classList.add("disabled-element")
                }
            } else {
                // Restore normal state
                row.classList.remove("marked-for-removal")
                const removeButton = row.querySelector(".mark-for-removal-btn")
                if (removeButton) {
                    removeButton.disabled = false
                    removeButton.classList.remove("disabled-element")
                }
            }
        }
    }

    /**
     * Update current captures list visual state
     * This method only updates the visual state of existing captures (e.g., marking for removal)
     * It does NOT add new captures - those should only appear in pending changes
     */
    updateCurrentCapturesList() {
        const currentCapturesList = document.getElementById(
            "current-captures-list",
        )
        if (!currentCapturesList) return

        // Update visual state of existing rows based on pending changes
        const rows = currentCapturesList.querySelectorAll("tr[data-capture-id]")
        for (const row of rows) {
            const captureId = row.dataset.captureId
            const pendingChange = this.pendingCaptures.get(captureId)

            if (pendingChange && pendingChange.action === "remove") {
                // Mark as pending removal
                row.classList.add("marked-for-removal")
                const removeButton = row.querySelector(".mark-for-removal-btn")
                if (removeButton) {
                    removeButton.disabled = true
                    removeButton.classList.add("disabled-element")
                }
            } else {
                // Restore normal state
                row.classList.remove("marked-for-removal")
                const removeButton = row.querySelector(".mark-for-removal-btn")
                if (removeButton) {
                    removeButton.disabled = false
                    removeButton.classList.remove("disabled-element")
                }
            }
        }
    }

    /**
     * Update hidden fields (no-op for editing mode)
     */
    updateHiddenFields() {
        // This method is called by SearchHandler but not needed for editing mode
        // We'll implement it as a no-op since editing mode doesn't use hidden fields
    }

    /**
     * Handle form submission for edit mode
     * @param {Event} e - Submit event
     */
    handleSubmit(e) {
        e.preventDefault()

        // Collect form data
        const formData = new FormData(document.getElementById("datasetForm"))

        // Add pending changes to form data
        const pendingChanges = this.getPendingChanges()

        // Add pending captures
        const capturesAdd = []
        const capturesRemove = []
        for (const [id, change] of pendingChanges.captures) {
            if (change.action === "add") {
                capturesAdd.push(id)
            } else if (change.action === "remove") {
                capturesRemove.push(id)
            }
        }

        // Add pending files
        const filesAdd = []
        const filesRemove = []
        for (const [id, change] of pendingChanges.files) {
            if (change.action === "add") {
                filesAdd.push(id)
            } else if (change.action === "remove") {
                filesRemove.push(id)
            }
        }

        // Add comma-separated lists to form data
        if (capturesAdd.length > 0) {
            formData.append("captures_add", capturesAdd.join(","))
        }
        if (capturesRemove.length > 0) {
            formData.append("captures_remove", capturesRemove.join(","))
        }
        if (filesAdd.length > 0) {
            formData.append("files_add", filesAdd.join(","))
        }
        if (filesRemove.length > 0) {
            formData.append("files_remove", filesRemove.join(","))
        }

        // Add author changes if they exist
        if (
            this.authorChanges &&
            (this.authorChanges.added.length > 0 ||
                this.authorChanges.removed.length > 0 ||
                Object.keys(this.authorChanges.modified).length > 0)
        ) {
            formData.append(
                "author_changes",
                JSON.stringify(this.authorChanges),
            )
        }

        // Submit the form
        this.submitForm(formData)
    }

    /**
     * Submit the form with pending changes
     * @param {FormData} formData - Form data to submit
     */
    async submitForm(formData) {
        try {
            // Show loading state
            const submitBtn = document.getElementById("submitForm")
            if (submitBtn) {
                submitBtn.disabled = true
                submitBtn.innerHTML =
                    '<span class="spinner-border spinner-border-sm me-2"></span>Updating...'
            }

            // Submit form
            const response = await fetch(window.location.href, {
                method: "POST",
                body: formData,
                headers: {
                    "X-CSRFToken": document.querySelector(
                        "[name=csrfmiddlewaretoken]",
                    ).value,
                },
            })

            if (response.ok) {
                // Success - redirect or show success message
                const result = await response.json()
                if (result.success) {
                    // Redirect to dataset list or show success message
                    window.location.href =
                        result.redirect_url || "/users/dataset-list/"
                } else {
                    // Show error message
                    this.showToast(
                        result.message ||
                            "An error occurred while updating the dataset.",
                        "error",
                    )
                }
            } else {
                // Handle error response
                this.showToast(
                    "An error occurred while updating the dataset.",
                    "error",
                )
            }
        } catch (error) {
            console.error("Error submitting form:", error)
            this.showToast(
                "An error occurred while updating the dataset.",
                "error",
            )
        } finally {
            // Restore submit button
            const submitBtn = document.getElementById("submitForm")
            if (submitBtn) {
                submitBtn.disabled = false
                submitBtn.innerHTML = "Update Dataset"
            }
        }
    }

    /**
     * Initialize authors management for edit mode
     */
    initializeAuthorsManagement() {
        window.DatasetAuthorsUI?.mount(this, {
            mode: "edit",
            initialAuthors: this.initialAuthors,
        })
    }

    /**
     * Update dataset authors with pending changes (for review display)
     */
    async updateDatasetAuthors(authorsField) {
        const authorsElement = document.querySelector(".dataset-authors")
        if (!authorsElement) return

        if (!authorsField) {
            // In contributor view, there's no editable authors field, so show original authors
            const originalAuthors =
                window.datasetModeManager?.originalDatasetData?.authors || []
            const originalAuthorNames = this.formatAuthors(originalAuthors)
            authorsElement.textContent = originalAuthorNames
            return
        }

        try {
            // Get current authors with DOM-based stable IDs
            const currentAuthorsWithIds = this.getCurrentAuthorsWithDOMIds()
            // Get original authors from DatasetModeManager's captured data
            const originalAuthors =
                window.datasetModeManager?.originalDatasetData?.authors || []

            // Format original authors for display
            const originalAuthorNames = this.formatAuthors(originalAuthors)

            // Always show original value
            authorsElement.innerHTML = `<span class="current-value">${originalAuthorNames}</span>`

            // Calculate changes using DOM-based IDs
            const changes = this.calculateAuthorChanges(
                originalAuthors,
                currentAuthorsWithIds,
            )

            // If there are changes, request server-side rendering
            if (changes.length > 0) {
                try {
                    // Normalize for generic change_list template
                    const normalizedChanges = changes.map((change) => {
                        if (change.type === "add") {
                            return {
                                type: "add",
                                parts: [
                                    { text: "Add: " },
                                    {
                                        text: change.name,
                                        css_class: "text-success",
                                    },
                                ],
                            }
                        }
                        if (change.type === "remove") {
                            return {
                                type: "remove",
                                parts: [
                                    { text: "Remove: " },
                                    {
                                        text: change.name,
                                        css_class: "text-danger",
                                    },
                                ],
                            }
                        }
                        if (change.type === "change") {
                            // Handle name changes
                            if (
                                change.oldName !== undefined &&
                                change.newName !== undefined
                            ) {
                                return {
                                    type: "change",
                                    parts: [
                                        { text: 'Change Name: "' },
                                        { text: change.oldName },
                                        { text: '" → ' },
                                        {
                                            text: `"${change.newName}"`,
                                            css_class: "text-warning",
                                        },
                                    ],
                                }
                            }
                            // Handle ORCID changes
                            if (
                                change.oldOrcid !== undefined &&
                                change.newOrcid !== undefined
                            ) {
                                const oldOrcidDisplay = change.oldOrcid || ""
                                const newOrcidDisplay = change.newOrcid || ""
                                return {
                                    type: "change",
                                    parts: [
                                        { text: 'Change ORCID ID: "' },
                                        { text: oldOrcidDisplay },
                                        { text: '" → ' },
                                        {
                                            text: `"${newOrcidDisplay}"`,
                                            css_class: "text-warning",
                                        },
                                    ],
                                }
                            }
                        }
                        return change
                    })

                    // Request server to render using generic change_list
                    const response = await window.APIClient.post(
                        "/users/render-html/",
                        {
                            template: "users/components/change_list.html",
                            context: { changes: normalizedChanges },
                        },
                        null,
                        true,
                    ) // true = send as JSON

                    // Insert the server-rendered HTML
                    if (response.html) {
                        authorsElement.insertAdjacentHTML(
                            "beforeend",
                            response.html,
                        )
                    }
                } catch (error) {
                    console.error("Error rendering author changes:", error)
                    // Fallback: show error message
                    authorsElement.insertAdjacentHTML(
                        "beforeend",
                        '<div class="text-danger mt-2"><small>Error loading changes</small></div>',
                    )
                }
            }
        } catch (e) {
            console.error("Error in updateDatasetAuthors:", e)
            authorsElement.innerHTML =
                '<span class="current-value">Error parsing authors.</span>'
        }
    }

    /**
     * Get current authors with DOM-based stable IDs
     */
    getCurrentAuthorsWithDOMIds() {
        return window.AuthorsManager.getCurrentAuthorsWithDOMIds()
    }

    /**
     * Capture authors with DOM-based stable IDs
     */
    captureAuthorsWithDOMIds(authors) {
        const authorsList = document.querySelector(".authors-list")
        const authorsWithIds = []

        if (authorsList) {
            // Get author items from DOM
            const authorItems = authorsList.querySelectorAll(".author-item")

            for (const [index, authorItem] of authorItems.entries()) {
                // Get or create a stable ID for this author item
                const authorId = authorItem.id
                if (!authorId) {
                    console.error("❌ Author item missing ID")
                    return
                }

                // Get the author data (either from the authors array or from DOM inputs)
                let authorData
                if (authors[index]) {
                    authorData =
                        typeof authors[index] === "string"
                            ? { name: authors[index], orcid_id: "" }
                            : { ...authors[index] }
                } else {
                    // Fallback to DOM inputs if author data is missing
                    const nameInput =
                        authorItem.querySelector(".author-name-input")
                    const orcidInput = authorItem.querySelector(
                        ".author-orcid-input",
                    )
                    authorData = {
                        name: nameInput?.value || "",
                        orcid_id: orcidInput?.value || "",
                    }
                }

                // Add the stable ID
                authorData._stableId = authorId
                authorsWithIds.push(authorData)
            }
        }

        return authorsWithIds
    }

    /**
     * Format authors array into display string
     */
    formatAuthors(authors) {
        return window.AuthorsManager.formatAuthors(authors)
    }

    /**
     * Calculate author changes between original and current
     */
    calculateAuthorChanges(originalAuthors, currentAuthors) {
        const changes = []

        // Create maps using stable IDs
        const originalMap = new Map()
        const currentMap = new Map()

        for (const author of originalAuthors) {
            if (author._stableId) {
                originalMap.set(author._stableId, author)
            }
        }

        for (const author of currentAuthors) {
            if (author._stableId) {
                currentMap.set(author._stableId, author)
            }
        }

        // Find additions (in current but not in original)
        for (const [id, author] of currentMap) {
            if (!originalMap.has(id)) {
                const name = author.name || "Unknown"
                changes.push({ type: "add", name })
            }
        }

        // Find removals (in original but not in current)
        for (const [id, author] of originalMap) {
            if (!currentMap.has(id)) {
                const name = author.name || "Unknown"
                changes.push({ type: "remove", name })
            }
        }

        // Find changes (same ID but different content)
        for (const [id, currentAuthor] of currentMap) {
            const originalAuthor = originalMap.get(id)
            if (originalAuthor) {
                const currentName = currentAuthor.name || "Unknown"
                const originalName = originalAuthor.name || "Unknown"

                const currentOrcid = currentAuthor.orcid_id || ""
                const originalOrcid = originalAuthor.orcid_id || ""

                if (currentName !== originalName) {
                    changes.push({
                        type: "change",
                        oldName: originalName,
                        newName: currentName,
                    })
                }
                if (currentOrcid !== originalOrcid) {
                    changes.push({
                        type: "change",
                        oldOrcid: originalOrcid,
                        newOrcid: currentOrcid,
                    })
                }
            }
        }

        return changes
    }
}

// Make class available globally
window.DatasetEditingHandler = DatasetEditingHandler

// Export for ES6 modules (Jest testing) - only if in module context
if (typeof module !== "undefined" && module.exports) {
    module.exports = { DatasetEditingHandler }
}
