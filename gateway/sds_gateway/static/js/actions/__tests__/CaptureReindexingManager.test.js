/**
 * Jest tests for CaptureReindexingManager
 */

import { CaptureReindexingManager } from "../CaptureReindexingManager.js";

function installReindexModalDom() {
	document.body.innerHTML = `
		<button type="button" class="reindex-capture-btn"
			data-capture-uuid="cap-1"
			data-capture-name="My Capture"
			data-top-level-dir="/drf/foo"></button>
		<div id="reindexCaptureModal"
			data-preview-url-template="/users/captures/00000000-0000-0000-0000-000000000000/reindex-preview/">
			<span id="reindex-capture-name"></span>
			<span id="reindex-top-level-dir"></span>
			<div id="reindex-loading" class="d-none"></div>
			<div id="reindex-empty-hint" class="d-none"></div>
			<div id="reindex-pending-section" class="d-none"></div>
			<tbody id="reindex-pending-tbody"></tbody>
			<div id="reindex-progress" class="d-none"></div>
			<div id="reindex-message" class="d-none"></div>
			<button id="reindex-confirm-btn"></button>
		</div>
	`;
}

describe("CaptureReindexingManager", () => {
	beforeEach(() => {
		jest.clearAllMocks();
		installReindexModalDom();
		window.DOMUtils = {
			toggleHidden: jest.fn((el, hidden) => {
				el?.classList?.toggle("d-none", hidden);
			}),
			renderLoading: jest.fn().mockResolvedValue(true),
			renderProgress: jest.fn().mockResolvedValue(true),
			formatFileSize: jest.fn((n) => `${n} bytes`),
		};
		window.APIClient = {
			get: jest.fn(),
			put: jest.fn().mockResolvedValue({}),
			getCSRFToken: jest.fn(() => "csrf"),
		};
		window.listRefreshManager = { loadTable: jest.fn().mockResolvedValue("") };
		window.bootstrap = {
			Modal: jest.fn().mockImplementation(() => ({
				show: jest.fn(),
				hide: jest.fn(),
			})),
		};
	});

	test("buildPreviewUrl substitutes capture uuid", () => {
		const mgr = new CaptureReindexingManager();
		expect(mgr.buildPreviewUrl("abc-123")).toBe(
			"/users/captures/abc-123/reindex-preview/",
		);
	});

	test("renderPendingList shows empty hint when no pending files", () => {
		const mgr = new CaptureReindexingManager();
		mgr.renderPendingList([]);
		expect(window.DOMUtils.toggleHidden).toHaveBeenCalledWith(
			document.getElementById("reindex-empty-hint"),
			false,
		);
	});

	test("confirmReindex PUTs capture update via APIClient", async () => {
		const mgr = new CaptureReindexingManager();
		mgr.currentCaptureUuid = "cap-uuid-9";
		mgr.modalEl = document.getElementById("reindexCaptureModal");
		mgr.showToast = jest.fn();

		await mgr.confirmReindex();

		expect(window.APIClient.put).toHaveBeenCalledWith(
			"/api/v1/assets/captures/cap-uuid-9/",
			{},
		);
	});
});
