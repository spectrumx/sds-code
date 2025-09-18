# JavaScript Architecture Documentation

This document explains the refactored JavaScript architecture for the SDS Gateway application, focusing on dataset management, sharing, and editing functionality.

## Overview

The JavaScript codebase has been refactored into a modular, maintainable architecture with clear separation of concerns.

## Directory Structure

```
static/js/
├── core/                           # Core utilities and managers
│   ├── APIClient.js               # Centralized API communication
│   ├── HTMLInjectionManager.js    # Safe DOM manipulation
│   ├── PermissionsManager.js      # Permission checking and access control
│   └── PageLifecycleManager.js    # Page initialization and cleanup
├── dataset/                        # Dataset-specific functionality
│   ├── DatasetCreationHandler.js  # Dataset creation workflow
│   ├── DatasetEditingHandler.js   # Dataset editing workflow
│   └── DatasetModeManager.js      # Creation vs editing mode management
├── actions/                        # Action-specific managers
│   ├── ShareActionManager.js      # Sharing functionality
│   ├── DownloadActionManager.js   # Download functionality
│   └── DetailsActionManager.js    # Details modal functionality
├── share/                          # Sharing functionality
│   ├── ShareGroupManager.js       # Share group management
│   └── UserShareManager.js        # User sharing functionality
├── search/                         # Search functionality
│   ├── AssetSearchHandler.js      # Asset search (captures/files)
│   └── UserSearchHandler.js       # User search functionality
├── tests/                          # Test suites
│   ├── test-permissions.js        # Permission manager tests
│   ├── test-sharing.js            # Sharing functionality tests
│   ├── test-dataset-editing.js    # Dataset editing tests
│   └── test-runner.js             # Test runner and execution
└── README.md                       # This documentation
```

## Core Components

### 1. APIClient.js

Centralized API communication with consistent error handling, CSRF token management, and loading states.

**Key Features:**
- Automatic CSRF token handling
- Consistent error handling with custom APIError class
- Loading state management
- Support for GET, POST, PATCH, PUT requests
- FormData serialization

**Usage:**
```javascript
// GET request
const data = await APIClient.get('/api/endpoint', { param: 'value' });

// POST request with loading state
const loadingState = new LoadingStateManager(buttonElement);
const result = await APIClient.post('/api/endpoint', { data: 'value' }, loadingState);
```

### 2. HTMLInjectionManager.js

Safe DOM manipulation with XSS protection and consistent HTML generation.

**Key Features:**
- HTML escaping to prevent XSS attacks
- Safe HTML injection methods
- Template-based content generation
- User chip creation
- Error message formatting
- Loading spinner generation

**Usage:**
```javascript
// Safe HTML injection
HTMLInjectionManager.injectHTML(container, htmlString, { escape: true });

// Create user chip
const chip = HTMLInjectionManager.createUserChip(user, {
    showPermissionSelect: true,
    showRemoveButton: true
});

// Create table row
const row = HTMLInjectionManager.createTableRow(data, template, options);
```

### 3. PermissionsManager.js

Centralized permission checking and user access control.

**Key Features:**
- Permission level hierarchy (owner > co-owner > contributor > viewer)
- Asset ownership validation
- Permission display utilities
- Dynamic permission updates

**Usage:**
```javascript
const permissions = new PermissionsManager({
    userPermissionLevel: 'contributor',
    datasetUuid: 'uuid',
    currentUserId: 123,
    isOwner: false,
    datasetPermissions: {}
});

// Check permissions
if (permissions.canEditMetadata()) {
    // Allow editing
}

// Get permission summary
const summary = permissions.getPermissionSummary();
```

### 4. PageLifecycleManager.js

Manages page initialization, component lifecycle, and cleanup.

**Key Features:**
- Automatic component initialization
- Page-specific manager setup
- Event listener management
- Resource cleanup
- Manager coordination

**Usage:**
```javascript
const lifecycleManager = new PageLifecycleManager({
    pageType: 'dataset-edit',
    permissions: { /* config */ },
    dataset: { /* config */ }
});

// Get specific manager
const datasetManager = lifecycleManager.getManager('datasetMode');
```

## Dataset Components

### 1. DatasetCreationHandler.js

Handles the dataset creation workflow with step-by-step validation.

