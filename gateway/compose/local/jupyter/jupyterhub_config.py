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

# Security configuration - use standard paths
c.JupyterHub.cookie_secret_file = os.environ.get(
    "JUPYTERHUB_COOKIE_SECRET_FILE", "/data/jupyterhub_cookie_secret"
)

# Use Docker spawner for containerized user servers
c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"

# Docker spawner configuration
c.DockerSpawner.image = os.environ.get(
    "DOCKER_NOTEBOOK_IMAGE", "quay.io/jupyter/base-notebook:latest"
)
c.DockerSpawner.network_name = os.environ.get(
    "DOCKER_NETWORK_NAME", "gateway_sds-network-local"
)
c.DockerSpawner.notebook_dir = os.environ.get(
    "DOCKER_NOTEBOOK_DIR", "/home/jovyan/work"
)
c.DockerSpawner.volumes = {
    "jupyterhub_data": "/home/jovyan/work",
    "/var/run/docker.sock": "/var/run/docker.sock",
    # TODO: Uncomment when ready to test script loading
    # Local script mounting for proof of concept
    # "/Users/srucker1/Desktop/sds-code/gateway/compose/local/jupyter/sample_scripts": (
    #     "/srv/jupyter/sample_scripts"
    # ),
    # "/Users/srucker1/Desktop/sds-code/gateway/scripts": "/srv/jupyter/scripts",
}
c.DockerSpawner.extra_host_config = {
    "security_opt": ["label:disable"],
    "cap_add": ["SYS_ADMIN"],
}

# Use simple local authenticator for development
c.JupyterHub.authenticator_class = "jupyterhub.auth.DummyAuthenticator"
c.DummyAuthenticator.password = os.environ.get("JUPYTERHUB_DUMMY_PASSWORD", "admin")
c.DummyAuthenticator.allowed_users = {"admin"}

# Admin users
c.JupyterHub.admin_users = {os.environ.get("JUPYTERHUB_ADMIN", "admin")}

# Database configuration - use SQLite for local development
c.JupyterHub.db_url = "sqlite:////data/jupyterhub.sqlite"

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

# Minimal setup - just install spectrumx
c.DockerSpawner.post_start_cmd = "pip install spectrumx"
