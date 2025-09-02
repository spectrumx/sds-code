# Production JupyterHub configuration file - Adopting SVI approach for simplicity
import os

# JupyterHub configuration
c = get_config()  # noqa: F821

# Spawn single-user servers as Docker containers
c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"

# JupyterHub is hosted at /hub
c.JupyterHub.base_url = "/notebook"

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

# Database configuration - Keep PostgreSQL for Gateway
db_user = os.environ.get("POSTGRES_USER", "spectrumx")
db_password = os.environ.get("POSTGRES_PASSWORD", "your-specfic-password")
db_host = os.environ.get("POSTGRES_HOST", "postgres")
db_port = os.environ.get("POSTGRES_PORT", "5432")
c.JupyterHub.db_url = (
    f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/jupyterhub"
)

# Authenticate users with Auth0
c.JupyterHub.authenticator_class = "oauthenticator.auth0.Auth0OAuthenticator"

# Enable automatic user creation and allow all users
c.Authenticator.auto_login = True
c.Auth0OAuthenticator.allow_all = True
c.Authenticator.allowed_users = set()
# Remove explicit user restrictions
c.Authenticator.admin_users = {os.environ.get("JUPYTERHUB_ADMIN", "admin")}

# Update Auth0 configuration
c.Auth0OAuthenticator.oauth_callback_url = (
    f'http://{os.environ.get("JUPYTERHUB_HOST", "localhost:8888")}/hub/oauth_callback'
)
c.Auth0OAuthenticator.client_id = os.environ.get("AUTH0_CLIENT_ID")
c.Auth0OAuthenticator.client_secret = os.environ.get("AUTH0_CLIENT_SECRET")
c.Auth0OAuthenticator.auth0_domain = os.environ.get("AUTH0_DOMAIN")

# Add scope configuration to request email
c.Auth0OAuthenticator.scope = ["openid", "email", "profile"]

# Set username from email in Auth0 response
c.Auth0OAuthenticator.username_key = "email"

# Enable debug logging
c.JupyterHub.log_level = "DEBUG"
c.Authenticator.enable_auth_state = True

# Increase timeout for server startup
c.Spawner.http_timeout = 60  # Increase from default 30 seconds
c.Spawner.start_timeout = 60  # Increase startup timeout

# Ensure environment variables are passed to the container
c.DockerSpawner.environment = {
    "JUPYTER_ENABLE_LAB": "yes",
    "GRANT_SUDO": "yes",
    "CHOWN_HOME": "yes",
}

# Add container configuration for better stability
c.DockerSpawner.extra_host_config = {
    "restart_policy": {"Name": "unless-stopped"},
    "mem_limit": "2g",  # Set memory limit
}

# Replace with a proper shell command that handles errors
c.DockerSpawner.post_start_cmd = "pip install ipywidgets spectrumx"
