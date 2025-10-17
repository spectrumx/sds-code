# JavaScript Architecture Documentation

This document explains the refactored JavaScript architecture for the SDS Gateway application, focusing on dataset management, sharing, and editing functionality.

## Overview

The JavaScript codebase has been refactored into a modular, maintainable architecture with clear separation of concerns.

## Directory Structure

```text
static/js/
├── core/                           # Core utilities and managers
│   ├── APIClient.js               # Centralized API communication
│   ├── HTMLInjectionManager.js    # Safe DOM manipulation
│   ├── PermissionsManager.js      # Permission checking and access control
│   ├── PageLifecycleManager.js    # Page initialization and cleanup
│   └── __tests__/                 # Core component tests
│       ├── APIClient.test.js
│       ├── HTMLInjectionManager.test.js
│       ├── PermissionsManager.test.js
│       └── PageLifecycleManager.test.js
├── dataset/                        # Dataset-specific functionality
│   ├── DatasetCreationHandler.js  # Dataset creation workflow
│   ├── DatasetEditingHandler.js   # Dataset editing workflow
│   ├── DatasetModeManager.js      # Creation vs editing mode management
│   └── __tests__/                 # Dataset component tests
│       ├── DatasetCreationHandler.test.js
│       ├── DatasetEditingHandler.test.js
│       └── DatasetModeManager.test.js
├── actions/                        # Action-specific managers
│   ├── ShareActionManager.js      # Sharing functionality
│   ├── DownloadActionManager.js   # Download functionality
│   ├── DetailsActionManager.js    # Details modal functionality
│   └── __tests__/                 # Action component tests
│       ├── ShareActionManager.test.js
│       ├── DownloadActionManager.test.js
│       └── DetailsActionManager.test.js
├── share/                          # Sharing functionality
│   ├── ShareGroupManager.js       # Share group management
│   ├── UserShareManager.js        # User sharing functionality
│   └── __tests__/                 # Share component tests
│       └── ShareGroupManager.test.js
├── search/                         # Search functionality
│   ├── AssetSearchHandler.js      # Asset search (captures/files)
│   ├── UserSearchHandler.js       # User search functionality
│   └── __tests__/                 # Search component tests
│       └── AssetSearchHandler.test.js
├── __tests__/                      # Test documentation
│   └── README.md                  # Testing documentation
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

The JavaScript codebase uses Jest for comprehensive testing with coverage reporting, similar to `pytest-cov` for Python.

### Test Structure

Tests are organized by component in `__tests__/` directories:

```
static/js/
├── core/__tests__/
│   ├── PermissionsManager.test.js
│   ├── APIClient.test.js
│   ├── HTMLInjectionManager.test.js
│   └── PageLifecycleManager.test.js
├── actions/__tests__/
│   ├── ShareActionManager.test.js
│   ├── DetailsActionManager.test.js
│   └── DownloadActionManager.test.js
├── dataset/__tests__/
│   ├── DatasetModeManager.test.js
│   ├── DatasetEditingHandler.test.js
│   └── DatasetCreationHandler.test.js
├── search/__tests__/
│   └── AssetSearchHandler.test.js
└── share/__tests__/
    └── ShareGroupManager.test.js
```

### Running Tests

**Basic Commands:**

```bash
# Run all tests
npm test

# Run tests in watch mode (re-runs on file changes)
npm run test:watch

# Run tests with coverage
npm run test:coverage

# Run tests for CI (no watch mode, with coverage)
npm run test:ci
```

**Using the Makefile:**

```bash
# Run all tests (Python + JavaScript)
make test

# This will run:
# - Python tests with pytest
# - JavaScript tests with Jest
# - JavaScript tests with coverage
```

**Using the Coverage Script:**

```bash
# Run the coverage script (opens HTML report on macOS)
./scripts/test-js-coverage.sh
```

### Coverage Reports

Jest automatically generates coverage reports in multiple formats:

- **Terminal**: Text output during test run
- **HTML**: Interactive report at `coverage/lcov-report/index.html`
- **LCOV**: For CI integration at `coverage/lcov.info`

Coverage thresholds are set at 70% for:

- Lines
- Functions
- Branches
- Statements

### Writing Tests

**Basic Test Structure:**

```javascript
describe('ComponentName', () => {
  let component;

  beforeEach(() => {
    // Setup before each test
    component = new ComponentName(config);
  });

  test('should do something', () => {
    expect(component.someMethod()).toBe(true);
  });

  describe('specific functionality', () => {
    test('should handle edge cases', () => {
      // Test implementation
    });
  });
});
```

**Mocking:**

Jest provides built-in mocking capabilities. Common mocks are set up in `jest.setup.js`:

- DOM APIs (`document`, `window`)
- Browser APIs (`fetch`, `localStorage`, etc.)
- Global objects (`console`, `ResizeObserver`, etc.)

**Example Test:**

```javascript
describe('APIClient', () => {
  let apiClient;

  beforeEach(() => {
    jest.clearAllMocks();
    apiClient = new APIClient();
  });

  test('should make GET request with correct headers', async () => {
    const mockResponse = {
      ok: true,
      json: () => Promise.resolve({ success: true })
    };
    global.fetch = jest.fn().mockResolvedValue(mockResponse);

    const result = await apiClient.get('/api/test');

    expect(global.fetch).toHaveBeenCalledWith('/api/test', {
      method: 'GET',
      headers: {
        'X-Requested-With': 'XMLHttpRequest'
      }
    });
    expect(result).toEqual({ success: true });
  });
});
```

### Configuration

**Jest Configuration (`jest.config.js`):**

- **Test Environment**: `jsdom` for DOM testing
- **Coverage**: Collects from `sds_gateway/static/js/**/*.js`
- **Excludes**: Test files, node_modules, coverage directory
- **Setup**: `jest.setup.js` for global test configuration

**Global Setup (`jest.setup.js`):**

Provides mocks for:

- DOM manipulation
- Browser APIs
- Global objects
- Console methods (configurable)

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

## Contributing

When adding new functionality:

1. **Follow established patterns**: Create classes for JS handling/management of each new component, utilizing core modules for generic functions.
2. **Add Jest tests**: Create comprehensive test files in the format `<ComponentName>.test.js` under the appropriate `__tests__/` directory.
3. **Update documentation**: Add features and usage information for each new component to this README.

### Adding New Components

**1. Create the component class:**

```javascript
class NewComponent {
  constructor(config) {
    this.config = config;
    this.initializeEventListeners();
  }

  initializeEventListeners() {
    // Setup event listeners
  }

  cleanup() {
    // Cleanup resources
  }
}
```

**2. Create Jest tests:**

```javascript
// In __tests__/NewComponent.test.js
describe('NewComponent', () => {
  let component;

  beforeEach(() => {
    component = new NewComponent(mockConfig);
  });

  test('should initialize correctly', () => {
    expect(component.config).toBeDefined();
  });

  test('should cleanup resources', () => {
    expect(() => component.cleanup()).not.toThrow();
  });
});
```

**3. Update documentation:**

- Add component description to this README
- Include usage examples
- Document key features and methods
