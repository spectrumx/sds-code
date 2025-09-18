# Search Components

This directory contains components for handling search functionality across the application.

## Components

### AssetSearchHandler.js

Handles search functionality for captures and files in dataset creation/editing workflows.

**Key Features:**

- Search captures with filters (directory, type, scan group, channel)
- Search files with filters (name, directory, extension)
- File tree rendering with expandable directories
- Selection management for both create and edit modes
- Pagination support
- Integration with form handlers

**Usage:**

```javascript
// Initialize asset search handler
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

## Integration

Both components integrate with the core components:

- **APIClient**: For all API communications
- **HTMLInjectionManager**: For safe DOM manipulation
- Form handlers for state management

## Dependencies

- Core components (`APIClient`, `HTMLInjectionManager`)
- Bootstrap 5 for UI components
- Form handlers for state management
