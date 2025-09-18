# Actions Components Documentation

This document provides detailed information about the action-specific JavaScript components that handle sharing, downloading, and details functionality.

## Overview

The actions components provide specialized functionality for specific user actions:
- **ShareActionManager**: Handles all sharing-related functionality
- **DownloadActionManager**: Manages download operations
- **DetailsActionManager**: Handles details modal functionality

## ShareActionManager.js

### Purpose

Manages all sharing-related functionality including user/group search, selection, permission management, and sharing operations.

### Key Features

- **User/Group Search**: Real-time search with debouncing
- **Permission Management**: Dynamic permission level changes
- **Pending Changes**: Tracks permission changes and removals
- **Notification Support**: Email notifications for shared items
- **Modal Management**: Handles sharing modal lifecycle

### API Reference

#### Constructor

```javascript
const shareManager = new ShareActionManager({
    itemUuid: 'dataset-uuid',              // Item UUID to share
    itemType: 'dataset',                   // Item type ('dataset' or 'capture')
    permissions: permissionsManager        // Permissions manager instance
});
```

#### Properties

- `selectedUsersMap` (Object): Map of selected users by input ID
- `pendingRemovals` (Set): Users marked for removal
- `pendingPermissionChanges` (Map): Pending permission level changes
- `searchTimeout` (number): Search debounce timeout
- `currentRequest` (AbortController): Current search request

#### Methods

##### `handleShareItem()`
Handles the share item action.

**Returns:** `Promise<void>`

**Example:**
```javascript
await shareManager.handleShareItem();
```

##### `searchUsers(query, dropdown)`
Searches for users and groups.

**Parameters:**
- `query` (string): Search query
- `dropdown` (Element): Dropdown element to populate

**Returns:** `Promise<void>`

**Example:**
```javascript
await shareManager.searchUsers('john', dropdownElement);
```

##### `selectUser(item, input)`
Selects a user from search results.

**Parameters:**
- `item` (Element): Selected item element
- `input` (Element): Search input element

**Example:**
```javascript
shareManager.selectUser(selectedItem, searchInput);
```

##### `renderChips(input)`
Renders user chips for selected users.

**Parameters:**
- `input` (Element): Search input element

**Example:**
```javascript
shareManager.renderChips(searchInput);
```

##### `clearSelections()`
Clears all selections and pending changes.

**Example:**
```javascript
shareManager.clearSelections();
```

#### User Selection Structure

Selected users are stored in the following format:

```javascript
selectedUsersMap[inputId] = [
    {
        name: 'John Doe',
        email: 'john@example.com',
        type: 'user',
        permission_level: 'viewer'
    },
    {
        name: 'Test Group',
        email: 'group:group-uuid',
        type: 'group',
        member_count: 5,
        permission_level: 'contributor'
    }
];
```

#### Permission Levels

Supported permission levels:
- `viewer`: Can only view and download
- `contributor`: Can add their own assets and edit metadata
- `co-owner`: Can edit metadata, add/remove assets, and share

#### Usage Example

```javascript
// Initialize share manager
const shareManager = new ShareActionManager({
    itemUuid: 'dataset-uuid',
    itemType: 'dataset',
    permissions: permissionsManager
});

// Handle share button click
document.getElementById('share-dataset-btn').addEventListener('click', async () => {
    try {
        await shareManager.handleShareItem();
        showToast('Dataset shared successfully!', 'success');
    } catch (error) {
        showToast('Error sharing dataset', 'danger');
    }
});

// Handle user selection
document.addEventListener('click', (e) => {
    if (e.target.closest('.list-group-item')) {
        const item = e.target.closest('.list-group-item');
        const input = document.getElementById('user-search-input');
        shareManager.selectUser(item, input);
    }
});
```

## DownloadActionManager.js

### Purpose

Manages download functionality with permission checking, request handling, and status tracking.

### Key Features

- **Permission Checking**: Validates download permissions
- **Request Handling**: Manages download requests
- **Status Tracking**: Tracks download status
- **Error Handling**: Comprehensive error handling
- **Loading States**: UI loading state management

### API Reference

#### Constructor

```javascript
const downloadManager = new DownloadActionManager({
    permissions: permissionsManager        // Permissions manager instance
});
```

#### Methods

