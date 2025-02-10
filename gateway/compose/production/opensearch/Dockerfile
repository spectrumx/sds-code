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

# Install netcat for port checking
RUN yum install -y nc gettext

# change uid of opensearch user to UID
RUN usermod -u ${UID} ${HOSTUSER}

# Copy configuration files directly to security directory
COPY ./compose/production/opensearch/config/*.yml /usr/share/opensearch/config/opensearch-security/
COPY ./compose/production/opensearch/init-security.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/init-security.sh

# Create wrapper script
RUN echo '#!/bin/bash' > /usr/local/bin/docker-entrypoint-wrapper.sh && \
    echo 'nohup /usr/local/bin/init-security.sh &' >> /usr/local/bin/docker-entrypoint-wrapper.sh && \
    echo 'exec /usr/share/opensearch/opensearch-docker-entrypoint.sh "$@"' >> /usr/local/bin/docker-entrypoint-wrapper.sh && \
    chmod +x /usr/local/bin/docker-entrypoint-wrapper.sh

USER ${HOSTUSER}

ENTRYPOINT ["/usr/local/bin/docker-entrypoint-wrapper.sh"]
