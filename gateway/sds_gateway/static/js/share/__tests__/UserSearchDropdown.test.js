/**
 * Jest tests for UserSearchDropdown
 */

import { UserSearchDropdown } from "../UserSearchDropdown.js"

describe("UserSearchDropdown", () => {
    beforeEach(() => {
        document.body.innerHTML = ""
    })

    test("getDropdownForInput finds primary id from input suffix", () => {
        document.body.innerHTML = `
			<input id="user-search-item-1" />
			<div id="user-search-dropdown-item-1" class="user-search-dropdown"></div>
		`
        const input = document.getElementById("user-search-item-1")

        expect(UserSearchDropdown.getDropdownForInput(input)).toBe(
            document.getElementById("user-search-dropdown-item-1"),
        )
    })

    test("getDropdownForInput falls back to container query", () => {
        document.body.innerHTML = `
			<div class="user-search-input-container">
				<input id="user-search-custom" />
				<div class="user-search-dropdown"></div>
			</div>
		`
        const input = document.getElementById("user-search-custom")

        expect(
            UserSearchDropdown.getDropdownForInput(input)?.classList.contains(
                "user-search-dropdown",
            ),
        ).toBe(true)
    })

    test("navigateDropdown wraps and selects item", () => {
        const items = [
            {
                classList: { add: jest.fn(), remove: jest.fn() },
                scrollIntoView: jest.fn(),
            },
            {
                classList: { add: jest.fn(), remove: jest.fn() },
                scrollIntoView: jest.fn(),
            },
        ]

        UserSearchDropdown.navigateDropdown(items, -1, 1)

        expect(items[0].classList.add).toHaveBeenCalledWith("selected")
        expect(items[0].scrollIntoView).toHaveBeenCalled()
    })

    test("hideDropdown clears selected state", () => {
        document.body.innerHTML = `
			<div class="user-search-dropdown">
				<div class="list-group-item selected"></div>
			</div>
		`
        const dropdown = document.querySelector(".user-search-dropdown")
        UserSearchDropdown.hideDropdown(dropdown)

        expect(dropdown.classList.contains("d-none")).toBe(true)
        expect(dropdown.querySelector(".selected")).toBeNull()
    })
})
