# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
ARG JUPYTERHUB_VERSION
FROM quay.io/jupyterhub/jupyterhub:$JUPYTERHUB_VERSION

# Build arguments
ARG NB_UID
ARG NB_GID
ARG DOCKER_GID

# Install packages and create users in one layer
RUN apt-get update && \
    apt-get install -y docker.io sudo curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    (groupadd -g ${DOCKER_GID} docker || groupmod -g ${DOCKER_GID} docker) && \
    useradd -m -u ${NB_UID} -g ${DOCKER_GID} -s /bin/bash jupyter && \
    usermod -aG ${NB_GID} jupyter && \
    echo "jupyter ALL=(ALL) NOPASSWD: /bin/chown, /bin/chmod" >> /etc/sudoers

# Install Python packages
COPY ./compose/production/jupyter/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

# Setup directories, permissions, and cookie secret
RUN mkdir -p /data /home/jupyter/work /home/jupyter/.local/share/jupyter/runtime && \
    chown -R jupyter:${DOCKER_GID} /data /home/jupyter && \
    chmod -R 755 /home/jupyter /data && \
    python3 -c "import secrets; open('/data/jupyterhub_cookie_secret', 'w').write(secrets.token_hex(32))" && \
    chown jupyter:${DOCKER_GID} /data/jupyterhub_cookie_secret && \
    chmod 600 /data/jupyterhub_cookie_secret

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
[ -d "/data" ] && sudo chown -R jupyter:${DOCKER_GID} /data\n\
[ -S "/var/run/docker.sock" ] && sudo chown root:${DOCKER_GID} /var/run/docker.sock && sudo chmod 660 /var/run/docker.sock\n\
exec jupyterhub -f /srv/jupyterhub/jupyterhub_config.py' > /start-jupyterhub.sh && \
    chmod +x /start-jupyterhub.sh

# Switch to non-root user
USER jupyter

CMD ["/start-jupyterhub.sh"]
