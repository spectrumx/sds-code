# Local JupyterHub configuration file for SVI integration
import os

# JupyterHub configuration
c = get_config()  # noqa: F821

# JupyterHub configuration
c.JupyterHub.bind_url = "http://0.0.0.0:8000"
c.JupyterHub.hub_ip = "jupyterhub"  # Container name for internal communication
c.JupyterHub.hub_port = 8080

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

# TODO: Uncomment when ready to test script loading
# PROOF OF CONCEPT: Load scripts from BOTH local files AND GitHub repository
# This allows testing both approaches to see which works better
# c.DockerSpawner.post_start_cmd = (
#     "bash -c 'pip install spectrumx && "
#     "mkdir -p /home/jovyan/work/scripts /home/jovyan/work/sample_scripts && "
#     "if [ ! -f /home/jovyan/work/scripts/.initialized ]; then "
#     "echo \"=== PROOF OF CONCEPT: Loading scripts from multiple sources ===\" && "
#     "echo \"1. Copying local scripts...\" && "
#     "cp -r /srv/jupyter/scripts/* /home/jovyan/work/scripts/ 2>/dev/null || echo \"No local scripts found\" && "
#     "cp -r /srv/jupyter/sample_scripts/* /home/jovyan/work/sample_scripts/ 2>/dev/null || echo \"No local sample_scripts found\" && "
#     "echo \"2. Downloading scripts from GitHub...\" && "
#     "cd /home/jovyan/work && "
#     "git clone https://github.com/your-org/sds-gateway-scripts.git temp_scripts || echo \"GitHub repo not found, skipping...\" && "
#     "if [ -d temp_scripts ]; then "
#     "cp -r temp_scripts/scripts/* /home/jovyan/work/scripts/ 2>/dev/null || echo \"No GitHub scripts directory found\" && "
#     "cp -r temp_scripts/sample_scripts/* /home/jovyan/work/sample_scripts/ 2>/dev/null || echo \"No GitHub sample_scripts directory found\" && "
#     "rm -rf temp_scripts; fi && "
#     "echo \"3. Setting permissions...\" && "
#     "touch /home/jovyan/work/scripts/.initialized && "
#     "chmod -R 755 /home/jovyan/work/scripts && "
#     "chmod -R 755 /home/jovyan/work/sample_scripts && "
#     "echo \"=== Script loading complete ===\"; fi'"
# )

# Minimal post-start command - just install spectrumx for now
c.DockerSpawner.post_start_cmd = "pip install spectrumx"
