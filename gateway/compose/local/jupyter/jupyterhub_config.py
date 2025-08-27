# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

# Configuration file for JupyterHub
import os

c = get_config()  # noqa: F821

# We rely on environment variables to configure JupyterHub so that we
# avoid having to rebuild the JupyterHub container every time we change a
# configuration parameter.

# Spawn single-user servers as Docker containers
c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"

# Spawn containers from this image
c.DockerSpawner.image = os.environ["DOCKER_NOTEBOOK_IMAGE"]

# Connect containers to this Docker network
network_name = os.environ["DOCKER_NETWORK_NAME"]
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.network_name = network_name

# Simplify network configuration
c.DockerSpawner.extra_host_config = {}  # Remove network_mode since we're using network_name

# Remove network config from create_kwargs since we're using network_name
c.DockerSpawner.extra_create_kwargs = {}

# Explicitly set notebook directory because we'll be mounting a volume to it.
# Most `jupyter/docker-stacks` *-notebook images run the Notebook server as
# user `jovyan`, and set the notebook directory to `/home/jovyan/work`.
# We follow the same convention.
notebook_dir = os.environ.get("DOCKER_NOTEBOOK_DIR", "/home/jovyan/work")
c.DockerSpawner.notebook_dir = notebook_dir

# Mount the real user's Docker volume on the host to the notebook user's
# notebook directory in the container
c.DockerSpawner.volumes = {"jupyterhub-user-{username}": notebook_dir}

# Remove conflicting container removal settings
c.DockerSpawner.remove = False  # Set to False to avoid conflict with restart policy

# For debugging arguments passed to spawned containers
c.DockerSpawner.debug = True

# User containers will access hub by container name on the Docker network
c.JupyterHub.hub_ip = "jupyterhub"
c.JupyterHub.hub_port = 8080

# Persist hub data on volume mounted inside container
c.JupyterHub.cookie_secret_file = "/data/jupyterhub_cookie_secret"
c.JupyterHub.db_url = "sqlite:////data/jupyterhub.sqlite"

# Use simple local authenticator for development
c.JupyterHub.authenticator_class = "jupyterhub.auth.DummyAuthenticator"

# Allow all users and auto-login for development
c.DummyAuthenticator.password = "admin"
c.DummyAuthenticator.allowed_users = {"admin"}
c.Authenticator.admin_users = {"admin"}

# Enable debug logging
c.JupyterHub.log_level = "DEBUG"
c.Authenticator.enable_auth_state = True

# Install packages using DockerSpawner's command configuration
c.DockerSpawner.cmd = ["start-notebook.sh"]
c.DockerSpawner.args = ["--NotebookApp.allow_origin='*'"]

# Automatically copy repository scripts to user's home directory when container starts
# Use a shell script to handle multiple commands properly
c.DockerSpawner.post_start_cmd = "bash -c 'pip install spectrumx && python /srv/jupyter/sample_scripts/copy_to_home.py'"
