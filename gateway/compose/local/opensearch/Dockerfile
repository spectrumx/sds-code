# opensearch upgrades follow semver - let's target a major version
# https://opensearch.org/docs/latest/install-and-configure/upgrade-opensearch/index/
# release notes
# https://opensearch.org/docs/latest/version-history/
FROM docker.io/opensearchproject/opensearch:2.18.0
# image is amazon linux (fedora-based)

# variables here can be passed in build.args of the compose file
ARG UID
ARG HOSTUSER=opensearch

# if UID is not set, fail the build
RUN test -n "${UID}" || (echo "UID is not set: pass it when building the image" && false)

USER root

# change uid of opensearch user to UID
RUN usermod -u ${UID} ${HOSTUSER}

USER ${HOSTUSER}
