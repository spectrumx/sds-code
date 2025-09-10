# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
ARG JUPYTERHUB_VERSION
FROM quay.io/jupyterhub/jupyterhub:$JUPYTERHUB_VERSION

# Create non-root user with daemon group access (for macOS Docker Desktop)
RUN useradd -m -u 1000 -g daemon -s /bin/bash jupyter && \
    usermod -aG daemon jupyter

# Create admin user for JupyterHub
RUN useradd -m -u 1001 -g daemon -s /bin/bash admin && \
    usermod -aG daemon admin

# Install Docker client
RUN apt-get update && \
    apt-get install -y docker.io && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python packages from requirements.txt
COPY ./compose/local/jupyter/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

# Create data directory with proper ownership
RUN mkdir -p /data && chown -R jupyter:daemon /data && \
    mkdir -p /home/jupyter/work && \
    mkdir -p /home/jupyter/.local/share/jupyter/runtime && \
    chown -R jupyter:daemon /home/jupyter && \
    chmod -R 755 /home/jupyter && \
    chmod 777 /home/jupyter/.local/share/jupyter/runtime

# Switch to non-root user
USER jupyter

CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]
