# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
ARG JUPYTERHUB_VERSION
FROM quay.io/jupyterhub/jupyterhub:$JUPYTERHUB_VERSION


# Install Python packages from requirements.txt
COPY ./compose/local/jupyter/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]