##### `handleDatasetDownload(datasetUuid, datasetName, button)`
Handles dataset download.

**Parameters:**
- `datasetUuid` (string): Dataset UUID
- `datasetName` (string): Dataset name
- `button` (Element): Download button element

**Returns:** `Promise<void>`

**Example:**
```javascript
await downloadManager.handleDatasetDownload('dataset-uuid', 'My Dataset', buttonElement);
```

##### `handleCaptureDownload(captureUuid, captureName, button)`
Handles capture download.

**Parameters:**
- `captureUuid` (string): Capture UUID
- `captureName` (string): Capture name
- `button` (Element): Download button element

**Returns:** `Promise<void>`

**Example:**
```javascript
await downloadManager.handleCaptureDownload('capture-uuid', 'My Capture', buttonElement);
```

##### `getDownloadStatus(itemUuid, itemType)`
Gets download status for an item.

**Parameters:**
- `itemUuid` (string): Item UUID
- `itemType` (string): Item type ('dataset' or 'capture')

**Returns:** `Promise<Object>` - Download status

**Example:**
```javascript
const status = await downloadManager.getDownloadStatus('dataset-uuid', 'dataset');
console.log('Download status:', status);
```

##### `cancelDownload(itemUuid, itemType)`
Cancels a download request.

**Parameters:**
- `itemUuid` (string): Item UUID
- `itemType` (string): Item type ('dataset' or 'capture')

**Returns:** `Promise<Object>` - Cancellation result

**Example:**
```javascript
const result = await downloadManager.cancelDownload('dataset-uuid', 'dataset');
```

##### `getDownloadHistory(options)`
Gets download history for the user.

**Parameters:**
- `options` (Object): Filtering options

**Returns:** `Promise<Array>` - Download history

**Example:**
```javascript
const history = await downloadManager.getDownloadHistory({
    limit: 10,
    status: 'completed'
});
```

##### `initializeDownloadButtonsForContainer(container)`
Initializes download buttons for dynamically loaded content.

**Parameters:**
- `container` (Element): Container element to search within

**Example:**
```javascript
downloadManager.initializeDownloadButtonsForContainer(document.getElementById('content'));
```

##### `canDownloadItem(item)`
Checks if user can download specific item.

**Parameters:**
- `item` (Object): Item object

**Returns:** `boolean` - Whether user can download

**Example:**
```javascript
const canDownload = downloadManager.canDownloadItem(datasetItem);
if (canDownload) {
    // Enable download button
}
```

#### Download Status Structure

Download status objects have the following structure:

```javascript
{
    status: 'pending' | 'processing' | 'completed' | 'failed',
    message: 'Status message',
    download_url: 'https://...', // Only present when completed
    created_at: '2023-01-01T00:00:00Z',
    completed_at: '2023-01-01T00:05:00Z' // Only present when completed
}
```

#### Usage Example

```javascript
// Initialize download manager
const downloadManager = new DownloadActionManager({
    permissions: permissionsManager
});

// Handle dataset download
document.addEventListener('click', async (e) => {
    if (e.target.classList.contains('download-dataset-btn')) {
        const datasetUuid = e.target.getAttribute('data-dataset-uuid');
        const datasetName = e.target.getAttribute('data-dataset-name');
        
        try {
            await downloadManager.handleDatasetDownload(datasetUuid, datasetName, e.target);
        } catch (error) {
            console.error('Download error:', error);
        }
    }
});

// Check download status
const checkStatus = async (uuid) => {
    const status = await downloadManager.getDownloadStatus(uuid, 'dataset');
    console.log('Download status:', status);
};

// Get download history
const getHistory = async () => {
    const history = await downloadManager.getDownloadHistory({ limit: 20 });
    console.log('Download history:', history);
};
```

## DetailsActionManager.js

### Purpose

Handles details modal functionality including content population, data formatting, and action button management.

### Key Features

- **Modal Management**: Handles modal lifecycle
- **Content Population**: Dynamically populates modal content
- **Data Formatting**: Formats data for display
- **Action Buttons**: Manages action buttons based on permissions
- **Error Handling**: Comprehensive error handling

### API Reference

#### Constructor

```javascript
const detailsManager = new DetailsActionManager({
    permissions: permissionsManager        // Permissions manager instance
});
```

#### Methods

