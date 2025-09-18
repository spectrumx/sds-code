# Core Components Documentation

This document provides detailed information about the core JavaScript components that form the foundation of the SDS Gateway application.

## Overview

The core components provide essential functionality that is used throughout the application:

- **APIClient**: Centralized API communication
- **HTMLInjectionManager**: Safe DOM manipulation
- **PermissionsManager**: Permission checking and access control
- **PageLifecycleManager**: Page initialization and component lifecycle

## APIClient.js

### Purpose

The APIClient provides a centralized, consistent interface for all API communication with built-in CSRF token handling, error management, and loading state support.

### Key Features

- **Automatic CSRF Token Management**: Automatically retrieves and includes CSRF tokens in requests
- **Consistent Error Handling**: Standardized error responses with custom APIError class
- **Loading State Management**: Built-in support for UI loading states
- **Request Methods**: Support for GET, POST, PATCH, PUT operations
- **FormData Serialization**: Automatic conversion of objects to FormData

### API Reference

#### Static Methods

##### `getCSRFToken()`

Retrieves the CSRF token from various sources (meta tag, input field, or cookie).

**Returns:** `string` - CSRF token

**Example:**

```javascript
const token = APIClient.getCSRFToken();
```

##### `request(url, options, loadingState)`

Makes a generic API request with consistent error handling.

**Parameters:**

- `url` (string): Request URL
- `options` (Object): Fetch options
- `loadingState` (LoadingStateManager): Optional loading state manager

**Returns:** `Promise<Object>` - Response data

**Example:**

```javascript
const data = await APIClient.request('/api/endpoint', {
    method: 'POST',
    body: formData
}, loadingState);
```

##### `get(url, params, loadingState)`

Makes a GET request with query parameters.

**Parameters:**

- `url` (string): Request URL
- `params` (Object): Query parameters
- `loadingState` (LoadingStateManager): Optional loading state manager

**Returns:** `Promise<Object>` - Response data

**Example:**

```javascript
const data = await APIClient.get('/api/users', { page: 1, limit: 10 });
```

##### `post(url, data, loadingState)`

Makes a POST request with form data.

**Parameters:**

- `url` (string): Request URL
- `data` (Object): Request data
- `loadingState` (LoadingStateManager): Optional loading state manager

**Returns:** `Promise<Object>` - Response data

**Example:**

```javascript
const result = await APIClient.post('/api/datasets', {
    name: 'My Dataset',
    description: 'Dataset description'
});
```

##### `patch(url, data, loadingState)`

Makes a PATCH request for partial updates.

**Parameters:**

- `url` (string): Request URL
- `data` (Object): Request data
- `loadingState` (LoadingStateManager): Optional loading state manager

**Returns:** `Promise<Object>` - Response data

**Example:**

```javascript
const result = await APIClient.patch('/api/datasets/123', {
    name: 'Updated Name'
});
```

##### `put(url, data, loadingState)`

Makes a PUT request for full updates.

**Parameters:**

- `url` (string): Request URL
- `data` (Object): Request data
- `loadingState` (LoadingStateManager): Optional loading state manager

**Returns:** `Promise<Object>` - Response data

### APIError Class

Custom error class for API-related errors.

**Properties:**

- `message` (string): Error message
- `status` (number): HTTP status code
- `data` (Object): Additional error data

**Example:**

```javascript
try {
    const data = await APIClient.get('/api/endpoint');
} catch (error) {
    if (error instanceof APIError) {
        console.log(`HTTP ${error.status}: ${error.message}`);
        console.log('Error data:', error.data);
    }
}
```

### LoadingStateManager Class

Manages loading states for UI elements.

**Constructor:**

```javascript
const loadingState = new LoadingStateManager(buttonElement);
```

**Methods:**

- `setLoading(loading)`: Sets the loading state

**Example:**

```javascript
const button = document.getElementById('submit-btn');
const loadingState = new LoadingStateManager(button);

// Show loading state
loadingState.setLoading(true);

// Make API call
const result = await APIClient.post('/api/endpoint', data, loadingState);

// Loading state is automatically cleared
```

