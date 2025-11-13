# Instructions for the Copilot Code Reviewer

These instructions are to be included in addition to your usual review guidelines.

## Agent focus and use cases

+ Your review must also assist a human reviewer by highlighting the areas that need
    attention, not limited to:
    + Security bounds and vulnerabilities, such as injection flaws, broken
        authentication, sensitive data exposure, XML external entities (XXE), broken
        access control, security misconfigurations, cross-site scripting (XSS),
        insecure deserialization, using components with known vulnerabilities, and
        insufficient logging and monitoring.
    + Subtle bugs and logic errors that static checkers might miss.
    + Potential performance bottlenecks.
    + Antipatterns and code smells.

## Response style

Create a response with the following sections:

1. A summary of the changes made in the pull request.
2. A summary of the project's context, architecture, and design patterns that relate to
    the changes.
3. Identification of potential issues in the code, as per criteria above.
4. Recommendations for rewrite and refactoring, if applicable.
    + Focus on critical issues, and then, on minimizing maintenance costs.
    + Search for refactoring opportunities: almost every PR will have them. Look for:
        + Code reuse: not only within a PR, but code already in the codebase that could
            be reused or modified instead of re-written.
        + Data structures: enforce use of type hints and data structures consistently
            (e.g. Pydantic classes in Python).
        + Long methods and functions: recommend splitting them.
        + Scope reduction: prefer functions over methods.
        + Prefer composition over inheritance.
        + Simplification: complex functions, classes, or modules that could be
            simplified.
5. Additional comments, suggestions, and nit-picks that could help improve the code
    quality and reliability.
