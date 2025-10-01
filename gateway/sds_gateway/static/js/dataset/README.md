# Dataset Components Documentation

This document provides detailed information about the dataset-specific JavaScript components that handle dataset creation, editing, and mode management.

## Overview

The dataset components provide specialized functionality for dataset management:

- **DatasetCreationHandler**: Handles dataset creation workflow
- **DatasetEditingHandler**: Manages dataset editing with pending changes
- **DatasetModeManager**: Coordinates between creation and editing modes

## DatasetCreationHandler.js

### Purpose

Manages the multi-step dataset creation workflow with validation, navigation, and form submission.

### Key Features

- **Multi-step Navigation**: Step-by-step form progression with validation
- **Asset Selection**: Captures and files selection management
- **Form Validation**: Real-time validation for each step
- **Review Generation**: Dynamic review step with selected items
- **Submission Handling**: Form submission with error handling

#### Constructor

```javascript
const creationHandler = new DatasetCreationHandler({
    formId: 'dataset-form',                    // Form element ID
    steps: ['info', 'captures', 'files', 'review'], // Step identifiers
    onStepChange: (step) => { /* callback */ } // Step change callback
});
```

#### Properties

- `currentStep` (number): Current step index
- `selectedCaptures` (Set): Selected capture IDs
- `selectedFiles` (Set): Selected file objects
- `selectedCaptureDetails` (Map): Capture details for selected captures

#### Methods

##### `navigateStep(direction)`

Navigates between steps.

**Parameters:**

- `direction` (number): Direction to navigate (-1 for previous, 1 for next)

**Returns:** `Promise<void>`

**Example:**

```javascript
// Go to next step
await creationHandler.navigateStep(1);

// Go to previous step
await creationHandler.navigateStep(-1);
```

##### `validateCurrentStep()`

Validates the current step.

**Returns:** `boolean` - Whether current step is valid

**Example:**

```javascript
if (creationHandler.validateCurrentStep()) {
    // Enable next button
    document.getElementById('nextStep').disabled = false;
}
```

##### `handleSubmit(e)`

Handles form submission.

**Parameters:**

- `e` (Event): Submit event

**Returns:** `Promise<void>`

**Example:**

```javascript
document.getElementById('submitForm').addEventListener('click', (e) => {
    creationHandler.handleSubmit(e);
});
```

##### `updateHiddenFields()`

Updates hidden form fields with current selections.

**Example:**

```javascript
creationHandler.updateHiddenFields();
```

##### `setSearchHandler(searchHandler, type)`

Sets search handler reference.

**Parameters:**

- `searchHandler` (Object): Search handler instance
- `type` (string): Handler type ('captures' or 'files')

**Example:**

```javascript
creationHandler.setSearchHandler(capturesSearchHandler, 'captures');
creationHandler.setSearchHandler(filesSearchHandler, 'files');
```

#### Step Validation

The handler includes built-in validation for each step:

##### Step 0: Dataset Info

- Name field is required and not empty
- Authors field contains valid JSON array
- Status field is selected

##### Step 1: Captures Selection

- Optional step (always valid)

##### Step 2: Files Selection

- Optional step (always valid)

##### Step 3: Review

- All previous steps must be valid

#### Event Listeners

The handler automatically sets up event listeners for:

- **Navigation buttons**: Previous/Next/Submit buttons
- **Step tabs**: Click navigation between steps
- **Form fields**: Real-time validation on input
- **Asset selection**: Checkbox changes for captures and files

#### Usage Example

```javascript
// Initialize creation handler
const creationHandler = new DatasetCreationHandler({
    formId: 'dataset-form',
    steps: ['info', 'captures', 'files', 'review'],
    onStepChange: (step) => {
        console.log(`Current step: ${step}`);
        // Update UI based on step
    }
});

// Set up search handlers
creationHandler.setSearchHandler(capturesSearchHandler, 'captures');
creationHandler.setSearchHandler(filesSearchHandler, 'files');

// Handle form submission
document.getElementById('submitForm').addEventListener('click', (e) => {
    creationHandler.handleSubmit(e);
});
```

## DatasetEditingHandler.js

### Purpose

Manages dataset editing workflow with pending changes tracking, allowing users to preview changes before saving.

### Key Features

- **Pending Changes**: Tracks additions and removals separately
- **Visual Indicators**: Shows pending changes with visual feedback
- **Change Cancellation**: Allows users to cancel pending changes
- **Current vs Pending**: Maintains separation between current and pending state

### API Reference

#### Constructor