## HTMLInjectionManager.js

### Purpose

Provides safe DOM manipulation with XSS protection and consistent HTML generation utilities.

### Key Features

- **XSS Protection**: Automatic HTML escaping
- **Safe Injection Methods**: Multiple injection strategies
- **Template System**: Data-driven HTML generation
- **Utility Functions**: Common UI element generation

### API Reference

#### Static Methods

##### `escapeHtml(text)`

Escapes HTML characters to prevent XSS attacks.

**Parameters:**

- `text` (string): Text to escape

**Returns:** `string` - Escaped HTML

**Example:**

```javascript
const safeText = HTMLInjectionManager.escapeHtml('<script>alert("xss")</script>');
// Returns: &lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;
```

##### `injectHTML(container, htmlString, options)`

Safely injects HTML into a container element.

**Parameters:**

- `container` (Element|string): Container element or selector
- `htmlString` (string): HTML string to inject
- `options` (Object): Injection options
    - `escape` (boolean): Whether to escape HTML (default: true)
    - `method` (string): Injection method - 'innerHTML', 'append', 'prepend' (default: 'innerHTML')

**Example:**

```javascript
// Safe injection with escaping
HTMLInjectionManager.injectHTML('#content', '<div>User input</div>', { escape: true });

// Append without escaping (for trusted content)
HTMLInjectionManager.injectHTML('#content', '<div>Trusted content</div>', {
    escape: false,
    method: 'append'
});
```

##### `createTableRow(data, template, options)`

Creates a table row with safe data processing.

**Parameters:**

- `data` (Object): Row data
- `template` (string): HTML template with placeholders
- `options` (Object): Processing options
    - `escape` (boolean): Whether to escape data (default: true)
    - `dateFormat` (string): Date format for date fields (default: "en-US")

**Returns:** `string` - Safe HTML string

**Example:**

```javascript
const data = { name: 'John Doe', email: 'john@example.com', created_at: new Date() };
const template = '<tr><td>{{name}}</td><td>{{email}}</td><td>{{created_at}}</td></tr>';
const row = HTMLInjectionManager.createTableRow(data, template);
```

##### `createUserChip(user, options)`

Creates a user chip HTML element.

**Parameters:**

- `user` (Object): User data
- `options` (Object): Chip options
    - `showPermissionSelect` (boolean): Show permission dropdown (default: true)
    - `showRemoveButton` (boolean): Show remove button (default: true)
    - `permissionLevels` (Array): Available permission levels

**Returns:** `string` - User chip HTML

**Example:**

```javascript
const user = {
    name: 'John Doe',
    email: 'john@example.com',
    type: 'user',
    permission_level: 'viewer'
};

const chip = HTMLInjectionManager.createUserChip(user, {
    showPermissionSelect: true,
    showRemoveButton: true,
    permissionLevels: ['viewer', 'contributor', 'co-owner']
});
```

##### `createErrorMessage(errors, options)`

Creates formatted error message HTML.

**Parameters:**

- `errors` (Object|Array|string): Error data
- `options` (Object): Formatting options
    - `showFieldNames` (boolean): Show field names (default: true)

**Returns:** `string` - Error message HTML

**Example:**

```javascript
const errors = {
    name: ['This field is required'],
    email: ['Enter a valid email address']
};

const errorHtml = HTMLInjectionManager.createErrorMessage(errors);
```

##### `createLoadingSpinner(text, options)`

Creates loading spinner HTML.

**Parameters:**

- `text` (string): Loading text (default: "Loading...")
- `options` (Object): Spinner options
    - `size` (string): Spinner size - 'sm', 'lg' (default: 'sm')
    - `color` (string): Spinner color (default: '')

**Returns:** `string` - Loading spinner HTML

**Example:**

```javascript
const spinner = HTMLInjectionManager.createLoadingSpinner('Processing...', {
    size: 'lg',
    color: 'primary'
});
```

##### `createBadge(text, type, options)`

Creates badge HTML.

**Parameters:**

