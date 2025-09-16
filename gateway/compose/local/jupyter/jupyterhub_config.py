# Local JupyterHub configuration file for SVI integration
import os

# JupyterHub configuration
c = get_config()  # noqa: F821

# JupyterHub configuration
c.JupyterHub.bind_url = "http://0.0.0.0:8000"
c.JupyterHub.hub_ip = "0.0.0.0"  # Bind to all interfaces
c.JupyterHub.hub_port = 8080

# Configure hub URL for user containers to use hostname instead of container ID
c.JupyterHub.hub_connect_url = "http://jupyterhub:8080"

# Security configuration - use environment variable for cookie secret
c.JupyterHub.cookie_secret = os.environ.get(
    "JUPYTERHUB_CRYPT_KEY",
    "09e1bbb166e33b5edf6479451910cacde5df6c06c40ce8f924e2dc5b1d505100",
)

# Use DockerSpawner for proper user isolation with Docker-in-Docker
c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"

# Docker configuration
c.DockerSpawner.docker_socket = "unix:///var/run/docker.sock"

# Docker image for user containers
c.DockerSpawner.image = "quay.io/jupyter/base-notebook:latest"

# Notebook directory in the container
c.DockerSpawner.notebook_dir = "/home/jovyan/work"

# Mount user volumes
c.DockerSpawner.volumes = {"jupyterhub-user-{username}": "/home/jovyan/work"}

# Container management
c.DockerSpawner.remove = True

# Network configuration - use internal Docker network
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.network_name = "gateway_jupyter-net"

# Increase timeouts for container startup
c.Spawner.start_timeout = 120  # 2 minutes
c.Spawner.http_timeout = 60  # 1 minute
c.Spawner.stop_timeout = 30  # 30 seconds

# Basic JupyterLab configuration
c.Spawner.default_url = "/lab"  # Start with JupyterLab
c.Spawner.cmd = ["jupyter-labhub"]  # Use JupyterLab
c.Spawner.cleanup_on_exit = True  # Clean up containers on exit

# User configuration for containers - use the default jovyan user
# The base notebook image uses jovyan (UID 1000, GID 100)
c.DockerSpawner.extra_create_kwargs = {
    "user": "1000:100"  # Use the default jovyan user from the image
}

# Environment variables for containers
c.DockerSpawner.environment = {
    "JUPYTER_ENABLE_LAB": "yes",
    "NB_UID": "1000",
    "NB_GID": "100",
    "CHOWN_HOME": "yes",
    "CHOWN_HOME_OPTS": "-R",
    "JUPYTERHUB_API_URL": "http://jupyterhub:8080/hub/api",
}

# Enable debug logging for DockerSpawner
c.DockerSpawner.debug = True

# Use simple local authenticator for development
c.JupyterHub.authenticator_class = "jupyterhub.auth.DummyAuthenticator"
c.DummyAuthenticator.password = os.environ.get("JUPYTERHUB_DUMMY_PASSWORD", "admin")
c.DummyAuthenticator.allowed_users = {"admin"}

# Admin users (use authenticator's admin_users instead of deprecated
# JupyterHub.admin_users)
c.DummyAuthenticator.admin_users = {"admin"}

# Database configuration - use SQLite for local development
c.JupyterHub.db_url = "sqlite:////data/jupyterhub.sqlite"

# Configure proxy PID file to use writable directory
c.ConfigurableHTTPProxy.pid_file = "/data/jupyterhub-proxy.pid"

# Logging
c.JupyterHub.log_level = "INFO"
c.Spawner.debug = True

# User limits
c.Spawner.mem_limit = "2G"
c.Spawner.cpu_limit = 1.0

# Timeout settings
c.Spawner.start_timeout = 600  # 10 minutes for first startup
c.Spawner.http_timeout = 300  # 5 minutes for HTTP operations

# Enable JupyterLab
c.Spawner.environment = {"JUPYTER_ENABLE_LAB": "yes"}

# Mount host directories into user containers (now handled in main volumes config)

# Minimal setup for local testing
