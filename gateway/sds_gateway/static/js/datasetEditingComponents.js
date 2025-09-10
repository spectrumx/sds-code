/* JavaScript for dataset editing with intermediate changes management */

class DatasetEditingHandler {
    constructor(config) {
        this.datasetUuid = config.datasetUuid;
        this.permissionLevel = config.permissionLevel;
        this.canEditMetadata = config.canEditMetadata;
        this.canAddAssets = config.canAddAssets;
        this.canRemoveAssets = config.canRemoveAssets;
        this.currentUserId = config.currentUserId;
        
        // Current assets in dataset
        this.currentCaptures = new Map();
        this.currentFiles = new Map();
        
        // Pending changes
        this.pendingCaptures = new Map(); // key: captureId, value: {action: 'add'|'remove', data: {...}}
        this.pendingFiles = new Map(); // key: fileId, value: {action: 'add'|'remove', data: {...}}
        
        // Search handlers
        this.capturesSearchHandler = null;
        this.filesSearchHandler = null;
        
        // Properties that SearchHandler expects from formHandler
        this.selectedCaptures = new Set();
        this.selectedFiles = new Set();
        
        // Store initial data for later use when search handlers are ready
        this.initialCaptures = config.initialCaptures || [];
        this.initialFiles = config.initialFiles || [];

        this.initializeEventListeners();
        
        // If no initial data, load from API
        if (!this.initialCaptures.length && !this.initialFiles.length) {
            this.loadCurrentAssets();
        }
    }
    
    initializeEventListeners() {
        // Initialize search handlers if they exist
        if (window.SearchHandler) {
            this.capturesSearchHandler = new window.SearchHandler({
                searchFormId: 'captures-search-form',
                searchButtonId: 'search-captures',
                clearButtonId: 'clear-captures-search',
                tableBodyId: 'captures-table-body',
                paginationContainerId: 'captures-pagination',
                type: 'captures',
                formHandler: this
            });
            
            this.filesSearchHandler = new window.SearchHandler({
                searchFormId: 'files-search-form',
                searchButtonId: 'search-files',
                clearButtonId: 'clear-files-search',
                tableBodyId: 'file-tree-table',
                paginationContainerId: 'files-pagination',
                type: 'files',
                formHandler: this
            });
            
            // Populate initial data now that handlers are ready
            this.populateFromInitialData(this.initialCaptures, this.initialFiles);
        }
    }
    
    // Add the missing setSearchHandler method that SearchHandler expects
    setSearchHandler(searchHandler, type) {
        if (type === "captures") {
            this.capturesSearchHandler = searchHandler;
            // Defer population until SearchHandler is fully ready
            Promise.resolve().then(() => {
                this.populateSearchHandlerWithInitialData();
            });
        } else if (type === "files") {
            this.filesSearchHandler = searchHandler;
            this.filesSearchHandler.updateSelectedFilesList();
        }
    }
    
    populateSearchHandlerWithInitialData() {
        // Populate the SearchHandler with initial captures if available
        if (this.capturesSearchHandler && 
            this.capturesSearchHandler.selectedCaptures && 
            this.capturesSearchHandler.selectedCaptureDetails &&
            this.initialCaptures && 
            this.initialCaptures.length > 0) {
            this.initialCaptures.forEach(capture => {
                this.capturesSearchHandler.selectedCaptures.add(capture.id.toString());
                this.capturesSearchHandler.selectedCaptureDetails.set(capture.id.toString(), capture);
            });
        }
        
        // Also populate the DatasetEditingHandler's selectedCaptures set
        // This is what the SearchHandler checks when rendering search results
        if (this.initialCaptures && this.initialCaptures.length > 0) {
            this.initialCaptures.forEach(capture => {
                this.selectedCaptures.add(capture.id.toString());
            });
        }
    }
    
    // Add the missing formatFileSize method that SearchHandler expects
    formatFileSize(bytes) {
        if (bytes === 0) return "0 Bytes";
        const k = 1024;
        const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
    }
    
    // Add the missing show/hide methods that SearchHandler expects
    show(container, showClass = "display-block") {
        container.classList.remove("display-none");
        container.classList.add(showClass);
    }
    
    hide(container, showClass = "display-block") {
        container.classList.remove(showClass);
        container.classList.add("display-none");
    }
    
