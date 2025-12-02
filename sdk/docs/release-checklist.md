# Release Checklist

Follow these steps to create a new `0.*.*` release of the SDK:

+ Version bump
    + [ ] Create a new branch for release "`$RELEASE_BRANCH`" from `master`.
    + [ ] `uv version --bump <major|minor|patch>` to bump the version number.
+ Update documentation and dependencies
    + [ ] Review the experimental features and see which ones are ready for release.
    + [ ] List new changes in [docs/changelog.md](changelog.md); choose a semver version number `$NEW_VERSION`.
    + [ ] Update usage guide in `docs/README.md` with new features and breaking changes.
    + [ ] Upgrade dependencies with `just update`.
+ Checks and tests (on failure, fix it, then restart this section)
    + [ ] Run pre-commit checks on everything with `just pre-commit`.
    + [ ] Pass local tests with `just test-all`; meeting target coverage.
    + [ ] Pass integration tests with `just test-integration`.
    + [ ] Clean artifacts with `just clean`.
    + [ ] Build package with `just build`. Check list of sdist files and pass build acceptance.
+ Commit freeze
    + [ ] Merge `$RELEASE_BRANCH` to `master`.
    + [ ] Create and push a new git tag for the release in the form `v$NEW_VERSION`.
        + Pushing the tag will publish the package via GH actions. Otherwise, publish
            the package to PyPI with `just publish` (you'll need a local PyPI token).
    + [ ] Announce release to stakeholders.