```javascript
const editingHandler = new DatasetEditingHandler({
    datasetUuid: 'dataset-uuid',              // Dataset UUID
    permissions: permissionsManager,          // Permissions manager instance
    currentUserId: 123,                      // Current user ID
    initialCaptures: [],                     // Initial captures data
    initialFiles: []                         // Initial files data
});
```

#### Properties

- `currentCaptures` (Map): Current captures in dataset
- `currentFiles` (Map): Current files in dataset
- `pendingCaptures` (Map): Pending capture changes
- `pendingFiles` (Map): Pending file changes
- `selectedCaptures` (Set): Selected capture IDs (for compatibility)
- `selectedFiles` (Set): Selected file objects (for compatibility)

#### Methods

##### `markCaptureForRemoval(captureId)`

Marks a capture for removal.

**Parameters:**

- `captureId` (string): Capture ID to mark for removal

**Example:**

```javascript
editingHandler.markCaptureForRemoval('capture-123');
```

##### `markFileForRemoval(fileId)`

Marks a file for removal.

**Parameters:**

- `fileId` (string): File ID to mark for removal

**Example:**

```javascript
editingHandler.markFileForRemoval('file-456');
```

##### `addCaptureToPending(captureId, captureData)`

Adds a capture to pending additions.

**Parameters:**

- `captureId` (string): Capture ID
- `captureData` (Object): Capture data

**Example:**

```javascript
editingHandler.addCaptureToPending('new-capture', {
    type: 'spectrum',
    directory: '/new/capture',
    owner_name: 'Current User'
});
```

##### `addFileToPending(fileId, fileData)`

Adds a file to pending additions.

**Parameters:**

- `fileId` (string): File ID
- `fileData` (Object): File data

**Example:**

```javascript
editingHandler.addFileToPending('new-file', {
    name: 'new.h5',
    media_type: 'application/x-hdf',
    size: '2.5 MB'
});
```

##### `getPendingChanges()`

Gets all pending changes.

**Returns:** `Object` - Pending changes object

**Example:**

```javascript
const changes = editingHandler.getPendingChanges();
// Returns: {
//   captures: [['capture-id', { action: 'remove', data: {...} }]],
//   files: [['file-id', { action: 'add', data: {...} }]]
// }
```

##### `hasChanges()`

Checks if there are any pending changes.

**Returns:** `boolean` - Whether there are pending changes

**Example:**

```javascript
if (editingHandler.hasChanges()) {
    // Show save prompt
    showSavePrompt();
}
```

##### `setSearchHandler(searchHandler, type)`

Sets search handler reference.

**Parameters:**

- `searchHandler` (Object): Search handler instance
- `type` (string): Handler type ('captures' or 'files')

**Example:**

```javascript
editingHandler.setSearchHandler(capturesSearchHandler, 'captures');
editingHandler.setSearchHandler(filesSearchHandler, 'files');
```

#### Pending Changes Structure

Pending changes are stored as Maps with the following structure:

```javascript
// For captures
pendingCaptures.set(captureId, {
    action: 'add' | 'remove',
    data: {
        id: captureId,
        type: 'spectrum',
        directory: '/path/to/capture',
        owner_name: 'User Name',
        // ... other capture data
    }
});

// For files
pendingFiles.set(fileId, {
    action: 'add' | 'remove',
    data: {
        id: fileId,
        name: 'file.h5',
        media_type: 'application/x-hdf',
        size: '1.2 MB',
        // ... other file data
    }
});
```

#### Visual Feedback

The handler provides visual feedback for pending changes:

- **Removal**: Items marked for removal are grayed out with strikethrough
- **Addition**: New items are highlighted
- **Pending Lists**: Separate lists show pending additions and removals

#### Usage Example

```javascript
// Initialize editing handler
const editingHandler = new DatasetEditingHandler({
    datasetUuid: 'dataset-uuid',
    permissions: permissionsManager,
    currentUserId: 123,
    initialCaptures: [
        { id: 'capture-1', type: 'spectrum', directory: '/capture1' },
        { id: 'capture-2', type: 'spectrum', directory: '/capture2' }
    ],
    initialFiles: [
        { id: 'file-1', name: 'file1.h5', size: '1.2 MB' }
    ]
});

// Set up search handlers
editingHandler.setSearchHandler(capturesSearchHandler, 'captures');
editingHandler.setSearchHandler(filesSearchHandler, 'files');

// Handle asset removal
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('mark-for-removal-btn')) {
        const captureId = e.target.dataset.captureId;
        editingHandler.markCaptureForRemoval(captureId);
    }
});

// Check for changes before leaving page
window.addEventListener('beforeunload', (e) => {
    if (editingHandler.hasChanges()) {
        e.preventDefault();
        e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
    }
});
```