    // Add the missing updateHiddenFields method that SearchHandler expects
    updateHiddenFields() {
        // This method is called by SearchHandler but not needed for editing mode
        // We'll implement it as a no-op since editing mode doesn't use hidden fields
    }
    
    // Override the SearchHandler's remove behavior for edit mode
    handleFileRemoval(fileId) {
        // Check if we're in edit mode (if we have a datasetUuid)
        if (this.datasetUuid) {
            // In edit mode: mark for removal instead of actually removing
            this.markFileForRemoval(fileId);
        } else {
            // In create mode: use the original behavior
            if (this.filesSearchHandler) {
                this.filesSearchHandler.selectedFiles.delete(fileId);
                this.filesSearchHandler.updateSelectedFilesList();
            }
        }
    }
    
    handleCaptureRemoval(captureId) {
        // Check if we're in edit mode (if we have a datasetUuid)
        if (this.datasetUuid) {
            // In edit mode: mark for removal instead of actually removing
            this.markCaptureForRemoval(captureId);
        } else {
            // In create mode: use the original behavior
            if (this.capturesSearchHandler) {
                this.selectedCaptures.delete(captureId);
                this.capturesSearchHandler.updateSelectedCapturesPane();
            }
        }
    }
    
    handleRemoveAllFiles() {
        // Check if we're in edit mode (if we have a datasetUuid)
        if (this.datasetUuid) {
            // In edit mode: mark all files for removal instead of actually removing them
            if (this.filesSearchHandler && this.filesSearchHandler.selectedFiles) {
                // Mark all current files for removal
                for (const [fileId, file] of this.filesSearchHandler.selectedFiles.entries()) {
                    this.markFileForRemoval(fileId);
                }
                // disable the remove all files button
                const removeAllFilesButton = document.querySelector('.remove-all-selected-files-button');
                if (removeAllFilesButton) {
                    removeAllFilesButton.disabled = true;
                    removeAllFilesButton.style.opacity = '0.5';
                }
            }
        } else {
            // In create mode: use the original behavior (handled by SearchHandler)
            // This should not be called in create mode, but just in case
            if (this.filesSearchHandler) {
                this.filesSearchHandler.selectedFiles.clear();
                this.filesSearchHandler.updateSelectedFilesList();

                // enable the remove all files button
                const removeAllFilesButton = document.querySelector('.remove-all-selected-files-button');
                if (removeAllFilesButton) {
                    removeAllFilesButton.disabled = false;
                    removeAllFilesButton.style.opacity = '1';
                }
            }
        }
    }
    
    populateFromInitialData(initialCaptures, initialFiles) {
        // Populate current captures in the side panel table
        this.currentCaptures.clear();
        const currentCapturesList = document.getElementById('current-captures-list');
        const currentCapturesCount = document.querySelector('.current-captures-count');
        const canRemove = this.canRemoveAssets;
        if (initialCaptures && initialCaptures.length > 0) {
            // Show all captures in the dataset, but only allow removal of user-owned ones
            currentCapturesList.innerHTML = initialCaptures.map(capture => {
                this.currentCaptures.set(capture.id, capture);
                const rowClass = !canRemove ? 'readonly-row' : '';
                
                return `
                    <tr data-capture-id="${capture.id}" class="current-capture-row ${rowClass}">
                        <td>${capture.type}</td>
                        <td>${capture.directory}</td>
                        <td>${capture.owner_name}</td>
                        ${canRemove ? `
                            <td>
                                <button class="btn btn-sm btn-danger mark-for-removal-btn" 
                                        data-capture-id="${capture.id}"
                                        data-capture-type="capture">
                                    Remove
                                </button>
                            </td>
                        ` : '<td><span class="text-muted">N/A</span></td>'}
                    </tr>
                `;
            }).join('');
            
            if (currentCapturesCount) {
                currentCapturesCount.textContent = initialCaptures.length;
            }
        } else {
            const colspan = canRemove ? 4 : 3;
            currentCapturesList.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-muted">No captures in dataset</td></tr>`;
            if (currentCapturesCount) {
                currentCapturesCount.textContent = '0';
            }
        }
        
        // Use the existing SearchHandler to populate captures in the main table
        // Note: SearchHandler might not be created yet, so we'll defer this until it's available
        if (this.capturesSearchHandler && this.capturesSearchHandler.selectedCaptures) {
            if (initialCaptures && initialCaptures.length > 0) {
                // Add existing captures to the selected captures map
                initialCaptures.forEach(capture => {
                    this.capturesSearchHandler.selectedCaptures.add(capture.id.toString());
                    this.capturesSearchHandler.selectedCaptureDetails.set(capture.id.toString(), capture);
                });
            }
        }
        
        // Also populate the DatasetEditingHandler's selectedCaptures set
        // This is what the SearchHandler checks when rendering search results
        if (initialCaptures && initialCaptures.length > 0) {
            initialCaptures.forEach(capture => {
                this.selectedCaptures.add(capture.id.toString());
            });
        }
        
        // Populate current files in the file browser table
        this.currentFiles.clear();
        if (initialFiles && initialFiles.length > 0) {
            initialFiles.forEach(file => {
                this.currentFiles.set(file.id, file);
            });
        }
        
        // Use the existing SearchHandler to populate files for the file browser
        if (this.filesSearchHandler) {
            if (initialFiles && initialFiles.length > 0) {
                // Add existing files to the selected files map
                initialFiles.forEach(file => {
                    this.filesSearchHandler.selectedFiles.set(file.id, file);
                });
            }
            
            // Always call updateSelectedFilesList to show the current state
            this.filesSearchHandler.updateSelectedFilesList();
        }
        
        // Add event listeners for remove buttons
        this.addRemoveButtonListeners();
    }
    
