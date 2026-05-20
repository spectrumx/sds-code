const {
	formatQuickAddSummary,
	postQuickAddCapture,
} = require("../quickAdd/quickAddApi.js");

describe("quickAddApi", () => {
	test("formatQuickAddSummary builds message parts", () => {
		expect(formatQuickAddSummary(2, 1, 0, null)).toBe(
			"2 added, 1 already in dataset.",
		);
		expect(formatQuickAddSummary(0, 0, 1, "Network error")).toBe(
			"1 failed, : Network error.",
		);
	});

	test("postQuickAddCapture maps APIClient response", async () => {
		global.APIClient = {
			post: jest.fn().mockResolvedValue({
				success: true,
				added: [{ id: 1 }],
				skipped: [],
				errors: [],
			}),
		};
		const result = await postQuickAddCapture("/quick-add/", "ds-1", "cap-1");
		expect(result.success).toBe(true);
		expect(result.added).toBe(1);
	});
});
