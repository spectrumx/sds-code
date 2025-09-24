# Local JupyterHub configuration file for SVI integration
import os

c = get_config()  # noqa: F821 # pyright: ignore[reportUndefinedVariable]

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
c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"

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

_nb_uid = os.environ.get("NB_UID", "1000")
_nb_gid = os.environ.get("NB_GID", "100")

c.DockerSpawner.debug = True
c.DockerSpawner.environment = {
    "CHOWN_HOME_OPTS": "-R",
    "CHOWN_HOME": "yes",
    "JUPYTER_ENABLE_LAB": "yes",
    "NB_GID": _nb_gid,
    "NB_UID": _nb_uid,
}
c.DockerSpawner.extra_create_kwargs = {"user": f"{_nb_uid}:{_nb_gid}"}
c.DockerSpawner.image = os.environ.get(
    "DOCKER_NOTEBOOK_IMAGE", "quay.io/jupyter/base-notebook:latest"
)
c.DockerSpawner.network_name = "jupyter_" + os.environ.get(
    "DOCKER_NETWORK_NAME", "sds-jupyter-local-net-clients"
)
c.DockerSpawner.notebook_dir = os.environ.get(
    "DOCKER_NOTEBOOK_DIR", "/home/jovyan/work"
)
c.DockerSpawner.post_start_cmd = "pip install ipywidgets spectrumx"
c.DockerSpawner.remove = True
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.volumes = {
    "jupyterhub-user-{username}": {"bind": c.DockerSpawner.notebook_dir, "mode": "rw"},
}

# === AUTHENTICATION ===
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

# === OTHER CONFIGURATION ===

# Configure proxy PID file to use writable directory
c.ConfigurableHTTPProxy.pid_file = "/data/jupyterhub-proxy.pid"
