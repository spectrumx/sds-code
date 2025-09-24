# Production JupyterHub configuration file - Adopting SVI approach for simplicity
import os

c = get_config()  # noqa: F821 # pyright: ignore[reportUndefinedVariable]

# === HUB APP ===
# reference: https://jupyterhub.readthedocs.io/en/stable/reference/api/app.html

c.JupyterHub.active_server_limit = 10
c.JupyterHub.base_url = os.environ.get("JUPYTERHUB_BASE_URL", "/")
c.JupyterHub.bind_url = "http://0.0.0.0:8000"
c.JupyterHub.cookie_secret_file = os.environ.get(
    "JUPYTERHUB_COOKIE_SECRET_FILE", "/data/jupyterhub_cookie_secret"
)

c.JupyterHub.cleanup_proxy = True
c.JupyterHub.cleanup_servers = True
c.JupyterHub.concurrent_spawn_limit = 10
c.JupyterHub.db_url = "sqlite:////data/jupyterhub.sqlite"
c.JupyterHub.hub_connect_ip = "jupyterhub"
c.JupyterHub.hub_ip = "0.0.0.0"
c.JupyterHub.hub_port = 8080
c.JupyterHub.log_level = "INFO"
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
c.Spawner.start_timeout = 60

# === DOCKER SPAWNER ===
# reference: https://jupyterhub-dockerspawner.readthedocs.io/en/latest/api/index.html

_nb_uid = os.environ.get("NB_UID", "1000")
_nb_gid = os.environ.get("NB_GID", "100")

c.DockerSpawner.debug = False
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
    "DOCKER_NETWORK_NAME", "sds-jupyter-prod-net-clients"
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

# === AUTHENTICATION AND ACCCESS CONTROL ===
# reference: https://jupyterhub.readthedocs.io/en/latest/reference/api/auth.html
c.JupyterHub.authenticator_class = "oauthenticator.auth0.Auth0OAuthenticator"
c.Authenticator.auto_login = False
c.Authenticator.enable_auth_state = True

env_allowed_groups = os.environ.get("JUPYTERHUB_ALLOWED_GROUPS", "")
allowed_groups: set[str] = {
    g.strip() for g in env_allowed_groups.split(",") if g.strip()
}

env_allowed_users = os.environ.get("JUPYTERHUB_ALLOWED_USERS", "")
allowed_users: set[str] = {u.strip() for u in env_allowed_users.split(",") if u.strip()}

env_admin_users = os.environ.get("JUPYTERHUB_ADMIN_USERS", "admin")
admin_users: set[str] = {a.strip() for a in env_admin_users.split(",") if a.strip()}

# Production validation: require explicit user/group restrictions
if not allowed_users and not allowed_groups:
    error_msg = (
        "SECURITY ERROR: No user/group in the allow list. "
        "Set JUPYTERHUB_ALLOWED_USERS or JUPYTERHUB_ALLOWED_GROUPS "
        "in production to prevent unauthorized access."
    )
    raise ValueError(error_msg)

if allowed_users:
    c.Authenticator.allowed_users = allowed_users
    c.Auth0OAuthenticator.allowed_users = allowed_users
    # admin_users are always allowed
if allowed_groups:
    c.Authenticator.allowed_groups = allowed_groups
    c.Authenticator.manage_groups = True
    c.Auth0OAuthenticator.allowed_groups = allowed_groups
    c.Auth0OAuthenticator.manage_groups = True
if admin_users:
    c.Authenticator.admin_users = admin_users
    c.Auth0OAuthenticator.admin_users = admin_users

# auth0 configuration
# reference: https://oauthenticator.readthedocs.io/en/stable/reference/api/gen/oauthenticator.auth0.html
c.Auth0OAuthenticator.allow_all = False
c.Auth0OAuthenticator.auth0_domain = os.environ.get("AUTH0_DOMAIN")
c.Auth0OAuthenticator.client_id = os.environ.get("AUTH0_CLIENT_ID")
c.Auth0OAuthenticator.client_secret = os.environ.get("AUTH0_CLIENT_SECRET")
c.Auth0OAuthenticator.oauth_callback_url = (
    f"https://{os.environ.get('JUPYTERHUB_HOST', 'localhost:8888')}/hub/oauth_callback"
)
c.Auth0OAuthenticator.scope = ["openid", "email", "profile"]
c.Auth0OAuthenticator.username_key = "email"

# === OTHER CONFIGURATION ===

# Configure proxy PID file to use writable directory
c.ConfigurableHTTPProxy.pid_file = "/data/jupyterhub-proxy.pid"
