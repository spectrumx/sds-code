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
c.DockerSpawner.debug = False  # Disable debug in production

# User containers will access hub by container name on the Docker network
c.JupyterHub.hub_ip = "jupyterhub"
c.JupyterHub.hub_port = 8080

# Persist hub data on volume mounted inside container
c.JupyterHub.cookie_secret_file = "/data/jupyterhub_cookie_secret"
c.JupyterHub.db_url = "sqlite:////data/jupyterhub.sqlite"

# Authenticate users with OAuth via Auth0 (PRODUCTION ONLY)
c.JupyterHub.authenticator_class = "oauthenticator.auth0.Auth0OAuthenticator"

# Enable automatic user creation and allow all users
c.Authenticator.auto_login = True
c.Auth0OAuthenticator.allow_all = True
c.Authenticator.allowed_users = set()
# Remove explicit user restrictions
c.Authenticator.admin_users = {"admin"}  # Keep admin user(s)

# Update Auth0 configuration
c.Auth0OAuthenticator.oauth_callback_url = (
    f'https://{os.environ.get("JUPYTERHUB_HOST", "localhost:18888")}/hub/oauth_callback'
)
c.Auth0OAuthenticator.client_id = os.environ.get("AUTH0_CLIENT_ID")
c.Auth0OAuthenticator.client_secret = os.environ.get("AUTH0_CLIENT_SECRET")
c.Auth0OAuthenticator.auth0_domain = os.environ.get("AUTH0_DOMAIN")

# Add scope configuration to request email
c.Auth0OAuthenticator.scope = ["openid", "email", "profile"]

# Set username from email in Auth0 response
c.Auth0OAuthenticator.username_key = "email"

# Production logging level
c.JupyterHub.log_level = "INFO"
c.Authenticator.enable_auth_state = True

# Install packages using DockerSpawner's command configuration
c.DockerSpawner.cmd = ["start-notebook.sh"]
c.DockerSpawner.args = ["--NotebookApp.allow_origin='*'"]

# Add pip install command to be run when container starts
c.DockerSpawner.post_start_cmd = "pip install spectrumx"

# Production security settings
c.JupyterHub.ssl_cert = os.environ.get("JUPYTERHUB_SSL_CERT", "")
c.JupyterHub.ssl_key = os.environ.get("JUPYTERHUB_SSL_KEY", "")
c.JupyterHub.bind_url = "https://0.0.0.0:8000" if c.JupyterHub.ssl_cert else "http://0.0.0.0:8000"
