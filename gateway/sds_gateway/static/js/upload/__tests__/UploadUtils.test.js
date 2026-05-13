/**
 * @jest-environment jsdom
 */

const { UploadUtils } = require("../UploadUtils.js");

describe("UploadUtils", () => {
	beforeEach(() => {
		document.body.innerHTML = "";
	});

	test("calculateTotalChunks counts byte-sized groups", () => {
		const chunkSize = 10;
		const files = [
			new File(["x"], "a.bin", { type: "application/octet-stream" }),
			new File(["yy"], "b.bin", { type: "application/octet-stream" }),
		];
		Object.defineProperty(files[0], "size", { value: 6 });
		Object.defineProperty(files[1], "size", { value: 6 });

		expect(UploadUtils.calculateTotalChunks(files, chunkSize)).toBe(2);
	});

	test("calculateTotalChunks splits oversized single file", () => {
		const chunkSize = 5;
		const files = [
			new File(["xxxxxxx"], "big.bin", { type: "application/octet-stream" }),
		];
		Object.defineProperty(files[0], "size", { value: 100 });

		expect(UploadUtils.calculateTotalChunks(files, chunkSize)).toBe(1);
	});

	test("appendCaptureTypeToFormData reads modal fields", () => {
		document.body.innerHTML = `
			<select id="captureTypeSelect"><option value="drf" selected>drf</option></select>
			<input id="captureChannelsInput" value="ch1,ch2" />
			<input id="captureScanGroupInput" value="" />
		`;
		const fd = new FormData();
		UploadUtils.appendCaptureTypeToFormData(fd);
		expect(fd.get("capture_type")).toBe("drf");
		expect(fd.get("channels")).toBe("ch1,ch2");
	});

	test("appendCaptureTypeToFormData appends scan_group for rh", () => {
		document.body.innerHTML = `
			<select id="captureTypeSelect"><option value="rh" selected>rh</option></select>
			<input id="captureChannelsInput" value="" />
			<input id="captureScanGroupInput" value="sg-1" />
		`;
		const fd = new FormData();
		UploadUtils.appendCaptureTypeToFormData(fd);
		expect(fd.get("capture_type")).toBe("rh");
		expect(fd.get("scan_group")).toBe("sg-1");
	});
});
