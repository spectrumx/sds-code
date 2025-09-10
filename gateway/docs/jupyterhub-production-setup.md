# JupyterHub Production Setup

Quick guide to get JupyterHub running in production (assumes repository and Docker are already installed).

## 1. Configure Environment

### Set UID/GID for your server

```bash
# Check your user UID/GID
id $USER

# Check docker group GID
getent group docker
```

### Configure JupyterHub environment

```bash
# Edit JupyterHub environment
./.envs/production/jupyterhub.env
```

**Required settings:**

```bash
# User and Group IDs (replace with your server's values)
NB_UID=1000
NB_GID=100
DOCKER_GID=999

# JupyterHub Configuration
JUPYTERHUB_HOST=your-domain.com:18888

# Auth0 Configuration
AUTH0_CLIENT_ID=your-auth0-client-id
AUTH0_CLIENT_SECRET=your-auth0-client-secret
AUTH0_DOMAIN=your-auth0-domain
```