**Key Features:**
- Multi-step form navigation
- Step validation
- Asset selection management
- Form submission handling
- Review step generation

**Usage:**
```javascript
const creationHandler = new DatasetCreationHandler({
    formId: 'dataset-form',
    steps: ['info', 'captures', 'files', 'review'],
    onStepChange: (step) => { /* handle step change */ }
});
```

### 2. DatasetEditingHandler.js

Manages dataset editing with pending changes tracking.

**Key Features:**
- Pending changes management
- Asset addition/removal tracking
- Visual change indicators
- Change cancellation
- Current vs pending state management

**Usage:**
```javascript
const editingHandler = new DatasetEditingHandler({
    datasetUuid: 'uuid',
    permissions: permissionsManager,
    currentUserId: 123,
    initialCaptures: [],
    initialFiles: []
});

// Mark asset for removal
editingHandler.markCaptureForRemoval('capture-id');

// Check for pending changes
if (editingHandler.hasChanges()) {
    // Show save prompt
}
```

### 3. DatasetModeManager.js

Manages the distinction between creation and editing modes.

**Key Features:**
- Mode detection (create vs edit)
- Handler delegation
- UI state management
- Permission-based UI updates

**Usage:**
```javascript
const modeManager = new DatasetModeManager({
    datasetUuid: null, // null for create mode
    userPermissionLevel: 'contributor',
    // ... other config
});

// Check mode
if (modeManager.isInEditMode()) {
    // Handle edit mode
}
```

## Action Components

### 1. ShareActionManager.js

Handles all sharing-related functionality.

**Key Features:**
- User/group search and selection
- Permission level management
- Pending changes tracking
- Notification handling
- Modal management

**Usage:**
```javascript
const shareManager = new ShareActionManager({
    itemUuid: 'dataset-uuid',
    itemType: 'dataset',
    permissions: permissionsManager
});

// Handle share action
await shareManager.handleShareItem();
```

### 2. DownloadActionManager.js

Manages download functionality with permission checking.

**Key Features:**
- Permission-based download access
- Download request handling
- Status tracking
- Error handling

**Usage:**
```javascript
const downloadManager = new DownloadActionManager({
    permissions: permissionsManager
});

// Handle download
await downloadManager.handleDatasetDownload(uuid, name, button);
```

### 3. DetailsActionManager.js

Handles details modal functionality.

**Key Features:**
- Modal content population
- Data formatting
- Permission-based action buttons
- Error handling

**Usage:**
```javascript
const detailsManager = new DetailsActionManager({
    permissions: permissionsManager
});

// Show details
await detailsManager.handleDatasetDetails(uuid);
```

## Share Components

### 1. ShareGroupManager.js

Handles all share group operations including creating, managing members, and deleting groups.

**Key Features:**
- Create new share groups
- Add/remove members from groups
- Delete groups with confirmation
- Display shared assets information
- Integration with UserSearchHandler for member management

**Usage:**
```javascript
const shareGroupManager = new ShareGroupManager({
    apiEndpoint: window.location.href
});

// Initialize all event listeners
shareGroupManager.initializeEventListeners();
```

### 2. UserShareManager.js

Handles share_modal.html functionality for sharing items with users and groups.

**Key Features:**
- User and group search functionality
- Permission level management (viewer, contributor, co-owner)
- Pending changes tracking
- Email notifications
- Integration with core components

**Usage:**
```javascript
const userShareManager = new UserShareManager({
    apiEndpoint: '/users/share-item'
});

// Set item information and initialize
userShareManager.setItemInfo(itemUuid, itemType);
userShareManager.init();
```

## Search Components

### 1. AssetSearchHandler.js

Handles search functionality for captures and files in dataset creation/editing workflows.

**Key Features:**
- Search captures with filters (directory, type, scan group, channel)
- Search files with filters (name, directory, extension)
- File tree rendering with expandable directories
- Selection management for both create and edit modes
- Pagination support

**Usage:**
```javascript
const assetSearchHandler = new AssetSearchHandler({
    searchFormId: 'captures-search-form',
    searchButtonId: 'search-captures',
    clearButtonId: 'clear-captures-search',
    tableBodyId: 'captures-table-body',
    paginationContainerId: 'captures-pagination',
    type: 'captures', // or 'files'
    formHandler: datasetCreationHandler,
    isEditMode: false
});
```

