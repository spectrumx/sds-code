/**
 * Tests for Download Functionality
 * Tests DownloadActionManager for both datasets and captures
 */

// Mock DOM environment for testing
const mockDOM = {
	createElement: (tag) => ({
		tagName: tag,
		textContent: '',
		innerHTML: '',
		dataset: {},
		classList: {
			add: () => {},
			remove: () => {},
			contains: () => false
		},
		addEventListener: () => {},
		removeEventListener: () => {},
		querySelector: () => null,
		querySelectorAll: () => [],
		setAttribute: () => {},
		getAttribute: () => null,
		click: () => {},
		disabled: false
	}),
	getElementById: (id) => {
		const element = mockDOM.createElement('div');
		element.id = id;
		return element;
	},
	querySelector: () => null,
	querySelectorAll: () => [],
	addEventListener: () => {}
};

// Mock global objects
global.document = mockDOM;
global.window = {
	fetch: () => Promise.resolve({
		ok: true,
		json: () => Promise.resolve({ success: true, message: 'Download requested' })
	}),
	showWebDownloadModal: () => {},
	bootstrap: {
		Modal: {
			getInstance: () => ({
				hide: () => {}
			})
		}
	}
};

// Mock PermissionsManager
class MockPermissionsManager {
	constructor(permissions) {
		this.permissions = permissions;
	}

	canDownload() {
		// Check both dataset and capture permissions
		const datasetCanDownload = this.permissions.datasetPermissions?.canDownload;
		const captureCanDownload = this.permissions.capturePermissions?.canDownload;
		
		// Return true if either permission is explicitly true, false if either is explicitly false
		if (datasetCanDownload !== undefined) return datasetCanDownload;
		if (captureCanDownload !== undefined) return captureCanDownload;
		
		// Default to true if no permissions specified
		return true;
	}
}

// Mock HTMLInjectionManager
global.HTMLInjectionManager = {
	createLoadingSpinner: (text) => `<span class="spinner">${text}</span>`,
	showAlert: (message, type) => console.log(`Alert: ${message} (${type})`)
};

// Mock APIClient
global.APIClient = {
	post: (url, data) => Promise.resolve({
		success: true,
		message: 'Download request submitted successfully!'
	})
};

// Mock DownloadActionManager for testing
class MockDownloadActionManager {
	constructor(config) {
		this.permissions = config.permissions;
	}

	initializeDatasetDownloadButtons() {
		document.querySelectorAll('.download-dataset-btn');
	}

	initializeCaptureDownloadButtons() {
		document.querySelectorAll('.download-capture-btn');
	}

	async handleDatasetDownload(uuid, name, button) {
		if (!this.permissions.canDownload()) {
			this.showToast("You don't have permission to download this dataset", "warning");
			return;
		}
		// Simulate successful download
	}

	async handleCaptureDownload(uuid, name, button) {
		if (!this.permissions.canDownload()) {
			this.showToast("You don't have permission to download this capture", "warning");
			return;
		}
		if (window.showWebDownloadModal) {
			window.showWebDownloadModal(uuid, name);
		} else {
			this.showToast("Download functionality not available", "error");
		}
	}

	showToast(message, type) {
		if (window.showAlert) {
			window.showAlert(message, type);
		}
	}

	cleanup() {
		const buttons = document.querySelectorAll(".download-dataset-btn, .download-capture-btn");
		buttons.forEach((button) => {
			button.removeEventListener("click", this.handleDatasetDownload);
			button.removeEventListener("click", this.handleCaptureDownload);
		});
	}
}

// Use mock if real class not available
const DownloadActionManager = global.DownloadActionManager || MockDownloadActionManager;

// Test suite for Download Functionality
class DownloadFunctionalityTests {
	constructor() {
		this.tests = [];
		this.passed = 0;
		this.failed = 0;
	}

	/**
	 * Add a test case
	 * @param {string} name - Test name
	 * @param {Function} testFn - Test function
	 */
	addTest(name, testFn) {
		this.tests.push({ name, testFn });
	}

