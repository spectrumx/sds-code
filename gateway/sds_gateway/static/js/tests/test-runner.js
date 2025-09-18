/**
 * Test Runner for JavaScript Components
 * Runs all tests and provides results
 */

class TestRunner {
	constructor() {
		this.testSuites = [];
		this.results = {
			passed: 0,
			failed: 0,
			total: 0,
			suites: [],
		};
	}

	/**
	 * Add a test suite
	 * @param {string} name - Test suite name
	 * @param {Object} testSuite - Test suite instance
	 */
	addTestSuite(name, testSuite) {
		this.testSuites.push({ name, testSuite });
	}

	/**
	 * Run all test suites
	 */
	async runAllTests() {
		console.log("Starting JavaScript Component Tests...\n");

		for (const { name, testSuite } of this.testSuites) {
			console.log(`\n=== Running ${name} ===`);

			try {
				const success = await testSuite.runTests();

				this.results.suites.push({
					name,
					passed: testSuite.passed,
					failed: testSuite.failed,
					total: testSuite.passed + testSuite.failed,
					success,
				});

				this.results.passed += testSuite.passed;
				this.results.failed += testSuite.failed;
				this.results.total += testSuite.passed + testSuite.failed;
			} catch (error) {
				console.error(`Error running ${name}:`, error);
				this.results.suites.push({
					name,
					passed: 0,
					failed: 1,
					total: 1,
					success: false,
					error: error.message,
				});
				this.results.failed++;
				this.results.total++;
			}
		}

		this.printSummary();
		return this.results.failed === 0;
	}

	/**
	 * Print test summary
	 */
	printSummary() {
		console.log("\n" + "=".repeat(50));
		console.log("TEST SUMMARY");
		console.log("=".repeat(50));

		for (const suite of this.results.suites) {
			const status = suite.success ? "✓" : "✗";
			console.log(
				`${status} ${suite.name}: ${suite.passed}/${suite.total} passed`,
			);
			if (suite.error) {
				console.log(`  Error: ${suite.error}`);
			}
		}

		console.log("\n" + "-".repeat(50));
		console.log(
			`Total: ${this.results.passed}/${this.results.total} tests passed`,
		);

		if (this.results.failed === 0) {
			console.log("🎉 All tests passed!");
		} else {
			console.log(`❌ ${this.results.failed} test(s) failed`);
		}

		console.log("=".repeat(50));
	}

	/**
	 * Get test results
	 * @returns {Object} Test results
	 */
	getResults() {
		return this.results;
	}

	/**
	 * Run tests in Node.js environment
	 */
	async runInNode() {
		// Load test suites
		try {
			const permissionsTests = require("./test-permissions.js");
			this.addTestSuite("Permissions Manager", permissionsTests);
		} catch (error) {
			console.warn("Could not load permissions tests:", error.message);
		}

		try {
			const sharingTests = require("./test-sharing.js");
			this.addTestSuite("Share Action Manager", sharingTests);
		} catch (error) {
			console.warn("Could not load sharing tests:", error.message);
		}

		try {
			const datasetEditingTests = require("./test-dataset-editing.js");
			this.addTestSuite("Dataset Editing", datasetEditingTests);
		} catch (error) {
			console.warn("Could not load dataset editing tests:", error.message);
		}

		try {
			const DownloadFunctionalityTests = require("./test-download-functionality.js");
			const downloadTests = new DownloadFunctionalityTests();
			downloadTests.setupTests();
			this.addTestSuite("Download Functionality", downloadTests);
		} catch (error) {
			console.warn(
				"Could not load download functionality tests:",
				error.message,
			);
		}

		try {
			const DetailsFunctionalityTests = require("./test-details-functionality.js");
			const detailsTests = new DetailsFunctionalityTests();
			detailsTests.setupTests();
			this.addTestSuite("Details Functionality", detailsTests);
		} catch (error) {
			console.warn(
				"Could not load details functionality tests:",
				error.message,
			);
		}

		// Run all tests
		return await this.runAllTests();
	}
}

// Export for Node.js
if (typeof module !== "undefined" && module.exports) {
	module.exports = TestRunner;

	// Auto-run tests if this file is executed directly in Node.js
	if (require.main === module) {
		(async () => {
			const runner = new TestRunner();
			const results = await runner.runInNode();

			// Exit with appropriate code
			const exitCode = results.failed > 0 ? 1 : 0;
			process.exit(exitCode);
		})();
	}
} else {
	window.TestRunner = TestRunner;
}
