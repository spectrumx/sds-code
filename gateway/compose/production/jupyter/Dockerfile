# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
ARG JUPYTERHUB_VERSION
FROM quay.io/jupyterhub/jupyterhub:$JUPYTERHUB_VERSION

# Create non-root user with docker group access
# Use dynamic UID/GID from environment variables
ARG NB_UID
ARG NB_GID
ARG DOCKER_GID

# Create docker group first
RUN groupadd -g ${DOCKER_GID} docker

# Create jupyter user with dynamic UID/GID
RUN groupadd -g ${NB_GID} jupyter && \
    useradd -m -u ${NB_UID} -g jupyter -s /bin/bash jupyter && \
    usermod -aG docker jupyter

# Docker CLI will be mounted from host - no need to install

# Install Python packages from requirements.txt
COPY ./compose/production/jupyter/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

# Create data directory with proper ownership
RUN mkdir -p /data && chown -R jupyter:docker /data && \
    mkdir -p /home/jupyter/work && \
    mkdir -p /home/jupyter/.local/share/jupyter/runtime && \
    chown -R jupyter:docker /home/jupyter && \
    chmod -R 755 /home/jupyter && \
    chmod 777 /home/jupyter/.local/share/jupyter/runtime

# Switch to non-root user
USER jupyter

CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]
