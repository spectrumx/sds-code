/**
 * Jest tests for APIClient
 * Tests centralized API client functionality including CSRF tokens, error handling, and loading states
 */

// Import the APIClient class
import { APIClient } from "../APIClient.js"

// Mock APIError class
class APIError extends Error {
    constructor(message, status, data) {
        super(message)
        this.name = "APIError"
        this.status = status
        this.data = data
    }
}

global.APIError = APIError

const {
    installMockWindowOrigin,
    mockFetchResolved,
    installMinimalDocumentForApiClient,
    installCsrfMetaToken,
    createMockFetchResponse,
} = require("../../tests-config/testHelpers.js")

describe("APIClient", () => {
    let apiClient
    let mockFetch

    beforeEach(() => {
        jest.clearAllMocks()
        mockFetch = jest.fn()
        global.fetch = mockFetch
        installMinimalDocumentForApiClient()
        apiClient = new APIClient()
    })

    describe("CSRF Token Management", () => {
        test("should get CSRF token from meta tag", () => {
            const mockMetaToken = {
                getAttribute: jest.fn(() => "test-csrf-token"),
            }
            global.document.querySelector = jest.fn((selector) => {
                if (selector === 'meta[name="csrf-token"]') return mockMetaToken
                return null
            })

            const token = apiClient.getCSRFToken()

            expect(token).toBe("test-csrf-token")
            expect(mockMetaToken.getAttribute).toHaveBeenCalledWith("content")
        })

        test("should fallback to input field for CSRF token", () => {
            const mockInputToken = {
                value: "input-csrf-token",
            }
            global.document.querySelector = jest.fn((selector) => {
                if (selector === 'meta[name="csrf-token"]') return null
                if (selector === '[name="csrfmiddlewaretoken"]')
                    return mockInputToken
                return null
            })

            const token = apiClient.getCSRFToken()

            expect(token).toBe("input-csrf-token")
        })

        test("should fallback to cookie for CSRF token", () => {
            global.document.cookie = "csrftoken=cookie-csrf-token; other=value"
            global.document.querySelector = jest.fn(() => null)

            const token = apiClient.getCSRFToken()

            expect(token).toBe("cookie-csrf-token")
        })

        test("should return empty string when no CSRF token found", () => {
            // Mock document with no cookie and no DOM elements
            const originalCookie = global.document.cookie
            Object.defineProperty(global.document, "cookie", {
                writable: true,
                value: "",
            })
            global.document.querySelector = jest.fn(() => null)

            const token = apiClient.getCSRFToken()

            expect(token).toBe("")

            // Restore cookie
            Object.defineProperty(global.document, "cookie", {
                writable: true,
                value: originalCookie,
            })
        })
    })

    describe("Cookie Management", () => {
        test.each([
            [
                "test-cookie=test-value; other-cookie=other-value",
                "test-cookie",
                "test-value",
            ],
            ["other-cookie=other-value", "test-cookie", null],
            ["", "test-cookie", null],
            [
                "test-cookie=test%20value%20encoded",
                "test-cookie",
                "test value encoded",
            ],
        ])(
            "should handle cookie '%s' - get '%s' returns '%s'",
            (cookieString, cookieName, expected) => {
                Object.defineProperty(global.document, "cookie", {
                    writable: true,
                    value: cookieString,
                })

                const value = apiClient.getCookie(cookieName)

                expect(value).toBe(expected)
            },
        )
    })

    describe("API Requests", () => {
        test("should make successful GET request", async () => {
            mockFetchResolved(mockFetch)

            const result = await apiClient.request("/api/test")

            // Check that fetch was called with correct headers
            expect(mockFetch).toHaveBeenCalled()
            const callArgs = mockFetch.mock.calls[0]
            expect(callArgs[1].headers["X-Requested-With"]).toBe(
                "XMLHttpRequest",
            )
            expect(result).toEqual({ success: true })
        })

        test("should make POST request with CSRF token", async () => {
            mockFetchResolved(mockFetch)
            installCsrfMetaToken()

            await apiClient.request("/api/test", {
                method: "POST",
                body: JSON.stringify({ test: "data" }),
            })

            expect(mockFetch).toHaveBeenCalledWith("/api/test", {
                method: "POST",
                body: JSON.stringify({ test: "data" }),
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": "test-csrf-token",
                },
            })
        })

        test("should handle loading state", async () => {
            mockFetchResolved(mockFetch)

            // Create a loading state manager to track loading
            const mockLoadingState = {
                setLoading: jest.fn(),
            }

            await apiClient.request("/api/test", {}, mockLoadingState)

            // Verify loading state was set to true and then false
            expect(mockLoadingState.setLoading).toHaveBeenCalledWith(true)
            expect(mockLoadingState.setLoading).toHaveBeenCalledWith(false)
        })

        test("should handle non-JSON response", async () => {
            mockFetch.mockResolvedValue(
                createMockFetchResponse({
                    contentType: "text/plain",
                }),
            )

            const result = await apiClient.request("/api/test")

            expect(result).toBe("plain text")
        })

        test("should handle HTTP error responses", async () => {
            mockFetch.mockResolvedValue(
                createMockFetchResponse({
                    ok: false,
                    status: 404,
                    jsonData: { error: "Resource not found" },
                }),
            )

            await expect(apiClient.request("/api/test")).rejects.toThrow()
        })

        test("should handle network errors", async () => {
            mockFetch.mockRejectedValue(new Error("Network error"))

            await expect(apiClient.request("/api/test")).rejects.toThrow(
                "Network error",
            )
        })

        test("should handle JSON parse errors", async () => {
            mockFetch.mockResolvedValue(
                createMockFetchResponse({
                    jsonReject: new Error("Invalid JSON"),
                }),
            )

            await expect(apiClient.request("/api/test")).rejects.toThrow(
                "Invalid JSON",
            )
        })
    })

    describe("Convenience Methods", () => {
        beforeEach(() => {
            installMockWindowOrigin()
        })

        test("should make GET request", async () => {
            mockFetchResolved(mockFetch)

            await apiClient.get("/api/test")

            // Verify fetch was called with correct URL and parameters
            expect(mockFetch).toHaveBeenCalledWith(
                "http://localhost:8000/api/test",
                expect.objectContaining({
                    method: "GET",
                    headers: expect.objectContaining({
                        "X-Requested-With": "XMLHttpRequest",
                    }),
                }),
            )
        })

        test("should make GET request with query parameters", async () => {
            mockFetchResolved(mockFetch)

            await apiClient.get("/api/test", {
                param1: "value1",
                param2: "value2",
            })

            expect(mockFetch).toHaveBeenCalledWith(
                expect.stringContaining(
                    "/api/test?param1=value1&param2=value2",
                ),
                expect.objectContaining({
                    method: "GET",
                }),
            )
        })

        test.each([
            ["POST", "post"],
            ["PUT", "put"],
            ["PATCH", "patch"],
        ])(
            "should make %s request with FormData and CSRF token",
            async (method, methodName) => {
                mockFetchResolved(mockFetch)
                installCsrfMetaToken()

                await apiClient[methodName]("/api/test", { data: "test" })

                // Verify request was made with FormData and CSRF token
                expect(mockFetch).toHaveBeenCalled()
                const callArgs = mockFetch.mock.calls[0]
                expect(callArgs[0]).toBe("/api/test")
                expect(callArgs[1].method).toBe(method)
                expect(callArgs[1].body).toBeInstanceOf(FormData)
                expect(callArgs[1].headers["X-CSRFToken"]).toBe(
                    "test-csrf-token",
                )
            },
        )
    })

    describe("Error Handling", () => {
        test("should create APIError with correct properties", async () => {
            mockFetch.mockResolvedValue(
                createMockFetchResponse({
                    ok: false,
                    status: 404,
                    jsonData: { error: "Resource not found" },
                }),
            )

            try {
                await apiClient.request("/api/test")
                // Should not reach here
                expect(true).toBe(false)
            } catch (error) {
                // Check error properties
                expect(error.name).toBe("APIError")
                expect(error.message).toBe("HTTP 404: Not Found")
                expect(error.status).toBe(404)
                expect(error.data).toEqual({ error: "Resource not found" })
            }
        })

        test("should handle loading state errors", async () => {
            mockFetch.mockRejectedValue(new Error("Network error"))

            const mockLoadingState = {
                setLoading: jest.fn(),
            }

            try {
                await apiClient.request("/api/test", {}, mockLoadingState)
            } catch (error) {
                // Verify loading state was set to false even on error
                expect(mockLoadingState.setLoading).toHaveBeenCalledWith(true)
                expect(mockLoadingState.setLoading).toHaveBeenCalledWith(false)
            }
        })
    })

    describe("URL Parameter Handling", () => {
        beforeEach(() => {
            installMockWindowOrigin()
        })

        test("should handle empty parameters", async () => {
            mockFetchResolved(mockFetch)

            await apiClient.get("/api/test", {})

            expect(mockFetch).toHaveBeenCalledWith(
                "http://localhost:8000/api/test",
                expect.any(Object),
            )
        })

        test("should handle multiple parameters", async () => {
            mockFetchResolved(mockFetch)

            await apiClient.get("/api/test", {
                param1: "value1",
                param2: "value2",
                param3: "value3",
            })

            const url = mockFetch.mock.calls[0][0]
            expect(url).toContain("param1=value1")
            expect(url).toContain("param2=value2")
            expect(url).toContain("param3=value3")
        })

        test("should encode special characters in parameters", async () => {
            mockFetchResolved(mockFetch)

            await apiClient.get("/api/test", {
                query: "test value & special=chars",
            })

            const url = mockFetch.mock.calls[0][0]
            expect(url).toContain("test%20value")
            expect(url).toContain("%26")
            expect(url).toContain("%3D")
        })

        test("should filter out null and undefined parameters", async () => {
            mockFetchResolved(mockFetch)

            await apiClient.get("/api/test", {
                valid: "value",
                nullParam: null,
                undefinedParam: undefined,
            })

            const url = mockFetch.mock.calls[0][0]
            expect(url).toContain("valid=value")
            expect(url).not.toContain("nullParam")
            expect(url).not.toContain("undefinedParam")
        })
    })

    describe("Content Type Detection", () => {
        test.each([
            [null, "plain text"],
            ["invalid-content-type", "plain text"],
            ["text/plain", "plain text"],
            ["application/json", { success: true }],
        ])(
            "should handle content-type '%s' correctly",
            async (contentType, expectedResult) => {
                mockFetch.mockResolvedValue(
                    createMockFetchResponse({ contentType }),
                )

                const result = await apiClient.request("/api/test")

                if (contentType?.includes("application/json")) {
                    expect(result).toEqual(expectedResult)
                } else {
                    expect(result).toBe(expectedResult)
                }
            },
        )
    })
})
