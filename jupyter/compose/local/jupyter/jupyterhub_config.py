# Local JupyterHub configuration file for SVI integration
import os
from pathlib import Path

from dockerspawner import DockerSpawner

# ruff: noqa: T201

c = get_config()  # noqa: F821 # pyright: ignore[reportUndefinedVariable]

# these have to be 1000 and 100, apparently, otherwise
# we get Permission denied: '/home/jovyan/.local'
_nb_uid = 1000
_nb_gid = 100


class MyDockerSpawner(DockerSpawner):
    def get_env(self):
        username = self.user.name
        env = super().get_env()
        # https://jupyter-docker-stacks.readthedocs.io/en/latest/using/common.html#user-related-configurations
        env["NB_USER"] = username
        env["NB_UID"] = _nb_uid
        env["NB_GID"] = _nb_gid
        env["NB_GROUP"] = "nb_users"
        env["CHOWN_HOME"] = "yes"
        env["CHOWN_HOME_OPTS"] = "-R"
        env["JUPYTER_ENABLE_LAB"] = "yes"
        print(f"Spawner environment for user {username}: {env}")
        return env


# === HUB APP ===
# reference: https://jupyterhub.readthedocs.io/en/stable/reference/api/app.html

c.JupyterHub.active_server_limit = 10
c.JupyterHub.base_url = os.environ.get("JUPYTERHUB_BASE_URL", "/")
c.JupyterHub.bind_url = "http://0.0.0.0:8000"
c.JupyterHub.cookie_secret = os.environ.get(
    "JUPYTERHUB_CRYPT_KEY",
    "09e1bbb166e33b5edf6479451910cacde5df6c06c40ce8f924e2dc5b1d505100",
)
c.JupyterHub.cleanup_proxy = True
c.JupyterHub.cleanup_servers = True
c.JupyterHub.concurrent_spawn_limit = 10
c.JupyterHub.db_url = "sqlite:////data/jupyterhub.sqlite"
c.JupyterHub.hub_connect_ip = "jupyterhub"
c.JupyterHub.hub_ip = "0.0.0.0"
c.JupyterHub.hub_port = 8080
c.JupyterHub.log_level = "DEBUG"
c.JupyterHub.spawner_class = MyDockerSpawner

# === HUB SPAWNER ===
# reference: https://jupyterhub.readthedocs.io/en/latest/reference/api/spawner.html

c.Spawner.cmd = ["jupyter-labhub"]
c.Spawner.cpu_limit = 1.0
c.Spawner.debug = True
c.Spawner.default_url = "/lab"
c.Spawner.environment = {"JUPYTER_ENABLE_LAB": "yes"}
c.Spawner.http_timeout = 60
c.Spawner.mem_limit = "2G"
c.Spawner.start_timeout = 120

# === DOCKER SPAWNER ===
# reference: https://jupyterhub-dockerspawner.readthedocs.io/en/latest/api/index.html

# prefix that docker prepends to this docker compose stack: e.g.
# use `docker network ls` to see which network is created after standing jupyterhub
# It might look like:
#   sds-jupyter-local_sds-jupyter-local-net-clients
# for that, the network_name_prefix is `sds-jupyter-local_`
network_name_prefix = "sds-jupyter-local_"

c.DockerSpawner.debug = True
c.DockerSpawner.extra_create_kwargs = {"user": f"{_nb_uid}:{_nb_gid}"}
c.DockerSpawner.image = os.environ.get(
    "DOCKER_NOTEBOOK_IMAGE", "quay.io/jupyter/base-notebook:latest"
)
c.DockerSpawner.network_name = network_name_prefix + os.environ.get(
    "DOCKER_NETWORK_NAME", "sds-jupyter-local-net-clients"
)
c.DockerSpawner.notebook_dir = os.environ.get(
    "DOCKER_NOTEBOOK_DIR", "/home/jovyan/work"
)
c.DockerSpawner.prefix = "sds-jupyter-user"
c.DockerSpawner.post_start_cmd = "pip install ipywidgets spectrumx"
c.DockerSpawner.remove = True
c.DockerSpawner.use_internal_ip = True

# Get the host path for sample scripts
# HOST_PWD is passed from the host via docker-compose environment variable
# It represents the directory from which docker-compose is run
host_pwd = os.environ.get("HOST_PWD")
if not host_pwd:
    raise ValueError(
        "HOST_PWD environment variable not set. "
        "Make sure you're using docker-compose which passes PWD as HOST_PWD."
    )
sample_scripts_host_path = Path(host_pwd) / "compose/local/jupyter/sample_scripts"
print(f"Sample scripts host path: {sample_scripts_host_path}")

c.DockerSpawner.volumes = {
    "jupyterhub-user-{username}": {"bind": c.DockerSpawner.notebook_dir, "mode": "rw"},
    sample_scripts_host_path: {"bind": "/home/jovyan/work/sample_scripts", "mode": "ro"},
}

# === AUTHENTICATION AND ACCCESS CONTROL ===
# reference: https://jupyterhub.readthedocs.io/en/latest/reference/api/auth.html
# oauthenticator: https://oauthenticator.readthedocs.io/en/stable/reference/api/gen/oauthenticator.auth0.html

c.Auth0OAuthenticator.allow_all = False
c.Authenticator.auto_login = False
c.Authenticator.enable_auth_state = True

use_auth0: bool = bool(
    os.environ.get("AUTH0_DOMAIN")
    and os.environ.get("AUTH0_CLIENT_ID")
    and os.environ.get("AUTH0_CLIENT_SECRET")
)

# Authenticate users with Auth0 (you can use Auth0 dev credentials for this)
if use_auth0:
    c.JupyterHub.authenticator_class = "oauthenticator.auth0.Auth0OAuthenticator"
# Alternatively, use simple local authenticator for development
else:
    c.JupyterHub.authenticator_class = "jupyterhub.auth.DummyAuthenticator"
    c.DummyAuthenticator.admin_users = {"admin"}
    c.DummyAuthenticator.allowed_users = {"admin"}
    c.DummyAuthenticator.password = os.environ.get("JUPYTERHUB_DUMMY_PASSWORD", "admin")

# === IDLE CULLER CONFIGURATION ===
# Configure jupyterhub-idle-culler service following JupyterHub 2.0+ scopes

# Define the idle culler service as a hub managed service
c.JupyterHub.services = [
    {
        "name": "jupyterhub-idle-culler-service",
        "command": [
            "python",
            "-m",
            "jupyterhub_idle_culler",
            "--timeout=43200",  # 12 hours timeout for idle servers
            "--cull-every=3600",  # Check every hour
            "--remove-named-servers",  # Remove named servers
            "--concurrency=10",  # Limit concurrent operations
            "--max-age=43200",  # Maximum age of 12 hours (hard limit)
        ],
    }
]

# Configure idle culler permissions using JupyterHub 2.0+ scopes
c.JupyterHub.load_roles = [
    {
        "name": "jupyterhub-idle-culler-role",
        "scopes": [
            "list:users",  # Access to the user list API
            "read:users:activity",  # Read users' last_activity field
            "read:servers",  # Read users' servers field
            "delete:servers",  # Stop users' servers and delete named servers
        ],
        "services": ["jupyterhub-idle-culler-service"],
    }
]

# === OTHER CONFIGURATION ===

# Configure proxy PID file to use writable directory
c.ConfigurableHTTPProxy.pid_file = "/data/jupyterhub-proxy.pid"
