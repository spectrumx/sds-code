module.exports = {
	// Root directory for tests (project root where package.json is located)
	rootDir: "../../../..",

	// Test environment
	testEnvironment: "jsdom",

	// Test file patterns
	testMatch: [
		"**/sds_gateway/static/js/**/*.test.js",
		"**/sds_gateway/static/js/**/*.spec.js",
		"**/sds_gateway/static/js/tests/**/*.js",
	],

	// Files to collect coverage from
	collectCoverageFrom: [
		"sds_gateway/static/js/**/*.js",
		"!sds_gateway/static/js/tests/**",
		"!sds_gateway/static/js/**/*.test.js",
		"!sds_gateway/static/js/**/*.spec.js",
		"!sds_gateway/static/js/**/node_modules/**",
		// Exclude deprecated directory
		"!sds_gateway/static/js/deprecated/**",
		// Exclude specific legacy files
		"!sds_gateway/static/js/components.js",
		"!sds_gateway/static/js/file_list_upload_capture_modal.js",
		"!sds_gateway/static/js/file-list.js",
		"!sds_gateway/static/js/file-manager.js",
		"!sds_gateway/static/js/files-ui.js",
		"!sds_gateway/static/js/vendors.js",
		"!sds_gateway/static/js/files-upload.js",
		"!sds_gateway/static/js/theme.js",
	],

	// Coverage thresholds
	coverageThreshold: {
		global: {
			branches: 70,
			functions: 70,
			lines: 70,
			statements: 70,
		},
	},

	// Coverage reporters
	coverageReporters: ["text", "html", "lcov"],

	// Coverage directory
	coverageDirectory: "./.coverage",

	// Setup files
	setupFilesAfterEnv: [
		"<rootDir>/sds_gateway/static/js/tests-config/jest.setup.js",
	],

	// Module name mapping for imports
	moduleNameMapper: {
		"^@/(.*)$": "<rootDir>/sds_gateway/static/js/$1",
	},

	// Transform files
	transform: {
		"^.+\\.js$": "babel-jest",
	},

	// Transform ignore patterns
	transformIgnorePatterns: ["node_modules/(?!(regenerator-runtime)/)"],

	// Ignore patterns
	testPathIgnorePatterns: ["/node_modules/", "/coverage/", "/staticfiles/"],

	// Verbose output
	verbose: true,

	// Clear mocks between tests
	clearMocks: true,

	// Restore mocks between tests
	restoreMocks: true,
};
