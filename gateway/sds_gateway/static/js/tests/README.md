# JavaScript Tests Documentation

This document provides comprehensive information about the JavaScript test suite for the SDS Gateway application.

## Overview

The test suite provides comprehensive testing for all major JavaScript components:

- **test-permissions.js**: Tests permission checking logic
- **test-sharing.js**: Tests sharing functionality
- **test-dataset-editing.js**: Tests dataset creation and editing
- **test-runner.js**: Executes all tests and provides results

## Test Structure

### Test Framework

The tests use a custom test framework that provides:

- **Assertion Methods**: `assert()`, `assertEqual()`, `assertContains()`
- **Test Organization**: Grouped test suites with individual test cases
- **Result Reporting**: Detailed pass/fail reporting with error messages
- **Async Support**: Full support for asynchronous test operations

### Test Suite Organization

Each test suite follows a consistent structure:

```javascript
class ComponentTests {
    constructor() {
        this.tests = [];
        this.passed = 0;
        this.failed = 0;
    }

    addTest(name, testFn) {
        this.tests.push({ name, testFn });
    }

    async runTests() {
        // Run all tests and report results
    }

    assert(condition, message) {
        if (!condition) {
            throw new Error(message);
        }
    }

    assertEqual(actual, expected, message) {
        if (actual !== expected) {
            throw new Error(`${message}. Expected: ${expected}, Actual: ${actual}`);
        }
    }
}
```

## Test Suites

### test-permissions.js

Tests the PermissionsManager class and permission checking logic.

#### Test Coverage

- **Owner Permissions**: Verifies owners have all permissions
- **Co-owner Permissions**: Verifies co-owners have most permissions
- **Contributor Permissions**: Verifies contributors have limited permissions
- **Viewer Permissions**: Verifies viewers have minimal permissions
- **Asset Ownership**: Tests asset-specific permission checks
- **Permission Hierarchy**: Tests permission level comparisons
- **Permission Utilities**: Tests display names, descriptions, icons
- **Permission Updates**: Tests dynamic permission updates

#### Example Tests

```javascript
// Test owner permissions
permissionsTests.addTest("Owner has all permissions", () => {
    const permissions = new PermissionsManager({
        userPermissionLevel: "owner",
        isOwner: true
    });

    permissionsTests.assert(permissions.canEditMetadata(), "Owner should be able to edit metadata");
    permissionsTests.assert(permissions.canAddAssets(), "Owner should be able to add assets");
    permissionsTests.assert(permissions.canRemoveAnyAssets(), "Owner should be able to remove any assets");
    permissionsTests.assert(permissions.canRemoveOwnAssets(), "Owner should be able to remove their own assets");
    permissionsTests.assert(permissions.canShare(), "Owner should be able to share");
    permissionsTests.assert(permissions.canDownload(), "Owner should be able to download");
    permissionsTests.assert(permissions.canDelete(), "Owner should be able to delete");
    permissionsTests.assert(permissions.canView(), "Owner should be able to view");
});

// Test permission hierarchy
permissionsTests.addTest("Permission hierarchy", () => {
    permissionsTests.assert(PermissionsManager.isHigherPermission("owner", "co-owner"), "Owner should be higher than co-owner");
    permissionsTests.assert(PermissionsManager.isHigherPermission("co-owner", "contributor"), "Co-owner should be higher than contributor");
    permissionsTests.assert(PermissionsManager.isHigherPermission("contributor", "viewer"), "Contributor should be higher than viewer");
    permissionsTests.assert(!PermissionsManager.isHigherPermission("viewer", "contributor"), "Viewer should not be higher than contributor");
});
```

### test-sharing.js

Tests the ShareActionManager class and sharing functionality.

#### Test Coverage

- **Permission Checking**: Verifies sharing permissions
- **User Selection**: Tests user and group selection
- **Permission Changes**: Tests permission level changes
- **Pending Changes**: Tests pending changes tracking
- **Error Handling**: Tests error scenarios
- **Modal Management**: Tests modal lifecycle

#### Example Tests