- `text` (string): Badge text
- `type` (string): Badge type - 'success', 'danger', 'warning', 'info', 'primary', 'secondary' (default: 'primary')
- `options` (Object): Badge options
    - `size` (string): Badge size (default: '')
    - `customClass` (string): Custom CSS class (default: '')

**Returns:** `string` - Badge HTML

**Example:**

```javascript
const badge = HTMLInjectionManager.createBadge('Active', 'success', { size: 'sm' });
```

##### `createButton(text, options)`

Creates button HTML.

**Parameters:**

- `text` (string): Button text
- `options` (Object): Button options
    - `type` (string): Button type (default: 'button')
    - `variant` (string): Button variant (default: 'primary')
    - `size` (string): Button size (default: '')
    - `disabled` (boolean): Whether button is disabled (default: false)
    - `icon` (string): Icon class (default: '')
    - `loading` (boolean): Whether button is loading (default: false)
    - `customClass` (string): Custom CSS class (default: '')
    - `attributes` (Object): Additional HTML attributes

**Returns:** `string` - Button HTML

**Example:**

```javascript
const button = HTMLInjectionManager.createButton('Save', {
    variant: 'success',
    icon: 'bi-save',
    loading: false,
    attributes: { 'data-id': '123' }
});
```

##### `createPagination(pagination, options)`

Creates pagination HTML.

**Parameters:**

- `pagination` (Object): Pagination data
- `options` (Object): Pagination options
    - `showArrows` (boolean): Show previous/next arrows (default: true)
    - `maxPages` (number): Maximum pages to show (default: 5)

**Returns:** `string` - Pagination HTML

**Example:**

```javascript
const pagination = {
    number: 2,
    num_pages: 10,
    has_previous: true,
    has_next: true
};

const paginationHtml = HTMLInjectionManager.createPagination(pagination, { maxPages: 7 });
```

## PermissionsManager.js

### Purpose

Centralizes permission checking and user access control throughout the application.

### Key Features

- **Permission Hierarchy**: Clear hierarchy (owner > co-owner > contributor > viewer)
- **Asset Ownership**: Validates ownership for asset-specific operations
- **Dynamic Permissions**: Supports runtime permission updates
- **Utility Functions**: Permission display and comparison utilities

### API Reference

#### Constructor

```javascript
const permissions = new PermissionsManager({
    userPermissionLevel: 'contributor',    // User's permission level
    datasetUuid: 'uuid',                   // Dataset UUID (null for create mode)
    currentUserId: 123,                    // Current user ID
    isOwner: false,                        // Whether user is the owner
    datasetPermissions: {                  // Dataset-specific permissions
        canEditMetadata: true,
        canAddAssets: true,
        // ... other permissions
    }
});
```

#### Permission Check Methods

##### `canEditMetadata()`

Checks if user can edit dataset metadata.

**Returns:** `boolean`

**Example:**

```javascript
if (permissions.canEditMetadata()) {
    // Enable metadata editing
}
```

##### `canAddAssets()`

Checks if user can add assets to dataset.

**Returns:** `boolean`

##### `canRemoveAnyAssets()`

Checks if user can remove any assets from dataset (owner/co-owner level).

##### `canRemoveOwnAssets()`

Checks if user can remove their own assets from dataset (contributor level).

**Returns:** `boolean`

##### `canShare()`

Checks if user can share dataset.

**Returns:** `boolean`

##### `canDownload()`

Checks if user can download dataset.

**Returns:** `boolean`

##### `canDelete()`

Checks if user can delete dataset.

**Returns:** `boolean`

##### `canView()`

Checks if user can view dataset.

**Returns:** `boolean`

##### `canEditAsset(asset)`

Checks if user can edit specific asset.

**Parameters:**

- `asset` (Object): Asset object with owner_id

**Returns:** `boolean`

**Example:**

```javascript
const asset = { owner_id: 123, name: 'test.h5' };
if (permissions.canEditAsset(asset)) {
    // Allow editing
}
```

##### `canRemoveAsset(asset)`

Checks if user can remove specific asset.