##### `handleDatasetDetails(datasetUuid)`
Handles dataset details display.

**Parameters:**
- `datasetUuid` (string): Dataset UUID

**Returns:** `Promise<void>`

**Example:**
```javascript
await detailsManager.handleDatasetDetails('dataset-uuid');
```

##### `handleCaptureDetails(captureUuid)`
Handles capture details display.

**Parameters:**
- `captureUuid` (string): Capture UUID

**Returns:** `Promise<void>`

**Example:**
```javascript
await detailsManager.handleCaptureDetails('capture-uuid');
```

##### `populateDatasetDetailsModal(datasetData)`
Populates dataset details modal with data.

**Parameters:**
- `datasetData` (Object): Dataset data

**Example:**
```javascript
detailsManager.populateDatasetDetailsModal({
    name: 'My Dataset',
    description: 'Dataset description',
    authors: [{ name: 'John Doe', email: 'john@example.com' }],
    captures: [],
    files: [],
    permissions: []
});
```

##### `populateCaptureDetailsModal(captureData)`
Populates capture details modal with data.

**Parameters:**
- `captureData` (Object): Capture data

**Example:**
```javascript
detailsManager.populateCaptureDetailsModal({
    name: 'My Capture',
    type: 'spectrum',
    directory: '/capture/path',
    channel: '1',
    scan_group: 'group1',
    owner_name: 'John Doe'
});
```

##### `openModal(modalId)`
Opens a modal.

**Parameters:**
- `modalId` (string): Modal ID

**Example:**
```javascript
detailsManager.openModal('datasetDetailsModal');
```

##### `closeModal(modalId)`
Closes a modal.

**Parameters:**
- `modalId` (string): Modal ID

**Example:**
```javascript
detailsManager.closeModal('datasetDetailsModal');
```

##### `showModalLoading(modalId)`
Shows loading state in modal.

**Parameters:**
- `modalId` (string): Modal ID

**Example:**
```javascript
detailsManager.showModalLoading('datasetDetailsModal');
```

##### `showModalError(modalId, message)`
Shows error in modal.

**Parameters:**
- `modalId` (string): Modal ID
- `message` (string): Error message

**Example:**
```javascript
detailsManager.showModalError('datasetDetailsModal', 'Failed to load dataset details');
```

##### `initializeDetailsButtonsForContainer(container)`
Initializes details buttons for dynamically loaded content.

**Parameters:**
- `container` (Element): Container element to search within

**Example:**
```javascript
detailsManager.initializeDetailsButtonsForContainer(document.getElementById('content'));
```

#### Dataset Data Structure

Dataset data objects should have the following structure:

```javascript
{
    name: 'Dataset Name',
    description: 'Dataset description',
    status: 'active',
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-01-01T00:00:00Z',
    authors: [
        { name: 'John Doe', email: 'john@example.com' }
    ],
    captures: [
        {
            id: 1,
            type: 'spectrum',
            directory: '/capture/path',
            channel: '1',
            scan_group: 'group1',
            created_at: '2023-01-01T00:00:00Z'
        }
    ],
    files: [
        {
            id: 1,
            name: 'file.h5',
            media_type: 'application/x-hdf',
            relative_path: '/file.h5',
            size: '1.2 MB'
        }
    ],
    permissions: [
        {
            user_name: 'Jane Doe',
            user_email: 'jane@example.com',
            permission_level: 'contributor'
        }
    ]
}
```

#### Capture Data Structure

Capture data objects should have the following structure:

```javascript
{
    name: 'Capture Name',
    type: 'spectrum',
    directory: '/capture/path',
    channel: '1',
    scan_group: 'group1',
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-01-01T00:00:00Z',
    owner_name: 'John Doe',
    center_frequency_ghz: 2.4,
    bandwidth_mhz: 20,
    sample_rate_hz: 1000000,
    duration_seconds: 60
}
```

#### Usage Example

