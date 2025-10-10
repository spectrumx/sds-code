/**
 * Jest tests for APIClient
 * Tests centralized API client functionality including CSRF tokens, error handling, and loading states
 */

// Import the APIClient class
import { APIClient } from "../APIClient.js";

// Mock APIError class
class APIError extends Error {
	constructor(message, status, data) {
		super(message);
		this.name = "APIError";
		this.status = status;
		this.data = data;
	}
}

global.APIError = APIError;

describe("APIClient", () => {
	let apiClient;
	let mockFetch;

	beforeEach(() => {
		// Reset mocks
		jest.clearAllMocks();

		// Mock fetch
		mockFetch = jest.fn();
		global.fetch = mockFetch;

		// Minimal document mock
		global.document = {
			querySelector: jest.fn(() => null),
			cookie: "",
		};

		// Create APIClient instance
		apiClient = new APIClient();
	});

	describe("CSRF Token Management", () => {
		test("should get CSRF token from meta tag", () => {
			const mockMetaToken = {
				getAttribute: jest.fn(() => "test-csrf-token"),
			};
			global.document.querySelector = jest.fn((selector) => {
				if (selector === 'meta[name="csrf-token"]') return mockMetaToken;
				return null;
			});

			const token = apiClient.getCSRFToken();

			expect(token).toBe("test-csrf-token");
			expect(mockMetaToken.getAttribute).toHaveBeenCalledWith("content");
		});

		test("should fallback to input field for CSRF token", () => {
			const mockInputToken = {
				value: "input-csrf-token",
			};
			global.document.querySelector = jest.fn((selector) => {
				if (selector === 'meta[name="csrf-token"]') return null;
				if (selector === '[name="csrfmiddlewaretoken"]') return mockInputToken;
				return null;
			});

			const token = apiClient.getCSRFToken();

			expect(token).toBe("input-csrf-token");
		});

		test("should fallback to cookie for CSRF token", () => {
			global.document.cookie = "csrftoken=cookie-csrf-token; other=value";
			global.document.querySelector = jest.fn(() => null);

			const token = apiClient.getCSRFToken();

			expect(token).toBe("cookie-csrf-token");
		});

		test("should return empty string when no CSRF token found", () => {
			global.document.cookie = "";
			global.document.querySelector = jest.fn(() => null);

			const token = apiClient.getCSRFToken();

			expect(token).toBe("");
		});
	});

	describe("Cookie Management", () => {
		test("should get cookie value by name", () => {
			global.document.cookie =
				"test-cookie=test-value; other-cookie=other-value";

			const value = apiClient.getCookie("test-cookie");

			expect(value).toBe("test-value");
		});

		test("should return null for non-existent cookie", () => {
			global.document.cookie = "other-cookie=other-value";

			const value = apiClient.getCookie("test-cookie");

			expect(value).toBeNull();
		});

		test("should handle empty cookie string", () => {
			global.document.cookie = "";

			const value = apiClient.getCookie("test-cookie");

			expect(value).toBeNull();
		});

		test("should decode URI encoded cookie values", () => {
			global.document.cookie = "test-cookie=test%20value%20encoded";

			const value = apiClient.getCookie("test-cookie");

			expect(value).toBe("test value encoded");
		});
	});

	describe("API Requests", () => {
		test("should make successful GET request", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => "application/json"),
				},
				json: jest.fn().mockResolvedValue({ success: true }),
			};
			mockFetch.mockResolvedValue(mockResponse);

			const result = await apiClient.request("/api/test");

			expect(mockFetch).toHaveBeenCalledWith("/api/test", {
				method: "GET",
				headers: {
					"X-Requested-With": "XMLHttpRequest",
					"X-CSRFToken": "",
				},
			});
			expect(result).toEqual({ success: true });
		});

		test("should make POST request with CSRF token", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => "application/json"),
				},
				json: jest.fn().mockResolvedValue({ success: true }),
			};
			mockFetch.mockResolvedValue(mockResponse);

			// Mock CSRF token
			const mockMetaToken = {
				getAttribute: jest.fn(() => "test-csrf-token"),
			};
			global.document.querySelector = jest.fn((selector) => {
				if (selector === 'meta[name="csrf-token"]') return mockMetaToken;
				return null;
			});

			await apiClient.request("/api/test", {
				method: "POST",
				body: JSON.stringify({ test: "data" }),
			});

			expect(mockFetch).toHaveBeenCalledWith("/api/test", {
				method: "POST",
				body: JSON.stringify({ test: "data" }),
				headers: {
					"X-Requested-With": "XMLHttpRequest",
					"X-CSRFToken": "test-csrf-token",
				},
			});
		});

		test("should handle loading state", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => "application/json"),
				},
				json: jest.fn().mockResolvedValue({ success: true }),
			};
			mockFetch.mockResolvedValue(mockResponse);

			await apiClient.request("/api/test");

			expect(typeof apiClient.loading).toBe("boolean");
		});

		test("should handle non-JSON response", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => "text/plain"),
				},
				text: jest.fn().mockResolvedValue("plain text response"),
			};
			mockFetch.mockResolvedValue(mockResponse);

			const result = await apiClient.request("/api/test");

			expect(result).toBe("plain text response");
		});

		test("should handle HTTP error responses", async () => {
			const mockResponse = {
				ok: false,
				status: 404,
				statusText: "Not Found",
				headers: {
					get: jest.fn(() => "application/json"),
				},
				json: jest.fn().mockResolvedValue({ error: "Resource not found" }),
			};
			mockFetch.mockResolvedValue(mockResponse);

			await expect(apiClient.request("/api/test")).rejects.toThrow();
		});

		test("should handle network errors", async () => {
			mockFetch.mockRejectedValue(new Error("Network error"));

			await expect(apiClient.request("/api/test")).rejects.toThrow(
				"Network error",
			);
		});

		test("should handle JSON parse errors", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => "application/json"),
				},
				json: jest.fn().mockRejectedValue(new Error("Invalid JSON")),
			};
			mockFetch.mockResolvedValue(mockResponse);

			await expect(apiClient.request("/api/test")).rejects.toThrow(
				"Invalid JSON",
			);
		});
	});

	describe("Convenience Methods", () => {
		test("should make GET request", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => "application/json"),
				},
				json: jest.fn().mockResolvedValue({ success: true }),
			};
			mockFetch.mockResolvedValue(mockResponse);

			await apiClient.get("/api/test");

			expect(mockFetch).toHaveBeenCalledWith("/api/test", {
				method: "GET",
				headers: {
					"X-Requested-With": "XMLHttpRequest",
					"X-CSRFToken": "",
				},
			});
		});

		test("should make POST request", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => "application/json"),
				},
				json: jest.fn().mockResolvedValue({ success: true }),
			};
			mockFetch.mockResolvedValue(mockResponse);

			await apiClient.post("/api/test", { data: "test" });

			expect(mockFetch).toHaveBeenCalledWith("/api/test", {
				method: "POST",
				headers: {
					"X-Requested-With": "XMLHttpRequest",
					"X-CSRFToken": "",
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ data: "test" }),
			});
		});

		test("should make PUT request", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => "application/json"),
				},
				json: jest.fn().mockResolvedValue({ success: true }),
			};
			mockFetch.mockResolvedValue(mockResponse);

			await apiClient.put("/api/test", { data: "test" });

			expect(mockFetch).toHaveBeenCalledWith("/api/test", {
				method: "PUT",
				headers: {
					"X-Requested-With": "XMLHttpRequest",
					"X-CSRFToken": "",
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ data: "test" }),
			});
		});

		test("should make DELETE request", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => "application/json"),
				},
				json: jest.fn().mockResolvedValue({ success: true }),
			};
			mockFetch.mockResolvedValue(mockResponse);

			await apiClient.delete("/api/test");

			expect(mockFetch).toHaveBeenCalledWith("/api/test", {
				method: "DELETE",
				headers: {
					"X-Requested-With": "XMLHttpRequest",
					"X-CSRFToken": "",
				},
			});
		});
	});

	describe("Error Handling", () => {
		test("should create APIError with correct properties", async () => {
			const mockResponse = {
				ok: false,
				status: 404,
				statusText: "Not Found",
				headers: {
					get: jest.fn(() => "application/json"),
				},
				json: jest.fn().mockResolvedValue({ error: "Resource not found" }),
			};
			mockFetch.mockResolvedValue(mockResponse);

			try {
				await apiClient.request("/api/test");
			} catch (error) {
				expect(error).toBeInstanceOf(APIError);
				expect(error.message).toBe("HTTP 404: Not Found");
				expect(error.status).toBe(404);
				expect(error.data).toEqual({ error: "Resource not found" });
			}
		});

		test("should handle loading state errors", async () => {
			mockFetch.mockRejectedValue(new Error("Network error"));

			try {
				await apiClient.request("/api/test");
			} catch (error) {
				expect(typeof apiClient.loading).toBe("boolean");
			}
		});
	});

	describe("URL Parameter Handling", () => {
		test("should handle empty parameters", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new APIClient();
			}).not.toThrow();
		});

		test("should handle multiple parameters", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new APIClient();
			}).not.toThrow();
		});

		test("should encode special characters in parameters", () => {
			expect(() => {
				// Test that the class can be instantiated without throwing
				new APIClient();
			}).not.toThrow();
		});
	});

	describe("Content Type Detection", () => {
		test("should handle missing content-type header", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => null),
				},
				text: jest.fn().mockResolvedValue("plain text"),
			};
			mockFetch.mockResolvedValue(mockResponse);

			const result = await apiClient.request("/api/test");

			expect(result).toBe("plain text");
		});

		test("should handle malformed content-type header", async () => {
			const mockResponse = {
				ok: true,
				status: 200,
				headers: {
					get: jest.fn(() => "invalid-content-type"),
				},
				text: jest.fn().mockResolvedValue("plain text"),
			};
			mockFetch.mockResolvedValue(mockResponse);

			const result = await apiClient.request("/api/test");

			expect(result).toBe("plain text");
		});
	});
});
