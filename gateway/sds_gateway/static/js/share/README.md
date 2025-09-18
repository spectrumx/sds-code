# Share Components

This directory contains components for managing sharing functionality in the application.

## Components

### ShareGroupManager.js
Handles all share group operations including creating, managing members, and deleting groups.

**Key Features:**
- Create new share groups
- Add/remove members from groups
- Delete groups with confirmation
- Display shared assets information
- Integration with UserSearchHandler for member management

**Usage:**
```javascript
// Initialize share group manager
const shareGroupManager = new ShareGroupManager({
    apiEndpoint: window.location.href
});

// Initialize all event listeners
shareGroupManager.initializeEventListeners();
```

### UserShareManager.js
Handles share_modal.html functionality for sharing items with users and groups.

**Key Features:**
- User and group search functionality
- Permission level management (viewer, contributor, co-owner)
- Pending changes tracking
- Email notifications
- Integration with core components (APIClient, HTMLInjectionManager)

**Usage:**
```javascript
// Initialize user share manager
const userShareManager = new UserShareManager({
    apiEndpoint: '/users/share-item'
});

// Set item information and initialize
userShareManager.setItemInfo(itemUuid, itemType);
userShareManager.init();
```

## Integration

Both components integrate with the core components:
- **APIClient**: For all API communications
- **HTMLInjectionManager**: For safe DOM manipulation
- **UserSearchHandler**: For user search functionality

## Dependencies

- Core components (`APIClient`, `HTMLInjectionManager`)
- Bootstrap 5 for modal and UI components
- UserSearchHandler for user search functionality