## DatasetModeManager.js

### Purpose

Manages the distinction between dataset creation and editing modes, delegating to appropriate handlers and managing UI state.

### Key Features

- **Mode Detection**: Automatically detects creation vs editing mode
- **Handler Delegation**: Routes operations to appropriate handler
- **UI Management**: Updates UI based on mode and permissions
- **Permission Integration**: Integrates with permissions system

### API Reference

#### Constructor

```javascript
const modeManager = new DatasetModeManager({
    datasetUuid: 'dataset-uuid',              // null for create mode
    userPermissionLevel: 'contributor',       // User's permission level
    currentUserId: 123,                      // Current user ID
    isOwner: false,                          // Whether user is owner
    datasetPermissions: {                    // Dataset-specific permissions
        canEditMetadata: true,
        canAddAssets: true,
        canRemoveAnyAssets: false,
        canRemoveOwnAssets: true
    }
});
```

#### Properties

- `isEditMode` (boolean): Whether in edit mode
- `permissions` (PermissionsManager): Permissions manager instance
- `handler` (Object): Current handler (creation or editing)

#### Methods

##### `getHandler()`

Gets the current handler.

**Returns:** `Object` - Current handler instance

**Example:**

```javascript
const handler = modeManager.getHandler();
if (modeManager.isInEditMode()) {
    // Use editing handler methods
    handler.markCaptureForRemoval('capture-id');
} else {
    // Use creation handler methods
    handler.navigateStep(1);
}
```

##### `getPermissions()`

Gets the permissions manager.

**Returns:** `PermissionsManager` - Permissions manager instance

**Example:**

```javascript
const permissions = modeManager.getPermissions();
if (permissions.canEditMetadata()) {
    // Enable metadata editing
}
```

##### `isInEditMode()`

Checks if in edit mode.

**Returns:** `boolean` - Whether in edit mode

**Example:**

```javascript
if (modeManager.isInEditMode()) {
    // Handle edit mode specific logic
} else {
    // Handle create mode specific logic
}
```

##### `getDatasetUuid()`

Gets the dataset UUID.

**Returns:** `string|null` - Dataset UUID or null for create mode

**Example:**

```javascript
const uuid = modeManager.getDatasetUuid();
if (uuid) {
    // In edit mode
    console.log('Editing dataset:', uuid);
} else {
    // In create mode
    console.log('Creating new dataset');
}
```

##### `updatePermissions(newPermissions)`

Updates permissions.

**Parameters:**

- `newPermissions` (Object): New permissions object

**Example:**

```javascript
modeManager.updatePermissions({
    canEditMetadata: false,
    canAddAssets: true
});
```

##### `handleSubmit(e)`

Handles form submission (delegates to appropriate handler).

**Parameters:**

- `e` (Event): Submit event

**Returns:** `Promise<void>`

**Example:**

```javascript
document.getElementById('submitForm').addEventListener('click', (e) => {
    modeManager.handleSubmit(e);
});
```

##### `getPendingChanges()`

Gets pending changes (edit mode only).

**Returns:** `Object|null` - Pending changes or null if not in edit mode

**Example:**

```javascript
const changes = modeManager.getPendingChanges();
if (changes) {
    console.log('Pending changes:', changes);
}
```

##### `hasPendingChanges()`

Checks if there are pending changes (edit mode only).

**Returns:** `boolean` - Whether there are pending changes

**Example:**

```javascript
if (modeManager.hasPendingChanges()) {
    // Show save prompt
}
```

##### `cleanup()`

Cleans up resources.

**Example:**

```javascript
modeManager.cleanup();
```

#### Mode Detection

The manager automatically detects the mode based on the presence of `datasetUuid`:

- **Create Mode**: `datasetUuid` is null or undefined
- **Edit Mode**: `datasetUuid` is provided

#### UI Management

The manager automatically updates UI elements based on mode and permissions:

- **Form Fields**: Enables/disables based on permissions
- **Action Buttons**: Shows/hides based on permissions
- **Navigation**: Updates step navigation for edit mode
- **Submit Button**: Changes text and behavior based on mode

#### Usage Example