    async loadCurrentAssets() {
        if (!this.datasetUuid) return;
        
        try {
            const response = await fetch(`/users/dataset-details/?dataset_uuid=${this.datasetUuid}`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                this.populateFromInitialData(data.captures || [], data.files || []);
            }
        } catch (error) {
            console.error('Error loading current assets:', error);
        }
    }
    

    
    addRemoveButtonListeners() {
        const removeButtons = document.querySelectorAll('.mark-for-removal-btn');
        removeButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                const captureId = button.dataset.captureId;
                const fileId = button.dataset.fileId;
                
                if (captureId) {
                    this.markCaptureForRemoval(captureId);
                } else if (fileId) {
                    this.markFileForRemoval(fileId);
                }
            });
        });
    }
    
    markCaptureForRemoval(captureId) {
        // In edit mode, captures are stored in the SearchHandler's selectedCaptureDetails Map
        const capture = this.capturesSearchHandler?.selectedCaptureDetails.get(captureId);
        if (!capture) return;
        
        // Add to pending removals
        this.pendingCaptures.set(captureId, {
            action: 'remove',
            data: capture
        });
        
        // Visual feedback - grey out the row in the current captures table (edit mode)
        const row = document.querySelector(`#current-captures-list tr[data-capture-id="${captureId}"]`);
        if (row) {
            row.classList.add('marked-for-removal');
            
            // Disable the remove button
            const removeButton = row.querySelector('.mark-for-removal-btn');
            console.log('removeButton', removeButton);
            if (removeButton) {
                console.log('removeButton.disabled', removeButton.disabled);
                removeButton.disabled = true;
                console.log('removeButton.disabled', removeButton.disabled);
                removeButton.style.opacity = '0.5';
            }
        }
        
        // Also mark in the search results table if visible
        const searchRow = document.querySelector(`#captures-table-body tr[data-capture-id="${captureId}"]`);
        if (searchRow) {
            searchRow.classList.add('marked-for-removal');
            
            // Also check the checkbox if it exists
            const checkbox = searchRow.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = true;
            }
        }
        
        this.updatePendingCapturesList();
    }
    
    markFileForRemoval(fileId) {
        // In edit mode, files are stored in the SearchHandler's selectedFiles Map
        const file = this.filesSearchHandler?.selectedFiles.get(fileId);
        if (!file) return;
        
        // Add to pending removals
        this.pendingFiles.set(fileId, {
            action: 'remove',
            data: file
        });
        
        // Visual feedback - grey out the row in the selected files table
        const row = document.querySelector(`#selected-files-table tr[data-file-id="${fileId}"]`);
        if (row) {
            row.classList.add('marked-for-removal');
            row.style.opacity = '0.5';
            row.style.textDecoration = 'line-through';
            
            // Disable the remove button
            const removeButton = row.querySelector('.remove-selected-file');
            if (removeButton) {
                removeButton.disabled = true;
                removeButton.style.opacity = '0.5';
            }
        }
        
        // Also mark in the search results table if visible
        const searchRow = document.querySelector(`#file-tree-table tr[data-file-id="${fileId}"]`);
        if (searchRow) {
            searchRow.classList.add('marked-for-removal');
            
            // Also check the checkbox if it exists
            const checkbox = searchRow.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = true;
            }
        }
        
        this.updatePendingFilesList();
    }
    
    addCaptureToPending(captureId, captureData) {
        // Check if already in current captures
        if (this.currentCaptures.has(captureId)) {
            return; // Already in dataset
        }
        
        // Check if already in pending additions
        if (this.pendingCaptures.has(captureId) && this.pendingCaptures.get(captureId).action === 'add') {
            return; // Already marked for addition
        }
        
        // Add to pending additions
        this.pendingCaptures.set(captureId, {
            action: 'add',
            data: captureData
        });
        
        // Also add to selectedCaptures set so it shows as checked in search results
        this.selectedCaptures.add(captureId.toString());
        
        this.updatePendingCapturesList();
    }
    
    updateCurrentCapturesList() {
        const currentCapturesList = document.getElementById('current-captures-list');
        const currentCapturesCount = document.querySelector('.current-captures-count');
        const canRemove = this.canRemoveAssets;
        if (!currentCapturesList) return;
        
        // Get all selected captures that are owned by the current user
        const selectedCaptures = Array.from(this.capturesSearchHandler?.selectedCaptures || [])
            .map(id => this.capturesSearchHandler?.selectedCaptureDetails.get(id))
            .filter(capture => capture && capture.owner_id === this.currentUserId);
        
        if (selectedCaptures.length === 0) {
            const colspan = canRemove ? 4 : 3;
            currentCapturesList.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-muted">No captures selected</td></tr>`;
            if (currentCapturesCount) {
                currentCapturesCount.textContent = '0';
            }
            return;
        }
        
        currentCapturesList.innerHTML = selectedCaptures.map(capture => {    
            return `
                <tr data-capture-id="${capture.id}" class="current-capture-row">
                    <td>${capture.type}</td>
                    <td>${capture.directory}</td>
                    <td>${capture.owner_name || capture.owner?.name || 'Unknown'}</td>
                    ${canRemove ? `
                        <td>
                            <button class="btn btn-sm btn-danger mark-for-removal-btn" 
                                    data-capture-id="${capture.id}"
                                    data-capture-type="capture">
                                Remove
                            </button>
                        </td>
                    ` : '<td><span class="text-muted">N/A</span></td>'}
                </tr>
            `;
        }).join('');
        
        if (currentCapturesCount) {
            currentCapturesCount.textContent = selectedCaptures.length;
        }
        
        // Add event listeners for remove buttons
        this.addRemoveButtonListeners();
    }
    
    addFileToPending(fileId, fileData) {
        // Check if already in current files
        if (this.currentFiles.has(fileId)) {
            return; // Already in dataset
        }
        
        // Check if already in pending additions
        if (this.pendingFiles.has(fileId) && this.pendingFiles.get(fileId).action === 'add') {
            return; // Already marked for addition
        }
        
        // Add to pending additions
        this.pendingFiles.set(fileId, {
            action: 'add',
            data: fileData
        });
        
        this.updatePendingFilesList();
    }
    
    updatePendingCapturesList() {
        const pendingList = document.getElementById('pending-captures-list');
        const pendingCount = document.querySelector('.pending-changes-count');
        
        // Show both additions and removals
        const allChanges = Array.from(this.pendingCaptures.entries());
        
        if (allChanges.length === 0) {
            pendingList.innerHTML = '<tr><td colspan="3" class="text-center text-muted">No pending capture changes</td></tr>';
            if (pendingCount) {
                pendingCount.textContent = '0';
            }
            return;
        }
        
        pendingList.innerHTML = allChanges.map(([id, change]) => {
            const badgeClass = change.action === 'add' ? 'bg-success' : 'bg-danger';
            const badgeText = change.action === 'add' ? 'Add' : 'Remove';
            return `
                <tr>
                    <td><span class="badge ${badgeClass}">${badgeText}</span></td>
                    <td>${change.data.type}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary cancel-change" 
                                data-capture-id="${id}"
                                data-change-type="capture">
                            Cancel
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
        
        if (pendingCount) {
            pendingCount.textContent = allChanges.length;
        }
        
        // Add event listeners for cancel buttons
        this.addCancelButtonListeners();
    }
    
    updatePendingFilesList() {
        const pendingList = document.getElementById('pending-files-list');
        const pendingCount = document.querySelector('.pending-files-changes-count');
        
        // Show both additions and removals
        const allChanges = Array.from(this.pendingFiles.entries());
        
        if (allChanges.length === 0) {
            pendingList.innerHTML = '<tr><td colspan="3" class="text-center text-muted">No pending file changes</td></tr>';
            if (pendingCount) {
                pendingCount.textContent = '0';
            }
            return;
        }
        
        pendingList.innerHTML = allChanges.map(([id, change]) => {
            const badgeClass = change.action === 'add' ? 'bg-success' : 'bg-danger';
            const badgeText = change.action === 'add' ? 'Add' : 'Remove';
            return `
                <tr>
                    <td><span class="badge ${badgeClass}">${badgeText}</span></td>
                    <td>${change.data.name}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary cancel-change" 
                                data-file-id="${id}"
                                data-change-type="file">
                            Cancel
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
        
        if (pendingCount) {
            pendingCount.textContent = allChanges.length;
        }
        
        // Add event listeners for cancel buttons
        this.addCancelButtonListeners();
    }
    
    addCancelButtonListeners() {
        const cancelButtons = document.querySelectorAll('.cancel-change');
        cancelButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                const captureId = button.dataset.captureId;
                const fileId = button.dataset.fileId;
                const changeType = button.dataset.changeType;
                
                if (changeType === 'capture' && captureId) {
                    this.cancelCaptureChange(captureId);
                } else if (changeType === 'file' && fileId) {
                    this.cancelFileChange(fileId);
                }
            });
        });
    }
    
    cancelCaptureChange(captureId) {
        const change = this.pendingCaptures.get(captureId);
        if (!change) return;
        
        this.pendingCaptures.delete(captureId);
        
        if (change.action === 'remove') {
            // Restore visual state
            const row = document.querySelector(`#current-captures-list tr[data-capture-id="${captureId}"]`);
            if (row) {
                row.classList.remove('marked-for-removal');
                row.style.opacity = '';
                row.style.textDecoration = '';
                
                // Re-enable the remove button
                const removeButton = row.querySelector('.mark-for-removal-btn');
                if (removeButton) {
                    removeButton.disabled = false;
                    removeButton.style.opacity = '';
                }
            }
        } else if (change.action === 'add') {
            // Remove from selectedCaptures set so it shows as unchecked in search results
            this.selectedCaptures.delete(captureId.toString());
        }
        
        this.updatePendingCapturesList();
    }
    
    cancelFileChange(fileId) {
        const change = this.pendingFiles.get(fileId);
        if (!change) return;
        
        this.pendingFiles.delete(fileId);
        
        if (change.action === 'remove') {
            // Restore visual state
            const row = document.querySelector(`#selected-files-table tr[data-file-id="${fileId}"]`);
            if (row) {
                row.classList.remove('marked-for-removal');
                row.style.opacity = '';
                row.style.textDecoration = '';
                
                // Re-enable the remove button
                const removeButton = row.querySelector('.remove-selected-file');
                if (removeButton) {
                    removeButton.disabled = false;
                    removeButton.style.opacity = '';
                }
            }
        } else if (change.action === 'add') {
            // Remove from SearchHandler's selectedFiles if it exists
            if (this.filesSearchHandler) {
                this.filesSearchHandler.selectedFiles.delete(fileId);
            }
        }
        
        this.updatePendingFilesList();
    }
    
    getPendingChanges() {
        return {
            captures: Array.from(this.pendingCaptures.entries()),
            files: Array.from(this.pendingFiles.entries())
        };
    }
    
    hasChanges() {
        return this.pendingCaptures.size > 0 || this.pendingFiles.size > 0;
    }
}

// Make class available globally
window.DatasetEditingHandler = DatasetEditingHandler;
