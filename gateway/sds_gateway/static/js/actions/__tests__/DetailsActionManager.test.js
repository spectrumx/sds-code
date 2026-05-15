/**
 * Jest tests for DetailsActionManager
 */

import "../../constants/PermissionLevels.js";
import { PermissionsManager } from "../../core/PermissionsManager.js";
import { DetailsActionManager } from "../DetailsActionManager.js";

describe("DetailsActionManager", () => {
	beforeEach(() => {
		jest.clearAllMocks();
		global.window.DOMUtils = {
			renderLoading: jest.fn().mockResolvedValue(true),
			renderContent: jest.fn().mockResolvedValue(true),
		};
		global.window.bootstrap = {
			Tooltip: jest.fn(function MockTooltip() {
				this.dispose = jest.fn();
			}),
		};
		global.window.bootstrap.Tooltip.getInstance = jest.fn(() => null);
		global.navigator.clipboard = { writeText: jest.fn().mockResolvedValue(undefined) };
	});

	test("initializes with permissions only", () => {
		const permissions = new PermissionsManager({
			userPermissionLevel: "owner",
			isOwner: true,
			datasetPermissions: { canEditMetadata: true },
		});
		const mgr = new DetailsActionManager({ permissions });
		expect(mgr.permissions).toBe(permissions);
	});

	test("showModalLoading delegates to DOMUtils", async () => {
		const permissions = new PermissionsManager({
			userPermissionLevel: "owner",
			isOwner: true,
			datasetPermissions: { canEditMetadata: true },
		});
		const mgr = new DetailsActionManager({ permissions });
		const modalBody = { dataset: {}, innerHTML: "" };
		document.getElementById = jest.fn((id) =>
			id === "m1" ? { querySelector: () => modalBody } : null,
		);
		await mgr.showModalLoading("m1");
		expect(global.window.DOMUtils.renderLoading).toHaveBeenCalledWith(
			modalBody,
			"Loading details...",
			expect.any(Object),
		);
	});

	test("attachUuidCopyButton wires click handler", () => {
		const btn = document.createElement("button");
		btn.className = "copy-uuid-btn";
		const modal = document.createElement("div");
		modal.appendChild(btn);
		document.body.appendChild(modal);

		DetailsActionManager.attachUuidCopyButton(modal, "u1");
		modal.querySelector(".copy-uuid-btn").click();
		expect(global.navigator.clipboard.writeText).toHaveBeenCalledWith("u1");

		document.body.removeChild(modal);
	});
});