## Testing

### Test Structure

The test suite includes comprehensive tests for all major components:

- **test-permissions.js**: Tests permission checking logic
- **test-sharing.js**: Tests sharing functionality
- **test-dataset-editing.js**: Tests dataset creation and editing
- **test-runner.js**: Executes all tests and provides results

### Running Tests

**In Browser:**
```javascript
// Tests run automatically when page loads
// Or manually:
const runner = new TestRunner();
await runner.runInBrowser();
```

**In Node.js:**
```bash
node test-runner.js
```

### Writing Tests

```javascript
// Add test to existing suite
permissionsTests.addTest("Test name", () => {
    // Test implementation
    permissionsTests.assert(condition, "Error message");
    permissionsTests.assertEqual(actual, expected, "Error message");
});
```

## Integration Guide

### 1. Adding New Pages

1. Create page-specific configuration
2. Initialize PageLifecycleManager with appropriate pageType
3. Add any custom managers to the lifecycle manager

```javascript
const lifecycleManager = new PageLifecycleManager({
    pageType: 'new-page-type',
    permissions: { /* config */ },
    // ... other config
});
```

### 2. Adding New Actions

1. Create new action manager in `actions/` directory
2. Extend base functionality as needed
3. Register with PageLifecycleManager

```javascript
class NewActionManager {
    constructor(config) {
        this.permissions = config.permissions;
        this.initializeEventListeners();
    }
    
    // Implement action-specific methods
}
```

### 3. Adding New Permissions

1. Add permission check method to PermissionsManager
2. Update permission hierarchy if needed
3. Add tests for new permission logic

```javascript
// In PermissionsManager.js
canNewAction() {
    if (this.isOwner) return true;
    return this.datasetPermissions.canNewAction || 
           this.userPermissionLevel === "co-owner";
}
```

## Best Practices

### 1. Permission Checking

Always check permissions before allowing actions:

```javascript
if (!this.permissions.canEditMetadata()) {
    this.showToast("You don't have permission to edit metadata", "warning");
    return;
}
```

### 2. Error Handling

Use consistent error handling with APIClient:

```javascript
try {
    const result = await APIClient.post('/api/endpoint', data);
    // Handle success
} catch (error) {
    if (error instanceof APIError) {
        this.showToast(error.message, "danger");
    } else {
        this.showToast("An unexpected error occurred", "danger");
    }
}
```

### 3. DOM Manipulation

Always use HTMLInjectionManager for safe DOM manipulation:

```javascript
// Good
HTMLInjectionManager.injectHTML(container, htmlString, { escape: true });

// Bad
container.innerHTML = htmlString; // Potential XSS vulnerability
```

### 4. Event Listener Management

Prevent duplicate event listeners:

```javascript
if (button.dataset.setupComplete === "true") {
    return;
}
button.dataset.setupComplete = "true";
button.addEventListener("click", handler);
```

### 5. Resource Cleanup

Implement cleanup methods for managers:

```javascript
class MyManager {
    cleanup() {
        // Remove event listeners
        // Clear references
        // Cancel pending operations
    }
}
```

## Migration Guide

### From Old Architecture

1. **Replace direct API calls** with APIClient
2. **Replace innerHTML usage** with HTMLInjectionManager
3. **Centralize permission checks** using PermissionsManager
4. **Use PageLifecycleManager** for initialization
5. **Break out functionality** into specific managers

### Backward Compatibility

The new architecture maintains backward compatibility by:
- Preserving global function names where possible
- Providing fallback implementations
- Maintaining existing API contracts

## Troubleshooting

### Common Issues

1. **Permission checks failing**: Ensure PermissionsManager is properly initialized
2. **Event listeners not working**: Check for duplicate listener attachment
3. **API calls failing**: Verify CSRF token and endpoint URLs
4. **DOM manipulation errors**: Use HTMLInjectionManager for safe operations


## Contributing

When adding new functionality:

1. Follow the established patterns
2. Add unit tests
3. Update documentation

## Performance Considerations

- Use debouncing for search operations
- Implement proper cleanup to prevent memory leaks
- Cache permission checks when possible
- Use efficient DOM manipulation methods
- Minimize API calls through proper state management
