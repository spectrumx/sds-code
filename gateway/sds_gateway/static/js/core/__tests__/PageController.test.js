/**
 * Jest tests for PageController
 */

import { PageController } from "../PageController.js";

describe("PageController", () => {
	test("bind tracks listeners and unbindAll removes them", () => {
		const ctrl = new PageController();
		const target = document.createElement("button");
		const handler = jest.fn();

		ctrl.bind(target, "click", handler);
		target.click();
		expect(handler).toHaveBeenCalledTimes(1);

		ctrl.unbindAll();
		target.click();
		expect(handler).toHaveBeenCalledTimes(1);
	});

	test("init runs hooks only once", () => {
		class TestController extends PageController {
			cacheElements() {
				this.cached = true;
			}
		}
		const ctrl = new TestController();
		const spy = jest.spyOn(ctrl, "cacheElements");

		ctrl.init();
		ctrl.init();

		expect(spy).toHaveBeenCalledTimes(1);
		expect(ctrl.cached).toBe(true);
	});

	test("initListPage creates lifecycle and list refresh managers", () => {
		window.PageLifecycleManager = jest.fn();
		window.ListRefreshManager = jest.fn();
		window.DOMUtils = { initIconDropdowns: jest.fn() };

		PageController.initListPage({
			pageLifecycleConfig: { itemType: "dataset" },
			listRefreshConfig: { url: "/list/" },
		});

		expect(window.PageLifecycleManager).toHaveBeenCalledWith({
			itemType: "dataset",
		});
		expect(window.ListRefreshManager).toHaveBeenCalledWith({ url: "/list/" });
		expect(window.DOMUtils.initIconDropdowns).toHaveBeenCalled();
	});
});
