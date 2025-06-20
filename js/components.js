document.addEventListener('DOMContentLoaded', function() {
    // File browser functionality with improved accessibility
    const fileBrowser = document.querySelector('.file-browser');
    if (!fileBrowser) return;

    const allSpans = fileBrowser.querySelectorAll('span[tabindex]');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const selectionInfo = document.getElementById('selectionInfo');
    const liveRegion = document.getElementById('aria-live-region');
    
    let selectedFiles = new Set();
    let selectedFolders = new Set();
    let allItemsSelected = false;
    let currentActionTarget = null;
    
    // File metadata for demo
    const fileMetadata = {
        'data_file_1.csv': { name: 'data_file_1.csv', type: 'CSV File', size: '2.3 MB', created: '2024-01-15 10:30:00', modified: '2024-01-15 14:45:00' },
        'data_file_2.csv': { name: 'data_file_2.csv', type: 'CSV File', size: '1.8 MB', created: '2024-01-16 09:15:00', modified: '2024-01-16 11:20:00' },
        'metadata.json': { name: 'metadata.json', type: 'JSON File', size: '45 KB', created: '2024-01-15 10:30:00', modified: '2024-01-15 14:45:00' },
        'capture_2024-05-01.bin': { name: 'capture_2024-05-01.bin', type: 'Binary Capture File', size: '45.2 MB', created: '2024-05-01 08:00:00', modified: '2024-05-01 08:00:00' },
        'capture_2024-05-02.bin': { name: 'capture_2024-05-02.bin', type: 'Binary Capture File', size: '52.1 MB', created: '2024-05-02 08:00:00', modified: '2024-05-02 08:00:00' },
        'spectrum_analysis.pdf': { name: 'spectrum_analysis.pdf', type: 'PDF Document', size: '3.2 MB', created: '2024-03-31 17:00:00', modified: '2024-03-31 17:00:00' },
        'noise_measurements.xlsx': { name: 'noise_measurements.xlsx', type: 'Excel Spreadsheet', size: '1.7 MB', created: '2024-04-15 14:20:00', modified: '2024-04-15 16:30:00' },
        'document.pdf': { name: 'document.pdf', type: 'PDF Document', size: '5.2 MB', created: '2024-01-10 16:00:00', modified: '2024-01-12 13:30:00' },
        'archive.zip': { name: 'archive.zip', type: 'ZIP Archive', size: '15.7 MB', created: '2024-01-25 13:20:00', modified: '2024-01-25 13:20:00' },
        'Q1_Report.pdf': { name: 'Q1_Report.pdf', type: 'PDF Document', size: '2.8 MB', created: '2024-03-31 17:00:00', modified: '2024-03-31 17:00:00' },
        'Q2_Report.pdf': { name: 'Q2_Report.pdf', type: 'PDF Document', size: '3.1 MB', created: '2024-06-30 17:00:00', modified: '2024-06-30 17:00:00' },
        'README.md': { name: 'README.md', type: 'Markdown File', size: '12 KB', created: '2024-01-01 09:00:00', modified: '2024-01-15 11:30:00' }
    };

    // Initialize modals
    const renameModal = new bootstrap.Modal(document.getElementById('renameModal'));
    const addSubfolderModal = new bootstrap.Modal(document.getElementById('addSubfolderModal'));
    const deleteModal = new bootstrap.Modal(document.getElementById('deleteModal'));
    const metadataModal = new bootstrap.Modal(document.getElementById('metadataModal'));

    function addButtonEventListeners(container) {
        const buttons = container.querySelectorAll('.action-btn');
        buttons.forEach(button => {
            button.addEventListener('click', function(event) {
                event.stopPropagation();
                event.preventDefault();
                
                const action = this.dataset.action;
                const targetSpan = this.closest('span');
                currentActionTarget = targetSpan;
                
                if (liveRegion) {
                    const itemName = targetSpan.dataset.name;
                    liveRegion.textContent = `${action} action triggered for ${itemName}`;
                }
                
                switch(action) {
                    case 'rename':
                        const currentName = targetSpan.dataset.name;
                        document.getElementById('newNameInput').value = currentName;
                        renameModal.show();
                        break;
                    case 'add-subfolder':
                        document.getElementById('subfolderNameInput').value = '';
                        addSubfolderModal.show();
                        break;
                    case 'delete':
                        deleteModal.show();
                        break;
                    case 'metadata':
                        const fileName = targetSpan.dataset.name;
                        const metadata = fileMetadata[fileName];
                        if (metadata) {
                            document.getElementById('metadataFileName').textContent = metadata.name;
                            document.getElementById('metadataFileType').textContent = metadata.type;
                            document.getElementById('metadataFileSize').textContent = metadata.size;
                            document.getElementById('metadataCreated').textContent = metadata.created;
                            document.getElementById('metadataModified').textContent = metadata.modified;
                            metadataModal.show();
                        }
                        break;
                }
            });
        });
    }

    addButtonEventListeners(document);

    function toggleFolder(li) {
        const span = li.querySelector('span');
        const isExpanded = span.getAttribute('aria-expanded') === 'true';
        const newExpanded = !isExpanded;
        
        span.setAttribute('aria-expanded', newExpanded);
        
        const icon = span.querySelector('.bi-folder-fill, .bi-folder2-open');
        if (icon) {
            if (newExpanded) {
                icon.className = 'bi bi-folder2-open';
            } else {
                icon.className = 'bi bi-folder-fill';
            }
        }
        
        if (liveRegion) {
            const folderName = span.dataset.name;
            liveRegion.textContent = `${folderName} folder ${newExpanded ? 'expanded' : 'collapsed'}`;
        }
    }

    allSpans.forEach(span => {
        span.addEventListener('keydown', function(event) {
            const currentLi = this.parentElement;
            const allVisibleSpans = Array.from(fileBrowser.querySelectorAll('span[tabindex]')).filter(s => s.offsetParent !== null);
            const currentIndex = allVisibleSpans.indexOf(this);

            switch(event.key) {
                case 'Enter':
                case ' ':
                    event.preventDefault();
                    if (this.dataset.type === 'folder') {
                        toggleFolder(currentLi);
                    }
                    break;
                case 'ArrowDown':
                    event.preventDefault();
                    if (currentIndex < allVisibleSpans.length - 1) {
                        const nextSpan = allVisibleSpans[currentIndex + 1];
                        this.setAttribute('tabindex', '-1');
                        nextSpan.setAttribute('tabindex', '0');
                        nextSpan.focus();
                    }
                    break;
                case 'ArrowUp':
                    event.preventDefault();
                    if (currentIndex > 0) {
                        const prevSpan = allVisibleSpans[currentIndex - 1];
                        this.setAttribute('tabindex', '-1');
                        prevSpan.setAttribute('tabindex', '0');
                        prevSpan.focus();
                    }
                    break;
                case 'ArrowRight':
                    event.preventDefault();
                    if (this.dataset.type === 'folder' && this.getAttribute('aria-expanded') === 'false') {
                        toggleFolder(currentLi);
                    }
                    break;
                case 'ArrowLeft':
                    event.preventDefault();
                    if (this.dataset.type === 'folder' && this.getAttribute('aria-expanded') === 'true') {
                        toggleFolder(currentLi);
                    }
                    break;
            }
        });
        
        span.addEventListener('click', function(event) {
            if (this.dataset.type === 'folder' && !event.target.closest('.action-btn, .file-checkbox, .folder-checkbox')) {
                toggleFolder(this.parentElement);
            }
        });
    });

    function updateSelectionInfo() {
        const selectedFileCount = selectedFiles.size;
        const selectedFolderCount = selectedFolders.size;
        const totalFiles = fileBrowser.querySelectorAll('.file-checkbox').length;
        const totalFolders = fileBrowser.querySelectorAll('.folder-checkbox').length;
        
        if (selectedFileCount === 0 && selectedFolderCount === 0) {
            selectionInfo.textContent = 'No items selected';
        } else if (selectedFileCount === totalFiles && selectedFolderCount === totalFolders) {
            selectionInfo.textContent = `All ${totalFiles + totalFolders} items selected`;
        } else {
            const totalSelected = selectedFileCount + selectedFolderCount;
            const totalItems = totalFiles + totalFolders;
            selectionInfo.textContent = `${totalSelected} of ${totalItems} items selected`;
        }
        
        allItemsSelected = selectedFileCount === totalFiles && selectedFolderCount === totalFolders && (totalFiles + totalFolders) > 0;
        const selectAllIcon = selectAllBtn.querySelector('i');
        
        if (allItemsSelected) {
            selectAllIcon.className = 'bi bi-check-square-fill';
            selectAllBtn.innerHTML = '<i class="bi bi-check-square-fill" aria-hidden="true"></i> Deselect All';
        } else {
            selectAllIcon.className = 'bi bi-square';
            selectAllBtn.innerHTML = '<i class="bi bi-square" aria-hidden="true"></i> Select All Files';
        }
    }

    function toggleFileSelection(filename, checked) {
        if (checked) {
            selectedFiles.add(filename);
        } else {
            selectedFiles.delete(filename);
        }
        updateSelectionInfo();
    }

    function toggleFolderSelection(foldername, checked) {
        const folderCheckbox = fileBrowser.querySelector(`.folder-checkbox[data-foldername="${foldername}"]`);
        const folderLi = folderCheckbox ? folderCheckbox.closest('li[role="treeitem"]') : null;
        if (checked) {
            selectedFolders.add(foldername);
            if (folderLi) {
                folderLi.querySelectorAll('.folder-checkbox').forEach(checkbox => {
                    checkbox.checked = true;
                    selectedFolders.add(checkbox.dataset.foldername);
                });
                folderLi.querySelectorAll('.file-checkbox').forEach(checkbox => {
                    checkbox.checked = true;
                    selectedFiles.add(checkbox.dataset.filename);
                });
            }
        } else {
            selectedFolders.delete(foldername);
            if (folderLi) {
                folderLi.querySelectorAll('.folder-checkbox').forEach(checkbox => {
                    checkbox.checked = false;
                    selectedFolders.delete(checkbox.dataset.foldername);
                });
                folderLi.querySelectorAll('.file-checkbox').forEach(checkbox => {
                    checkbox.checked = false;
                    selectedFiles.delete(checkbox.dataset.filename);
                });
            }
        }
        updateSelectionInfo();
    }

    function selectAllFiles() {
        const fileCheckboxes = fileBrowser.querySelectorAll('.file-checkbox');
        const folderCheckboxes = fileBrowser.querySelectorAll('.folder-checkbox');
        
        if (allItemsSelected) {
            fileCheckboxes.forEach(checkbox => { checkbox.checked = false; selectedFiles.delete(checkbox.dataset.filename); });
            folderCheckboxes.forEach(checkbox => { checkbox.checked = false; selectedFolders.delete(checkbox.dataset.foldername); });
        } else {
            fileCheckboxes.forEach(checkbox => { checkbox.checked = true; selectedFiles.add(checkbox.dataset.filename); });
            folderCheckboxes.forEach(checkbox => { checkbox.checked = true; selectedFolders.add(checkbox.dataset.foldername); });
        }
        updateSelectionInfo();
    }

    fileBrowser.addEventListener('change', function(event) {
        if (event.target.classList.contains('file-checkbox')) {
            toggleFileSelection(event.target.dataset.filename, event.target.checked);
        } else if (event.target.classList.contains('folder-checkbox')) {
            toggleFolderSelection(event.target.dataset.foldername, event.target.checked);
        }
    });

    selectAllBtn.addEventListener('click', selectAllFiles);

    if (allSpans.length > 0) {
        allSpans.forEach((span, index) => { span.setAttribute('tabindex', index === 0 ? '0' : '-1'); });
    }

    selectAllBtn.innerHTML = '<i class="bi bi-square" aria-hidden="true"></i> Select All Files';
    updateSelectionInfo();

    document.getElementById('renameConfirmBtn').addEventListener('click', function() {
        const newName = document.getElementById('newNameInput').value.trim();
        const targetSpan = currentActionTarget;
        const itemType = targetSpan.dataset.type;
        const itemName = targetSpan.dataset.name;
        
        if (newName && newName !== itemName) {
            const itemContent = targetSpan.querySelector('.item-content');
            const textNode = itemContent.childNodes[itemContent.childNodes.length - 1];
            textNode.textContent = ` ${newName}`;
            targetSpan.dataset.name = newName;
            
            if (itemType === 'file' && fileMetadata[itemName]) {
                fileMetadata[newName] = { ...fileMetadata[itemName], name: newName };
                delete fileMetadata[itemName];
            }
            if (liveRegion) { liveRegion.textContent = `${itemName} renamed to ${newName}`; }
        }
        renameModal.hide();
    });

    document.getElementById('addSubfolderConfirmBtn').addEventListener('click', function() {
        const folderName = document.getElementById('subfolderNameInput').value.trim();
        const targetSpan = currentActionTarget;
        
        if (folderName) {
            const parentLi = targetSpan.parentElement;
            let parentUl = parentLi.querySelector('ul[role="group"]');
            
            if (!parentUl) {
                parentUl = document.createElement('ul');
                parentUl.setAttribute('role', 'group');
                parentLi.appendChild(parentUl);
                toggleFolder(parentLi);
            }
            
            const newLi = document.createElement('li');
            newLi.setAttribute('role', 'treeitem');
            newLi.setAttribute('aria-expanded', 'false');
            newLi.innerHTML = `
                <span tabindex="-1" data-type="folder" data-name="${folderName}">
                    <div class="item-content">
                        <input type="checkbox" class="folder-checkbox" data-foldername="${folderName}" aria-label="Select ${folderName} folder">
                        <i class="bi bi-folder-fill" aria-hidden="true"></i> ${folderName}
                    </div>
                    <div class="action-buttons">
                        <button class="action-btn" title="Rename" data-action="rename" aria-label="Rename ${folderName}"><i class="bi bi-pencil" aria-hidden="true"></i></button>
                        <button class="action-btn" title="Add subfolder" data-action="add-subfolder" aria-label="Add subfolder to ${folderName}"><i class="bi bi-folder-plus" aria-hidden="true"></i></button>
                        <button class="action-btn delete" title="Delete" data-action="delete" aria-label="Delete ${folderName}"><i class="bi bi-trash" aria-hidden="true"></i></button>
                    </div>
                </span>`;
            parentUl.appendChild(newLi);
            
            addButtonEventListeners(newLi);
            
            if (liveRegion) { liveRegion.textContent = `New folder ${folderName} created`; }
        }
        addSubfolderModal.hide();
    });

    document.getElementById('deleteConfirmBtn').addEventListener('click', function() {
        const targetSpan = currentActionTarget;
        const itemType = targetSpan.dataset.type;
        const itemName = targetSpan.dataset.name;
        const parentLi = targetSpan.parentElement;
        
        if (itemType === 'file') {
            selectedFiles.delete(itemName);
        } else if (itemType === 'folder') {
            selectedFolders.delete(itemName);
            parentLi.querySelectorAll('.file-checkbox').forEach(checkbox => { selectedFiles.delete(checkbox.dataset.filename); });
        }
        updateSelectionInfo();
        parentLi.remove();
        if (itemType === 'file' && fileMetadata[itemName]) { delete fileMetadata[itemName]; }
        if (liveRegion) { liveRegion.textContent = `${itemName} deleted`; }
        
        deleteModal.hide();
    });
}); 