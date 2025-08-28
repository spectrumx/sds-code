# Production JupyterHub configuration file for SVI integration
import os

# JupyterHub configuration
c = get_config()  # noqa: F821

# JupyterHub configuration
c.JupyterHub.bind_url = "https://0.0.0.0:8000"
c.JupyterHub.hub_ip = "jupyterhub"  # Container name for internal communication
c.JupyterHub.hub_port = 8080

# Security configuration - use standard paths
c.JupyterHub.cookie_secret_file = os.environ.get(
    "JUPYTERHUB_COOKIE_SECRET_FILE", "/srv/jupyterhub/jupyterhub_cookie_secret"
)

# Use Docker spawner for containerized user servers
c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"

# Docker spawner configuration
c.DockerSpawner.image = os.environ.get(
    "DOCKER_NOTEBOOK_IMAGE", "quay.io/jupyter/base-notebook:latest"
)
c.DockerSpawner.network_name = os.environ.get(
    "DOCKER_NETWORK_NAME", "sds-gateway-prod-minio-net"
)
c.DockerSpawner.notebook_dir = os.environ.get(
    "DOCKER_NOTEBOOK_DIR", "/home/jovyan/work"
)
c.DockerSpawner.volumes = {
    "sds-gateway-prod-jupyterhub-data": "/home/jovyan/work",
    "/var/run/docker.sock": "/var/run/docker.sock",
}
c.DockerSpawner.extra_host_config = {
    "security_opt": ["label:disable"],
    "cap_add": ["SYS_ADMIN"],
}

# Auth0 authentication configuration
c.JupyterHub.authenticator_class = "oauthenticator.auth0.Auth0OAuthenticator"
c.Auth0OAuthenticator.client_id = os.environ.get("AUTH0_CLIENT_ID")
c.Auth0OAuthenticator.client_secret = os.environ.get("AUTH0_CLIENT_SECRET")
c.Auth0OAuthenticator.oauth_callback_url = "https://your-domain.com/hub/oauth_callback"
c.Auth0OAuthenticator.scope = ["openid", "email", "profile"]

# Database configuration
db_user = os.environ.get("POSTGRES_USER", "spectrumx")
db_password = os.environ.get("POSTGRES_PASSWORD", "your-specfic-password")
db_host = os.environ.get("POSTGRES_HOST", "postgres")
db_port = os.environ.get("POSTGRES_PORT", "5432")
c.JupyterHub.db_url = (
    f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/jupyterhub"
)

# Admin users
c.JupyterHub.admin_users = {os.environ.get("JUPYTERHUB_ADMIN", "admin")}

# SSL configuration for production
c.JupyterHub.ssl_cert = "/etc/ssl/certs/cert.pem"
c.JupyterHub.ssl_key = "/etc/ssl/certs/key.pem"

# Security settings
c.JupyterHub.allow_named_servers = True
c.JupyterHub.named_server_limit_per_user = 2
c.JupyterHub.active_server_limit = 10

# Logging
c.JupyterHub.log_level = "WARN"
c.Spawner.debug = False

# User limits
c.Spawner.mem_limit = "4G"
c.Spawner.cpu_limit = 2.0

# Timeout settings
c.Spawner.start_timeout = 300
c.Spawner.http_timeout = 120

# Enable JupyterLab
c.Spawner.environment = {"JUPYTER_ENABLE_LAB": "yes"}

# Rate limiting
c.JupyterHub.concurrent_spawn_limit = 5
c.JupyterHub.active_user_window = 3600

# Cleanup settings
c.JupyterHub.cleanup_servers = True
c.JupyterHub.cleanup_interval = 300