```javascript
// Test user selection
sharingTests.addTest("User selection works correctly", () => {
    const manager = sharingTests.createMockShareActionManager();
    const inputId = "user-search-test-uuid";

    // Add user to selection
    manager.selectedUsersMap[inputId] = [
        {
            name: "Test User",
            email: "test@example.com",
            type: "user",
            permission_level: "viewer"
        }
    ];

    sharingTests.assert(manager.selectedUsersMap[inputId].length === 1);
    sharingTests.assertEqual(manager.selectedUsersMap[inputId][0].email, "test@example.com");
    sharingTests.assertEqual(manager.selectedUsersMap[inputId][0].permission_level, "viewer");
});

// Test permission level changes
sharingTests.addTest("Permission level changes work correctly", () => {
    const manager = sharingTests.createMockShareActionManager();
    const userEmail = "test@example.com";

    // Add permission change
    manager.pendingPermissionChanges.set(userEmail, {
        userName: "Test User",
        itemUuid: "test-uuid",
        itemType: "dataset",
        permissionLevel: "contributor"
    });

    sharingTests.assert(manager.pendingPermissionChanges.has(userEmail));
    sharingTests.assertEqual(manager.pendingPermissionChanges.get(userEmail).permissionLevel, "contributor");
});
```

### test-dataset-editing.js

Tests dataset creation and editing functionality.

#### Test Coverage

- **Creation Handler**: Tests dataset creation workflow
- **Editing Handler**: Tests dataset editing with pending changes
- **Step Navigation**: Tests multi-step form navigation
- **Asset Selection**: Tests capture and file selection
- **Pending Changes**: Tests pending changes tracking
- **Permission Integration**: Tests permission-based access control

#### Example Tests

```javascript
// Test step navigation
datasetEditingTests.addTest("Step navigation works correctly in creation mode", () => {
    const handler = datasetEditingTests.createMockDatasetCreationHandler();

    // Test forward navigation
    const forwardResult = handler.navigateStep(1);
    datasetEditingTests.assert(forwardResult, "Should be able to navigate forward");
    datasetEditingTests.assertEqual(handler.currentStep, 1);

    // Test backward navigation
    const backwardResult = handler.navigateStep(-1);
    datasetEditingTests.assert(backwardResult, "Should be able to navigate backward");
    datasetEditingTests.assertEqual(handler.currentStep, 0);
});

// Test pending changes
datasetEditingTests.addTest("Pending changes tracking works correctly", () => {
    const handler = datasetEditingTests.createMockDatasetEditingHandler();

    // Initially no changes
    datasetEditingTests.assert(!handler.hasChanges(), "Should have no changes initially");

    // Add some changes
    handler.markCaptureForRemoval("capture1");
    handler.addFileToPending("file1", { name: "new.h5" });

    datasetEditingTests.assert(handler.hasChanges(), "Should have changes after modifications");

    const changes = handler.getPendingChanges();
    datasetEditingTests.assertEqual(changes.captures.length, 1);
    datasetEditingTests.assertEqual(changes.files.length, 1);
});
```

## Test Runner

### test-runner.js

The test runner coordinates execution of all test suites and provides comprehensive reporting.

#### Features

- **Suite Management**: Manages multiple test suites
- **Result Aggregation**: Aggregates results from all suites
- **Error Handling**: Handles test execution errors
- **Detailed Reporting**: Provides detailed pass/fail reporting
- **Browser/Node Support**: Works in both browser and Node.js environments

#### Usage

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

**Programmatic:**

```javascript
const runner = new TestRunner();

// Add test suites
runner.addTestSuite("Permissions Manager", permissionsTests);
runner.addTestSuite("Share Action Manager", sharingTests);
runner.addTestSuite("Dataset Editing", datasetEditingTests);

// Run all tests
const success = await runner.runAllTests();

// Get results
const results = runner.getResults();
console.log(`Passed: ${results.passed}, Failed: ${results.failed}`);
```

## Writing Tests

### Adding New Tests

To add a new test to an existing suite:

```javascript
// Add test to existing suite
permissionsTests.addTest("New test name", () => {
    // Test implementation
    permissionsTests.assert(condition, "Error message if condition fails");
    permissionsTests.assertEqual(actual, expected, "Error message if values don't match");
});
```

### Creating New Test Suites

To create a new test suite:

```javascript
class NewComponentTests {
    constructor() {
        this.tests = [];
        this.passed = 0;
        this.failed = 0;
    }

    addTest(name, testFn) {
        this.tests.push({ name, testFn });
    }

    async runTests() {
        console.log("Running NewComponent tests...");

        for (const test of this.tests) {
            try {
                await test.testFn();
                console.log(`✓ ${test.name}`);
                this.passed++;
            } catch (error) {
                console.error(`✗ ${test.name}: ${error.message}`);
                this.failed++;
            }
        }

        console.log(`\nTest Results: ${this.passed} passed, ${this.failed} failed`);
        return this.failed === 0;
    }

    assert(condition, message) {
        if (!condition) {
            throw new Error(message);
        }
    }

    assertEqual(actual, expected, message) {
        if (actual !== expected) {
            throw new Error(`${message}. Expected: ${expected}, Actual: ${actual}`);
        }
    }
}

// Create instance
const newComponentTests = new NewComponentTests();

// Add tests
newComponentTests.addTest("Test 1", () => {
    newComponentTests.assert(true, "This test should pass");
});

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = newComponentTests;
} else {
    window.NewComponentTests = newComponentTests;
}
```