**Parameters:**

- `asset` (Object): Asset object with owner_id

**Returns:** `boolean`

##### `canAddAsset(asset)`

Checks if user can add specific asset.

**Parameters:**

- `asset` (Object): Asset object with owner_id

**Returns:** `boolean`

#### Utility Methods

##### `getPermissionDisplayName(level)`

Gets display name for permission level.

**Parameters:**

- `level` (string): Permission level

**Returns:** `string` - Display name

**Example:**

```javascript
const displayName = PermissionsManager.getPermissionDisplayName('co-owner');
// Returns: 'Co-Owner'
```

##### `getPermissionDescription(level)`

Gets description for permission level.

**Parameters:**

- `level` (string): Permission level

**Returns:** `string` - Description

##### `getPermissionIcon(level)`

Gets icon class for permission level.

**Parameters:**

- `level` (string): Permission level

**Returns:** `string` - Icon class

##### `getPermissionBadgeClass(level)`

Gets badge class for permission level.

**Parameters:**

- `level` (string): Permission level

**Returns:** `string` - Badge class

##### `isHigherPermission(level1, level2)`

Compares permission levels.

**Parameters:**

- `level1` (string): First permission level
- `level2` (string): Second permission level

**Returns:** `boolean` - Whether level1 is higher than level2

##### `getAvailablePermissionLevels()`

Gets all available permission levels.

**Returns:** `Array<Object>` - Array of permission level objects

**Example:**

```javascript
const levels = PermissionsManager.getAvailablePermissionLevels();
// Returns: [
//   { value: 'viewer', label: 'Viewer', description: '...', icon: '...', badgeClass: '...' },
//   { value: 'contributor', label: 'Contributor', description: '...', icon: '...', badgeClass: '...' },
//   { value: 'co-owner', label: 'Co-Owner', description: '...', icon: '...', badgeClass: '...' }
// ]
```

#### Instance Methods

##### `getPermissionSummary()`

Gets comprehensive permission summary.

**Returns:** `Object` - Permission summary

**Example:**

```javascript
const summary = permissions.getPermissionSummary();
// Returns: {
//   userPermissionLevel: 'contributor',
//   displayName: 'Contributor',
//   description: 'Can add their own assets and edit metadata',
//   icon: 'bi-plus-circle',
//   badgeClass: 'bg-success',
//   isEditMode: true,
//   isOwner: false,
//   permissions: {
//     canEditMetadata: true,
//     canAddAssets: true,
//     canRemoveAnyAssets: false,
//     canRemoveOwnAssets: true,
//     canShare: false,
//     canDownload: true,
//     canDelete: false,
//     canView: true
//   }
// }
```

##### `updateDatasetPermissions(newPermissions)`

Updates dataset-specific permissions.

**Parameters:**

- `newPermissions` (Object): New permissions object

**Example:**

```javascript
permissions.updateDatasetPermissions({
    canEditMetadata: false,
    canAddAssets: true
});
```

##### `hasAnyPermission(permissionNames)`

Checks if user has any of the specified permissions.

**Parameters:**

- `permissionNames` (Array&lt;string&gt;): Array of permission names

**Returns:** `boolean`

**Example:**

```javascript
const hasPermission = permissions.hasAnyPermission(['canEditMetadata', 'canShare']);
```

##### `hasAllPermissions(permissionNames)`

Checks if user has all of the specified permissions.

**Parameters:**

- `permissionNames` (Array&lt;string&gt;): Array of permission names

**Returns:** `boolean`

**Example:**

```javascript
const hasAllPermissions = permissions.hasAllPermissions(['canEditMetadata', 'canAddAssets']);
```

## PageLifecycleManager.js

### Purpose

Manages page initialization, component lifecycle, and cleanup for the entire application.

### Key Features

- **Automatic Initialization**: Detects page type and initializes appropriate components
- **Manager Coordination**: Coordinates between different managers
- **Event Management**: Handles global event listeners
- **Resource Cleanup**: Ensures proper cleanup on page unload

### API Reference

#### Constructor

