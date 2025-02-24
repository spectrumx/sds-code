# Release Checklist

Follow these steps to create a new `0.*.*` release of the SDK:

+ Version bump
    + [ ] Create a new branch for release "`$RELEASE_BRANCH`" from `master`.
    + [ ] Update the `version` field in the `[project]` section of `pyproject.toml`.
+ Update documentation
    + [ ] List new changes in [docs/changelog.md](changelog.md); choose a semver version number `$NEW_VERSION`.
    + [ ] Update usage guide in [docs/README.md](README.md) with new features and breaking changes.
+ Tests (on failure, fix it, then restart this section):
    + [ ] Pass local tests with `make test-all`; meeting target coverage.
    + [ ] Pass integration tests with `make test-integration`.
    + [ ] Build package with `make build`. Check list of sdist files and pass build acceptance.
+ Commit freeze
    + [ ] Create and push a new git tag for the release in the form `v$NEW_VERSION`.
    + [ ] Publish package to PyPI with `make publish`.
    + [ ] Announce release to stakeholders.