```javascript
// Initialize mode manager
const modeManager = new DatasetModeManager({
    datasetUuid: 'dataset-uuid', // null for create mode
    userPermissionLevel: 'contributor',
    currentUserId: 123,
    isOwner: false,
    datasetPermissions: {
        canEditMetadata: true,
        canAddAssets: true,
        canRemoveAnyAssets: false,
        canRemoveOwnAssets: true
    }
});

// Check mode
if (modeManager.isInEditMode()) {
    console.log('In edit mode');

    // Get editing handler
    const editingHandler = modeManager.getHandler();

    // Check for pending changes
    if (modeManager.hasPendingChanges()) {
        showSavePrompt();
    }
} else {
    console.log('In create mode');

    // Get creation handler
    const creationHandler = modeManager.getHandler();

    // Navigate steps
    creationHandler.navigateStep(1);
}

// Handle form submission
document.getElementById('submitForm').addEventListener('click', (e) => {
    modeManager.handleSubmit(e);
});

// Update permissions dynamically
modeManager.updatePermissions({
    canEditMetadata: false
});
```

## Integration with Search Handlers

Both creation and editing handlers integrate with search handlers for asset selection:

### Creation Mode Integration

```javascript
// Set up search handlers
const capturesSearchHandler = new SearchHandler({
    searchFormId: 'captures-search-form',
    searchButtonId: 'search-captures',
    clearButtonId: 'clear-captures-search',
    tableBodyId: 'captures-table-body',
    paginationContainerId: 'captures-pagination',
    type: 'captures',
    formHandler: creationHandler,
    isEditMode: false
});

const filesSearchHandler = new SearchHandler({
    searchFormId: 'files-search-form',
    searchButtonId: 'search-files',
    clearButtonId: 'clear-files-search',
    tableBodyId: 'file-tree-table',
    paginationContainerId: 'files-pagination',
    type: 'files',
    formHandler: creationHandler,
    isEditMode: false
});

// Connect handlers
creationHandler.setSearchHandler(capturesSearchHandler, 'captures');
creationHandler.setSearchHandler(filesSearchHandler, 'files');
```

### Editing Mode Integration

```javascript
// Set up search handlers
const capturesSearchHandler = new SearchHandler({
    searchFormId: 'captures-search-form',
    searchButtonId: 'search-captures',
    clearButtonId: 'clear-captures-search',
    tableBodyId: 'captures-table-body',
    paginationContainerId: 'captures-pagination',
    type: 'captures',
    formHandler: editingHandler,
    isEditMode: true
});

const filesSearchHandler = new SearchHandler({
    searchFormId: 'files-search-form',
    searchButtonId: 'search-files',
    clearButtonId: 'clear-files-search',
    tableBodyId: 'file-tree-table',
    paginationContainerId: 'files-pagination',
    type: 'files',
    formHandler: editingHandler,
    isEditMode: true
});

// Connect handlers
editingHandler.setSearchHandler(capturesSearchHandler, 'captures');
editingHandler.setSearchHandler(filesSearchHandler, 'files');
```

## Best Practices

### 1. Mode Detection

Always check the mode before performing operations:

```javascript
if (modeManager.isInEditMode()) {
    // Use editing handler methods
    const editingHandler = modeManager.getHandler();
    editingHandler.markCaptureForRemoval('capture-id');
} else {
    // Use creation handler methods
    const creationHandler = modeManager.getHandler();
    creationHandler.navigateStep(1);
}
```

### 2. Pending Changes

Always check for pending changes in edit mode:

```javascript
if (modeManager.isInEditMode() && modeManager.hasPendingChanges()) {
    // Show save prompt
    showSavePrompt();
}
```

### 3. Permission Checking

Use the permissions manager for access control:

```javascript
const permissions = modeManager.getPermissions();
if (!permissions.canEditMetadata()) {
    // Disable metadata editing
    document.getElementById('edit-metadata-btn').disabled = true;
}
```

### 4. Error Handling

Handle errors appropriately for each mode:

```javascript
try {
    await modeManager.handleSubmit(e);
} catch (error) {
    if (modeManager.isInEditMode()) {
        // Handle editing errors
        showEditError(error);
    } else {
        // Handle creation errors
        showCreationError(error);
    }
}
```

### 5. Resource Cleanup

Always clean up resources:

```javascript
window.addEventListener('beforeunload', () => {
    modeManager.cleanup();
});
```

## Troubleshooting

### Common Issues

1. **Handler Not Found**: Ensure the mode manager is properly initialized
2. **Pending Changes Not Tracked**: Verify the editing handler is connected to search handlers
3. **Validation Failures**: Check that all required fields are filled
4. **Navigation Issues**: Ensure step validation is working correctly

### Debug Mode

Enable debug logging:

```javascript
window.DEBUG_JS = true;
```

This will provide detailed logging for all dataset operations.