```javascript
const lifecycleManager = new PageLifecycleManager({
    pageType: 'dataset-edit',              // Page type identifier
    permissions: {                         // Permission configuration
        userPermissionLevel: 'contributor',
        currentUserId: 123,
        isOwner: false,
        datasetPermissions: {}
    },
    dataset: {                             // Dataset configuration
        datasetUuid: 'uuid',
        initialCaptures: [],
        initialFiles: []
    }
});
```

#### Supported Page Types

- `dataset-create`: Dataset creation page
- `dataset-edit`: Dataset editing page
- `dataset-list`: Dataset list page
- `capture-list`: Capture list page

#### Methods

##### `getManager(type)`

Gets a specific manager by type.

**Parameters:**

- `type` (string): Manager type - 'permissions', 'datasetMode', 'shareAction', 'downloadAction', 'detailsAction', or class name

**Returns:** `Object|null` - Manager instance or null

**Example:**

```javascript
const permissions = lifecycleManager.getManager('permissions');
const datasetManager = lifecycleManager.getManager('datasetMode');
```

##### `addManager(manager)`

Adds a custom manager to the lifecycle.

**Parameters:**

- `manager` (Object): Manager instance

**Example:**

```javascript
const customManager = new CustomManager(config);
lifecycleManager.addManager(customManager);
```

##### `removeManager(manager)`

Removes a manager from the lifecycle.

**Parameters:**

- `manager` (Object): Manager instance to remove

##### `updateConfig(newConfig)`

Updates the configuration.

**Parameters:**

- `newConfig` (Object): New configuration object

**Example:**

```javascript
lifecycleManager.updateConfig({
    permissions: {
        userPermissionLevel: 'co-owner'
    }
});
```

##### `refresh()`

Refreshes all page components.

**Returns:** `Promise<void>`

**Example:**

```javascript
await lifecycleManager.refresh();
```

##### `cleanup()`

Cleans up all managers and resources.

**Example:**

```javascript
lifecycleManager.cleanup();
```

##### `getStatus()`

Gets current page status.

**Returns:** `Object` - Status information

**Example:**

```javascript
const status = lifecycleManager.getStatus();
// Returns: {
//   initialized: true,
//   pageType: 'dataset-edit',
//   managersCount: 5,
//   managers: ['PermissionsManager', 'DatasetModeManager', 'ShareActionManager', ...]
// }
```

##### `isManagerInitialized(type)`

Checks if a manager is initialized.

**Parameters:**

- `type` (string): Manager type

**Returns:** `boolean`

##### `waitForManager(type, timeout)`

Waits for a manager to be initialized.

**Parameters:**

- `type` (string): Manager type
- `timeout` (number): Timeout in milliseconds (default: 5000)

**Returns:** `Promise<Object>` - Manager instance

**Example:**

```javascript
try {
    const manager = await lifecycleManager.waitForManager('datasetMode', 3000);
    // Manager is ready
} catch (error) {
    console.error('Manager not initialized:', error.message);
}
```

## Usage Examples

### Complete Page Setup

```javascript
// Initialize page lifecycle manager
const lifecycleManager = new PageLifecycleManager({
    pageType: 'dataset-edit',
    permissions: {
        userPermissionLevel: 'contributor',
        currentUserId: 123,
        isOwner: false,
        datasetPermissions: {
            canEditMetadata: true,
            canAddAssets: true,
            canRemoveAnyAssets: false,
            canRemoveOwnAssets: true
        }
    },
    dataset: {
        datasetUuid: 'dataset-uuid',
        initialCaptures: [],
        initialFiles: []
    }
});

// Wait for initialization
await lifecycleManager.waitForManager('datasetMode');

// Get specific managers
const datasetManager = lifecycleManager.getManager('datasetMode');
const permissions = lifecycleManager.getManager('permissions');

// Use managers
if (permissions.canEditMetadata()) {
    // Enable editing
}
```

### API Communication