### Test Best Practices

#### 1. Test Naming

Use descriptive test names that clearly indicate what is being tested:

```javascript
// Good
permissionsTests.addTest("Owner has all permissions", () => { ... });
permissionsTests.addTest("Contributor cannot remove assets", () => { ... });

// Bad
permissionsTests.addTest("Test 1", () => { ... });
permissionsTests.addTest("Permission test", () => { ... });
```

#### 2. Test Organization

Group related tests together and use clear assertions:

```javascript
// Test multiple related conditions
permissionsTests.addTest("Co-owner has most permissions", () => {
    const permissions = new PermissionsManager({
        userPermissionLevel: "co-owner",
        isOwner: false
    });

    // Test all co-owner permissions
    permissionsTests.assert(permissions.canEditMetadata(), "Co-owner should be able to edit metadata");
    permissionsTests.assert(permissions.canAddAssets(), "Co-owner should be able to add assets");
    permissionsTests.assert(permissions.canRemoveAnyAssets(), "Co-owner should be able to remove any assets");
    permissionsTests.assert(permissions.canRemoveOwnAssets(), "Co-owner should be able to remove their own assets");
    permissionsTests.assert(permissions.canShare(), "Co-owner should be able to share");
    permissionsTests.assert(permissions.canDownload(), "Co-owner should be able to download");
    permissionsTests.assert(permissions.canDelete(), "Co-owner should be able to delete");
    permissionsTests.assert(permissions.canView(), "Co-owner should be able to view");
});
```

#### 3. Mock Objects

Create mock objects for testing:

```javascript
// Create mock ShareActionManager
createMockShareActionManager(config = {}) {
    const defaultConfig = {
        itemUuid: "test-uuid",
        itemType: "dataset",
        permissions: new PermissionsManager({
            userPermissionLevel: "co-owner",
            isOwner: false
        })
    };

    return {
        ...defaultConfig,
        ...config,
        selectedUsersMap: {},
        pendingRemovals: new Set(),
        pendingPermissionChanges: new Map(),

        // Mock methods
        handleShareItem: async function() {
            return { success: true };
        },

        clearSelections: function() {
            this.selectedUsersMap = {};
            this.pendingRemovals.clear();
            this.pendingPermissionChanges.clear();
        }
    };
}
```

#### 4. Error Testing

Test error scenarios:

```javascript
// Test error handling
sharingTests.addTest("Error handling works correctly", async () => {
    const manager = sharingTests.createMockShareActionManager();

    // Mock API error
    const originalAPIClient = global.APIClient;
    global.APIClient.post = async () => {
        throw new Error("Network error");
    };

    try {
        await manager.handleShareItem();
        sharingTests.assert(false, "Should have thrown an error");
    } catch (error) {
        sharingTests.assert(error.message === "Network error", "Should catch the network error");
    } finally {
        // Restore original APIClient
        global.APIClient = originalAPIClient;
    }
});
```

#### 5. Async Testing

Handle asynchronous operations properly:

```javascript
// Test async operations
datasetEditingTests.addTest("Form submission works correctly in creation mode", async () => {
    const handler = datasetEditingTests.createMockDatasetCreationHandler();

    // Mock form submission
    const result = await handler.handleSubmit(new Event("submit"));

    datasetEditingTests.assert(result.success, "Form submission should be successful");
});
```

## Running Tests

### Browser Environment

Tests run automatically when the page loads, or can be run manually:

```javascript
// Manual execution
const runner = new TestRunner();
await runner.runInBrowser();
```

### Node.js Environment

Run tests from the command line:

```bash
# Run all tests
node test-runner.js

# Run specific test file
node test-permissions.js
```

### Integration with Build Process

Add tests to your build process:

```javascript
// In package.json
{
  "scripts": {
    "test": "node test-runner.js",
    "test:permissions": "node test-permissions.js",
    "test:sharing": "node test-sharing.js",
    "test:dataset": "node test-dataset-editing.js"
  }
}
```

### Continuous Integration

For CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Run JavaScript Tests
  run: |
    cd gateway/sds_gateway/static/js/tests
    node test-runner.js
