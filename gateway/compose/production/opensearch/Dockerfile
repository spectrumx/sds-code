# opensearch upgrades follow semver - let's target a major version
# https://opensearch.org/docs/latest/install-and-configure/upgrade-opensearch/index/
# release notes
# https://opensearch.org/docs/latest/version-history/
FROM docker.io/opensearchproject/opensearch:2
# image is amazon linux (fedora-based)

# variables here can be passed in build.args of the compose file
ARG UID
ARG HOSTUSER=opensearch

USER root

# change uid of opensearch user to UID
RUN usermod -u ${UID} ${HOSTUSER}

USER ${HOSTUSER}
