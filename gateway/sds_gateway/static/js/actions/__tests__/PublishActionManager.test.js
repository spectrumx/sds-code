/**
 * Jest tests for PublishActionManager
 * Tests publish functionality for datasets
 */

// Import the PublishActionManager class
import { PublishActionManager } from "../PublishActionManager.js";

describe("PublishActionManager", () => {
	let publishManager;
	let mockAPIClient;
	let mockStatusBadge;
	let mockPublishToggle;
	let mockPublicOption;
	let mockPrivateOption;

	beforeEach(() => {
		mockAPIClient = {
			post: jest.fn(),
		};
		window.APIClient = mockAPIClient;

		mockStatusBadge = {
			textContent: "Draft",
			className: "badge bg-secondary",
		};

		mockPublishToggle = { checked: true };
		mockPublicOption = { checked: true };
		mockPrivateOption = { checked: false };

		document.getElementById = jest.fn((id) => {
			if (id === "publishDatasetBtn-test-uuid") {
				return {
					disabled: false,
					innerHTML: "Publish",
				};
			}
			if (id === "publish-dataset-modal-test-uuid") {
				return { id: "publish-dataset-modal-test-uuid" };
			}
			return null;
		});

		global.bootstrap = {
			Modal: {
				getInstance: jest.fn(() => ({
					hide: jest.fn(),
				})),
			},
		};

		window.DOMUtils = {
			showMessage: jest.fn(),
		};

		window.location = { reload: jest.fn() };

		publishManager = new PublishActionManager();
	});

	test("should publish dataset as final and public when toggle is checked", async () => {
		mockAPIClient.post.mockResolvedValue({
			success: true,
			message: "Dataset published successfully",
		});

		await publishManager.handlePublish(
			"test-uuid",
			mockStatusBadge,
			mockPublishToggle,
			mockPrivateOption,
			mockPublicOption,
		);

		expect(mockAPIClient.post).toHaveBeenCalledWith(
			"/users/publish-dataset/test-uuid/",
			{
				status: "final",
				is_public: "true",
			},
		);
		expect(window.DOMUtils.showMessage).toHaveBeenCalledWith(
			"Dataset published successfully",
			expect.objectContaining({
				variant: "success",
				placement: "toast",
				presentation: "toast",
			}),
		);
	});

	test("should publish dataset as draft and private when toggle is unchecked", async () => {
		mockPublishToggle.checked = false;
		mockPublicOption.checked = false;
		mockPrivateOption.checked = true;

		mockAPIClient.post.mockResolvedValue({
			success: true,
		});

		await publishManager.handlePublish(
			"test-uuid",
			mockStatusBadge,
			mockPublishToggle,
			mockPrivateOption,
			mockPublicOption,
		);

		expect(mockAPIClient.post).toHaveBeenCalledWith(
			"/users/publish-dataset/test-uuid/",
			{
				status: "draft",
				is_public: "false",
			},
		);
	});

	test("should handle API errors gracefully", async () => {
		mockAPIClient.post.mockResolvedValue({
			success: false,
			error: "Validation failed",
		});

		const publishBtn = document.getElementById("publishDatasetBtn-test-uuid");

		await publishManager.handlePublish(
			"test-uuid",
			mockStatusBadge,
			mockPublishToggle,
			mockPrivateOption,
			mockPublicOption,
		);

		expect(window.DOMUtils.showMessage).toHaveBeenCalledWith(
			"Validation failed",
			expect.objectContaining({
				variant: "danger",
				placement: "toast",
				presentation: "toast",
			}),
		);
		expect(publishBtn.disabled).toBe(false);
		expect(publishBtn.innerHTML).toBe("Publish");
	});

	test("should reload page after successful publish", async () => {
		jest.useFakeTimers();
		const reloadMock = jest.fn();
		Object.defineProperty(window, "location", {
			value: { reload: reloadMock },
			writable: true,
			configurable: true,
		});
		mockAPIClient.post.mockResolvedValue({
			success: true,
			message: "Published",
		});
		publishManager.closeModal = jest.fn();

		await publishManager.handlePublish(
			"test-uuid",
			mockStatusBadge,
			mockPublishToggle,
			mockPrivateOption,
			mockPublicOption,
		);

		expect(publishManager.closeModal).toHaveBeenCalledWith(
			"publish-dataset-modal-test-uuid",
		);
		expect(reloadMock).not.toHaveBeenCalled();

		jest.advanceTimersByTime(1000);
		expect(reloadMock).toHaveBeenCalledTimes(1);
		jest.useRealTimers();
	});
});