```

## Test Results

### Output Format

Tests provide detailed output including:

```text
Running PermissionsManager tests...
✓ Owner has all permissions
✓ Co-owner has most permissions
✓ Contributor has limited permissions
✓ Viewer has minimal permissions
✓ Asset ownership permissions
✓ Co-owner asset permissions
✓ Permission display names
✓ Permission descriptions
✓ Permission icons
✓ Permission badge classes
✓ Permission hierarchy
✓ Available permission levels
✓ Permission summary
✓ Has any permission
✓ Has all permissions
✓ Update dataset permissions

Test Results: 16 passed, 0 failed

=== Running Share Action Manager ===
✓ Owner can share items
✓ Co-owner can share items
✓ Contributor cannot share items
✓ Viewer cannot share items
✓ ShareActionManager initializes correctly
✓ User selection works correctly
✓ Group selection works correctly
✓ Permission level changes work correctly
✓ User removal works correctly
✓ Clear selections works correctly
✓ Share item with users works correctly
✓ Search users works correctly
✓ User chip creation works correctly
✓ Group chip creation works correctly
✓ Permission level validation works correctly
✓ Multiple user selection works correctly
✓ Duplicate user prevention works correctly
✓ Mixed permission changes and removals work correctly
✓ Share with notification works correctly
✓ Error handling works correctly

Test Results: 20 passed, 0 failed

=== Running Dataset Editing ===
✓ Dataset creation handler initializes correctly
✓ Dataset editing handler initializes correctly
✓ Step navigation works correctly in creation mode
✓ Step validation works correctly in creation mode
✓ Capture selection works correctly in creation mode
✓ File selection works correctly in creation mode
✓ Capture removal works correctly in editing mode
✓ File removal works correctly in editing mode
✓ Capture addition works correctly in editing mode
✓ File addition works correctly in editing mode
✓ Pending changes tracking works correctly
✓ Form submission works correctly in creation mode
✓ Permission-based access control works correctly
✓ Asset ownership validation works correctly
✓ Mixed operations work correctly in editing mode
✓ Error handling works correctly in form submission
✓ Hidden field updates work correctly
✓ Step change callbacks work correctly
✓ Dataset mode detection works correctly
✓ Complex workflow simulation works correctly

Test Results: 20 passed, 0 failed

==================================================
TEST SUMMARY
==================================================
✓ Permissions Manager: 16/16 passed
✓ Share Action Manager: 20/20 passed
✓ Dataset Editing: 20/20 passed

--------------------------------------------------
Total: 56/56 tests passed
🎉 All tests passed!
==================================================
```

### Result Object

The test runner returns a detailed result object:

```javascript
{
    passed: 56,
    failed: 0,
    total: 56,
    suites: [
        {
            name: "Permissions Manager",
            passed: 16,
            failed: 0,
            total: 16,
            success: true
        },
        {
            name: "Share Action Manager",
            passed: 20,
            failed: 0,
            total: 20,
            success: true
        },
        {
            name: "Dataset Editing",
            passed: 20,
            failed: 0,
            total: 20,
            success: true
        }
    ]
}
```

## Troubleshooting

### Common Issues

1. **Tests Not Running**: Ensure all dependencies are loaded
2. **Mock Objects Not Working**: Check mock object implementation
3. **Async Tests Failing**: Verify async/await usage
4. **Permission Tests Failing**: Check PermissionsManager initialization

### Debug Mode

Enable debug logging:

```javascript
window.DEBUG_JS = true;
```

### Test Isolation

Ensure tests are isolated and don't affect each other:

```javascript
// Clean up after each test
afterEach(() => {
    // Reset global state
    global.APIClient = originalAPIClient;
    global.HTMLInjectionManager = originalHTMLInjectionManager;
});
```

## Contributing

When adding new tests:

1. **Follow Naming Conventions**: Use descriptive test names
2. **Group Related Tests**: Organize tests logically
3. **Use Mock Objects**: Create appropriate mocks
4. **Test Edge Cases**: Include error scenarios
5. **Document Complex Tests**: Add comments for complex logic
6. **Maintain Coverage**: Ensure comprehensive test coverage

## Performance

### Test Performance

- **Fast Execution**: Tests run quickly with minimal setup
- **Parallel Execution**: Tests can run in parallel
- **Minimal Dependencies**: Tests use minimal external dependencies
- **Efficient Mocking**: Lightweight mock objects

### Optimization Tips

1. **Use Mocks**: Avoid real API calls in tests
2. **Minimize DOM**: Use minimal DOM manipulation
3. **Batch Operations**: Group related assertions
4. **Clean Up**: Properly clean up after tests
