# JupyterHub in SDS Gateway

This directory contains the JupyterHub configuration for the SDS Gateway project.

## Authentication Strategy

- **Local Development**: Simple username/password authentication (no OAuth)
- **Production**: OAuth authentication via Auth0

## Local Development

### Current Setup

- **Authenticator**: `jupyterhub.auth.DummyAuthenticator`
- **Login**: Username: `admin`, Password: `admin`
- **No external dependencies** required

### Access

- **URL**: <http://localhost:8888>
- **Port**: 8888 (mapped from container port 8000)

## Production Deployment

### OAuth Setup

- **Authenticator**: `oauthenticator.auth0.Auth0OAuthenticator`
- **Requires**: Auth0 credentials and SSL certificates
- **Port**: 18888 (production)

### Configuration Files

- `compose/production/jupyter/` - Production configuration
- `.envs/production/jupyterhub.env` - Production environment variables

## Files

- `Dockerfile` - JupyterHub container image
- `jupyterhub_config.py` - JupyterHub configuration
- `requirements.txt` - Python dependencies
- `README.md` - This documentation

## Switching to OAuth (Local)

If you want to test OAuth locally:

1. **Edit** `jupyterhub_config.py` to use OAuth authenticator
2. **Configure** Auth0 credentials in `.envs/local/jupyterhub.env`
3. **Add** `oauthenticator` to `requirements.txt`
4. **Restart** JupyterHub

## Current Status

✅ **Local Development**: Working with simple authentication
✅ **Production Ready**: OAuth configuration prepared
✅ **No OAuth locally**: Simple local development setup
