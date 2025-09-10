# Local JupyterHub configuration file for SVI integration
import os

from jupyterhub.spawner import LocalProcessSpawner

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

# Custom spawner configuration
c.CustomLocalProcessSpawner.notebook_dir = "/home/jupyter/work"
c.CustomLocalProcessSpawner.username = "jupyter"
c.CustomLocalProcessSpawner.working_dir = "/home/jupyter"
c.CustomLocalProcessSpawner.set_user = False


# Custom spawner class to avoid user lookup issues
class CustomLocalProcessSpawner(LocalProcessSpawner):
    def get_env(self):
        env = super().get_env()
        env["HOME"] = "/home/jupyter"
        env["USER"] = "jupyter"
        return env

    def user_env(self, env):
        # Override user_env to avoid getpwnam lookup
        env["HOME"] = "/home/jupyter"
        env["USER"] = "jupyter"
        return env

    def set_user_setuid(self, username):
        # Override set_user_setuid to avoid getpwnam lookup
        # Just return without doing anything since we're not switching users
        pass


# Use custom spawner
c.JupyterHub.spawner_class = CustomLocalProcessSpawner

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
