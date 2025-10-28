# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
ARG JUPYTERHUB_VERSION

# https://quay.io/repository/jupyterhub/jupyterhub?tab=tags&tag=latest
FROM quay.io/jupyterhub/jupyterhub:$JUPYTERHUB_VERSION

# Build arguments with defaults
ARG NB_UID=1000
ARG NB_GID=100
ARG DOCKER_GID=999
ARG JUPYTER_USER=jupyter
ARG JUPYTER_HOME=/home/${JUPYTER_USER}

# Install packages
RUN apt-get update && \
    apt-get install -y docker.io sudo curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# create user and set groups
RUN (groupadd -g ${DOCKER_GID} docker || groupmod -g ${DOCKER_GID} docker || true) && \
    (groupadd -g ${NB_GID} nb_group || groupmod -g ${NB_GID} nb_group || true) && \
    useradd -m -u ${NB_UID} -g ${DOCKER_GID} -s /bin/bash ${JUPYTER_USER} && \
    usermod -aG ${NB_GID} ${JUPYTER_USER} && \
    useradd -m -u 1001 -g ${NB_GID} -s /bin/bash admin && \
    usermod -aG ${DOCKER_GID} admin && \
    usermod -aG ${DOCKER_GID} ${JUPYTER_USER} && \
    echo "${JUPYTER_USER} ALL=(ALL) NOPASSWD: /bin/chown, /bin/chmod" >> /etc/sudoers

# Setup directories, permissions, and cookie secret
RUN mkdir -p /data ${JUPYTER_HOME}/work ${JUPYTER_HOME}/.local/share/jupyter/runtime && \
    chown -R ${JUPYTER_USER}:${DOCKER_GID} /data ${JUPYTER_HOME} && \
    chmod -R 755 ${JUPYTER_HOME} /data && \
    python3 -c "import secrets; open('/data/jupyterhub_cookie_secret', 'w').write(secrets.token_hex(32))" && \
    chown ${JUPYTER_USER}:${DOCKER_GID} /data/jupyterhub_cookie_secret && \
    chmod 600 /data/jupyterhub_cookie_secret

# Create startup script
RUN echo '#!/bin/bash\n\
    set -e\n\
    [ -d "/data" ] && sudo chown -R ${JUPYTER_USER}:${DOCKER_GID} /data\n\
    exec jupyterhub -f /srv/jupyterhub/jupyterhub_config.py' > /start-jupyterhub.sh && \
    chmod +x /start-jupyterhub.sh

# Switch to non-root user
USER ${JUPYTER_USER}

# Install Python packages
COPY ./compose/local/jupyter/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

CMD ["/start-jupyterhub.sh"]