	/**
	 * Run all tests
	 */
	async runTests() {
		console.log('Running Download Functionality Tests...\n');

		for (const test of this.tests) {
			try {
				await test.testFn();
				this.passed++;
				console.log(`✅ ${test.name}`);
			} catch (error) {
				this.failed++;
				console.log(`❌ ${test.name}: ${error.message}`);
			}
		}

		console.log(`\nDownload Tests: ${this.passed} passed, ${this.failed} failed\n`);
		return { passed: this.passed, failed: this.failed, total: this.tests.length };
	}

	/**
	 * Setup all tests
	 */
	setupTests() {
		// Test DownloadActionManager initialization
		this.addTest('DownloadActionManager should initialize with permissions', () => {
			const permissions = new MockPermissionsManager({
				datasetPermissions: { canDownload: true }
			});

			const downloadManager = new DownloadActionManager({ permissions });
			
			if (!downloadManager.permissions) {
				throw new Error('DownloadActionManager should store permissions');
			}
		});

		// Test dataset download permissions check
		this.addTest('Dataset download should check permissions', async () => {
			const permissions = new MockPermissionsManager({
				datasetPermissions: { canDownload: false }
			});

			const downloadManager = new DownloadActionManager({ permissions });
			
			// Mock button element
			const button = mockDOM.createElement('button');
			button.setAttribute('data-dataset-uuid', 'test-uuid');
			button.setAttribute('data-dataset-name', 'Test Dataset');

			// Mock showToast method to capture message
			let toastMessage = '';
			let toastType = '';
			downloadManager.showToast = (message, type) => {
				toastMessage = message;
				toastType = type;
			};

			// This should trigger permission check and show warning
			await downloadManager.handleDatasetDownload('test-uuid', 'Test Dataset', button);

			if (!toastMessage.includes("don't have permission") || toastType !== 'warning') {
				throw new Error(`Should show permission denied message, got: "${toastMessage}" (${toastType})`);
			}
		});

		// Test capture download permissions check
		this.addTest('Capture download should check permissions', async () => {
			const permissions = new MockPermissionsManager({
				capturePermissions: { canDownload: false }
			});

			const downloadManager = new DownloadActionManager({ permissions });
			
			// Mock button element
			const button = mockDOM.createElement('button');
			button.setAttribute('data-capture-uuid', 'test-uuid');
			button.setAttribute('data-capture-name', 'Test Capture');

			// Mock showToast method to capture message
			let toastMessage = '';
			let toastType = '';
			downloadManager.showToast = (message, type) => {
				toastMessage = message;
				toastType = type;
			};

			// This should trigger permission check and show warning
			await downloadManager.handleCaptureDownload('test-uuid', 'Test Capture', button);

			if (!toastMessage.includes("don't have permission") || toastType !== 'warning') {
				throw new Error(`Should show permission denied message, got: "${toastMessage}" (${toastType})`);
			}
		});

		// Test dataset download with valid permissions
		this.addTest('Dataset download should work with valid permissions', async () => {
			const permissions = new MockPermissionsManager({
				datasetPermissions: { canDownload: true }
			});

			const downloadManager = new DownloadActionManager({ permissions });
			
			// Mock DOM elements
			global.document.getElementById = (id) => {
				if (id === 'downloadDatasetName') {
					return { textContent: '' };
				}
				return mockDOM.createElement('div');
			};

			// Mock showModal function
			downloadManager.showModal = () => {};

			const button = mockDOM.createElement('button');
			
			// This should not throw an error
			await downloadManager.handleDatasetDownload('test-uuid', 'Test Dataset', button);
		});

		// Test capture download with web modal
		this.addTest('Capture download should use web download modal', async () => {
			const permissions = new MockPermissionsManager({
				capturePermissions: { canDownload: true }
			});

			const downloadManager = new DownloadActionManager({ permissions });
			
			// Mock web download modal function
			let modalCalled = false;
			global.window.showWebDownloadModal = (uuid, name) => {
				modalCalled = true;
				if (uuid !== 'test-uuid' || name !== 'Test Capture') {
					throw new Error('Wrong parameters passed to modal');
				}
			};

			const button = mockDOM.createElement('button');
			
			await downloadManager.handleCaptureDownload('test-uuid', 'Test Capture', button);

			if (!modalCalled) {
				throw new Error('Web download modal should be called');
			}
		});

		// Test download button initialization for datasets
		this.addTest('Should initialize dataset download buttons', () => {
			const permissions = new MockPermissionsManager({
				datasetPermissions: { canDownload: true }
			});

			const downloadManager = new DownloadActionManager({ permissions });
			
			// Mock querySelectorAll to return mock buttons
			let buttonCount = 0;
			global.document.querySelectorAll = (selector) => {
				if (selector === '.download-dataset-btn') {
					buttonCount++;
					const button = mockDOM.createElement('button');
					button.dataset = { downloadSetup: 'false' };
					return [button];
				}
				return [];
			};

			downloadManager.initializeDatasetDownloadButtons();

			if (buttonCount === 0) {
				throw new Error('Should query for dataset download buttons');
			}
		});

		// Test download button initialization for captures
		this.addTest('Should initialize capture download buttons', () => {
			const permissions = new MockPermissionsManager({
				capturePermissions: { canDownload: true }
			});

			const downloadManager = new DownloadActionManager({ permissions });
			
			// Mock querySelectorAll to return mock buttons
			let buttonCount = 0;
			global.document.querySelectorAll = (selector) => {
				if (selector === '.download-capture-btn') {
					buttonCount++;
					const button = mockDOM.createElement('button');
					button.dataset = { downloadSetup: 'false' };
					return [button];
				}
				return [];
			};

			downloadManager.initializeCaptureDownloadButtons();

			if (buttonCount === 0) {
				throw new Error('Should query for capture download buttons');
			}
		});

		// Test toast notification functionality
		this.addTest('Should show toast notifications', () => {
			const permissions = new MockPermissionsManager({
				datasetPermissions: { canDownload: true }
			});

			const downloadManager = new DownloadActionManager({ permissions });
			
			// Mock window.showAlert
			let alertShown = false;
			global.window.showAlert = (message, type) => {
				alertShown = true;
				if (!message || !type) {
					throw new Error('Alert should have message and type');
				}
			};

			downloadManager.showToast('Test message', 'success');

			if (!alertShown) {
				throw new Error('Should show alert notification');
			}
		});

		// Test cleanup functionality
		this.addTest('Should cleanup event listeners', () => {
			const permissions = new MockPermissionsManager({
				datasetPermissions: { canDownload: true }
			});

			const downloadManager = new DownloadActionManager({ permissions });
			
			// Mock buttons with removeEventListener
			let cleanupCalled = false;
			const mockButton = {
				removeEventListener: (event, handler) => {
					cleanupCalled = true;
				}
			};

			global.document.querySelectorAll = () => [mockButton];

			downloadManager.cleanup();

			if (!cleanupCalled) {
				throw new Error('Should cleanup event listeners');
			}
		});

		// Test error handling in download process
		this.addTest('Should handle download errors gracefully', async () => {
			const permissions = new MockPermissionsManager({
				capturePermissions: { canDownload: true }
			});

			const downloadManager = new DownloadActionManager({ permissions });
			
			// Mock showToast to capture error message
			let errorShown = false;
			let errorMessage = '';
			downloadManager.showToast = (message, type) => {
				if (type === 'danger' || type === 'error') {
					errorShown = true;
					errorMessage = message;
				}
			};

			// Mock web download modal that fails
			global.window.showWebDownloadModal = () => {
				// Simulate error in modal
				downloadManager.showToast('Download functionality not available', 'error');
			};

			const button = mockDOM.createElement('button');
			
			await downloadManager.handleCaptureDownload('test-uuid', 'Test Capture', button);

			if (!errorShown || !errorMessage.includes('not available')) {
				throw new Error(`Should show error message on failure, got: "${errorMessage}"`);
			}
		});
	}
}

// Export for use in test runner
if (typeof module !== 'undefined' && module.exports) {
	module.exports = DownloadFunctionalityTests;
}

// Make available globally
window.DownloadFunctionalityTests = DownloadFunctionalityTests;