```javascript
// Simple GET request
const data = await APIClient.get('/api/datasets');

// POST with loading state
const button = document.getElementById('submit-btn');
const loadingState = new LoadingStateManager(button);

try {
    const result = await APIClient.post('/api/datasets', {
        name: 'New Dataset',
        description: 'Dataset description'
    }, loadingState);

    console.log('Dataset created:', result);
} catch (error) {
    if (error instanceof APIError) {
        console.error(`API Error: ${error.status} - ${error.message}`);
    } else {
        console.error('Network error:', error.message);
    }
}
```

### Safe DOM Manipulation

```javascript
// Safe HTML injection
const container = document.getElementById('content');
const userData = { name: 'John Doe', email: 'john@example.com' };

HTMLInjectionManager.injectHTML(container, `
    <div class="user-info">
        <h3>{{name}}</h3>
        <p>{{email}}</p>
    </div>
`, { escape: true });

// Create user chip
const user = {
    name: 'Jane Smith',
    email: 'jane@example.com',
    type: 'user',
    permission_level: 'contributor'
};

const chip = HTMLInjectionManager.createUserChip(user, {
    showPermissionSelect: true,
    showRemoveButton: true
});

HTMLInjectionManager.injectHTML('#user-chips', chip, { escape: false });
```

### Permission Checking

```javascript
// Initialize permissions
const permissions = new PermissionsManager({
    userPermissionLevel: 'contributor',
    currentUserId: 123,
    isOwner: false,
    datasetPermissions: {}
});

// Check permissions
if (permissions.canEditMetadata()) {
    // Enable metadata editing
    document.getElementById('edit-metadata-btn').style.display = 'block';
}

if (permissions.canShare()) {
    // Enable sharing
    document.getElementById('share-btn').style.display = 'block';
}

// Check asset-specific permissions
const asset = { owner_id: 123, name: 'test.h5' };
if (permissions.canEditAsset(asset)) {
    // Enable asset editing
}

// Get permission summary for UI
const summary = permissions.getPermissionSummary();
document.getElementById('permission-display').innerHTML = `
    <span class="badge ${summary.badgeClass}">${summary.displayName}</span>
    <small>${summary.description}</small>
`;
```

## Best Practices

### 1. Error Handling

Always use try-catch blocks with APIClient:

```javascript
try {
    const result = await APIClient.post('/api/endpoint', data);
    // Handle success
} catch (error) {
    if (error instanceof APIError) {
        // Handle API errors
        console.error(`API Error: ${error.status} - ${error.message}`);
    } else {
        // Handle network errors
        console.error('Network error:', error.message);
    }
}
```

### 2. Permission Checking

Check permissions before allowing actions:

```javascript
if (!permissions.canEditMetadata()) {
    showToast('You do not have permission to edit metadata', 'warning');
    return;
}

// Proceed with action
```

### 3. Safe DOM Manipulation

Always use HTMLInjectionManager for DOM manipulation:

```javascript
// Good
HTMLInjectionManager.injectHTML(container, htmlString, { escape: true });

// Bad - potential XSS vulnerability
container.innerHTML = htmlString;
```

### 4. Resource Cleanup

Implement cleanup methods for custom managers:

```javascript
class CustomManager {
    constructor(config) {
        this.setupEventListeners();
    }

    cleanup() {
        // Remove event listeners
        // Clear references
        // Cancel pending operations
    }
}
```

### 5. Loading States

Use LoadingStateManager for better UX:

```javascript
const button = document.getElementById('submit-btn');
const loadingState = new LoadingStateManager(button);

// Loading state is automatically managed
const result = await APIClient.post('/api/endpoint', data, loadingState);
```

## Troubleshooting

### Common Issues

1. **CSRF Token Errors**: Ensure the page includes CSRF token in meta tag or form
2. **Permission Check Failures**: Verify PermissionsManager is properly initialized
3. **DOM Manipulation Errors**: Use HTMLInjectionManager for all DOM operations
4. **Memory Leaks**: Implement proper cleanup methods in custom managers

### Debug Mode

Enable debug logging:

```javascript
window.DEBUG_JS = true;
```

This will provide detailed logging for all core operations.