```javascript
// Initialize details manager
const detailsManager = new DetailsActionManager({
    permissions: permissionsManager
});

// Handle dataset details
document.addEventListener('click', async (e) => {
    if (e.target.classList.contains('dataset-details-btn')) {
        const datasetUuid = e.target.getAttribute('data-dataset-uuid');
        
        try {
            await detailsManager.handleDatasetDetails(datasetUuid);
        } catch (error) {
            console.error('Error loading dataset details:', error);
        }
    }
});

// Handle capture details
document.addEventListener('click', async (e) => {
    if (e.target.classList.contains('capture-details-btn')) {
        const captureUuid = e.target.getAttribute('data-capture-uuid');
        
        try {
            await detailsManager.handleCaptureDetails(captureUuid);
        } catch (error) {
            console.error('Error loading capture details:', error);
        }
    }
});

// Initialize for dynamically loaded content
const initializeDetailsButtons = (container) => {
    detailsManager.initializeDetailsButtonsForContainer(container);
};
```

## Integration with PageLifecycleManager

All action managers integrate with the PageLifecycleManager for coordinated initialization:

### Initialization

```javascript
// In PageLifecycleManager
initializeCoreManagers() {
    // Initialize permissions manager
    this.permissions = new PermissionsManager(this.config.permissions);
    
    // Initialize action managers
    this.downloadActionManager = new DownloadActionManager({
        permissions: this.permissions
    });
    
    this.detailsActionManager = new DetailsActionManager({
        permissions: this.permissions
    });
    
    // Initialize share managers for specific items
    this.initializeShareManagers();
}
```

### Share Manager Initialization

```javascript
// Initialize share managers for each item
initializeDatasetModals() {
    const datasetModals = document.querySelectorAll(".modal[data-item-type='dataset']");
    
    datasetModals.forEach((modal) => {
        const itemUuid = modal.getAttribute("data-item-uuid");
        
        if (itemUuid && this.permissions) {
            const shareManager = new ShareActionManager({
                itemUuid: itemUuid,
                itemType: 'dataset',
                permissions: this.permissions
            });
            
            this.managers.push(shareManager);
            modal.shareActionManager = shareManager;
        }
    });
}
```

## Best Practices

### 1. Permission Checking

Always check permissions before allowing actions:

```javascript
// In ShareActionManager
if (!this.permissions.canShare()) {
    this.showToast("You don't have permission to share this item", "warning");
    return;
}

// In DownloadActionManager
if (!this.permissions.canDownload()) {
    this.showToast("You don't have permission to download this item", "warning");
    return;
}
```

### 2. Error Handling

Use consistent error handling patterns:

```javascript
try {
    await this.handleShareItem();
    this.showToast('Item shared successfully!', 'success');
} catch (error) {
    console.error('Error sharing item:', error);
    this.showToast('Error sharing item. Please try again.', 'danger');
}
```

### 3. Loading States

Provide visual feedback during operations:

```javascript
// Show loading state
const originalContent = button.innerHTML;
button.innerHTML = HTMLInjectionManager.createLoadingSpinner('Processing...');
button.disabled = true;

try {
    await this.performAction();
} finally {
    // Restore button state
    button.innerHTML = originalContent;
    button.disabled = false;
}
```

### 4. Event Listener Management

Prevent duplicate event listeners:

```javascript
// Check if already set up
if (button.dataset.setupComplete === "true") {
    return;
}
button.dataset.setupComplete = "true";

// Add event listener
button.addEventListener("click", handler);
```

### 5. Resource Cleanup

Implement cleanup methods:

```javascript
class ShareActionManager {
    cleanup() {
        // Clear selections
        this.clearSelections();
        
        // Cancel pending requests
        if (this.currentRequest) {
            this.currentRequest.abort();
        }
        
        // Clear timeouts
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }
    }
}
```

## Troubleshooting

### Common Issues

1. **Permission Errors**: Ensure PermissionsManager is properly initialized
2. **Modal Not Opening**: Check modal ID and Bootstrap initialization
3. **Search Not Working**: Verify API endpoints and CSRF tokens
4. **Download Failures**: Check download permissions and file availability

### Debug Mode

Enable debug logging:

```javascript
window.DEBUG_JS = true;
```

This will provide detailed logging for all action operations.

### Testing

Use the provided test suites to verify functionality:

```javascript
// Run action manager tests
const runner = new TestRunner();
runner.addTestSuite("Share Action Manager", window.ShareActionManagerTests);
runner.addTestSuite("Download Action Manager", window.DownloadActionManagerTests);
runner.addTestSuite("Details Action Manager", window.DetailsActionManagerTests);
await runner.runAllTests();
```
