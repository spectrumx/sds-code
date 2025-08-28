# Nginx Configuration for JupyterHub Production

This directory contains nginx configurations for serving JupyterHub in production alongside the main SDS Gateway application.

## Files

- `nginx-default.conf` - Main nginx config with JupyterHub routing
- `jupyterhub.conf` - Separate config for subdomain routing
- `README.md` - This documentation

## Configuration Options

### Option 1: Path-based Routing (Recommended)

**File**: `nginx-default.conf`
**Access**: `https://yourdomain.com/jupyter/`

This configuration:

- Routes JupyterHub under `/jupyter/` path
- Keeps everything on the same domain
- Easier SSL certificate management
- Good for internal/enterprise use

**Usage**:

1. Deploy with the main application
2. Access JupyterHub at `https://yourdomain.com/jupyter/`
3. Update JupyterHub OAuth callback URLs accordingly

### Option 2: Subdomain Routing

**File**: `jupyterhub.conf`
**Access**: `https://jupyter.yourdomain.com/`

This configuration:

- Routes JupyterHub to a separate subdomain
- Cleaner URLs for users
- Can have separate SSL certificates
- Good for public-facing deployments

**Usage**:

1. Copy `jupyterhub.conf` to your nginx sites-available
2. Update `server_name` to your actual domain
3. Configure SSL certificates for the subdomain
4. Update JupyterHub OAuth callback URLs

## Required Updates

### 1. OAuth Callback URLs

When using nginx routing, update your Auth0 configuration:

**Path-based routing**:

```text
https://yourdomain.com/jupyter/hub/oauth_callback
```

**Subdomain routing**:

```text
https://jupyter.yourdomain.com/hub/oauth_callback
```

### 2. JupyterHub Configuration

Update your JupyterHub config to match the nginx routing:

**Path-based routing**:

```python
c.JupyterHub.base_url = '/jupyter/'
```

**Subdomain routing**:

```python
c.JupyterHub.base_url = '/'
```

### 3. SSL/TLS

Ensure your SSL certificates cover:

- **Path-based**: Main domain + `/jupyter/` path
- **Subdomain**: `jupyter.yourdomain.com`

## Security Considerations

- **WebSocket support** enabled for real-time notebook updates
- **Security headers** added for production use
- **CORS configuration** for cross-origin requests
- **Timeout settings** for long-running operations
- **File upload limits** configured (100MB default)

## Testing

### Local Testing

```bash
# Test nginx config syntax
docker exec sds-gateway-prod-nginx nginx -t

# Check nginx logs
docker exec sds-gateway-prod-nginx tail -f /var/log/nginx/error.log
```

### Production Deployment

1. **Update** nginx configuration
2. **Reload** nginx: `nginx -s reload`
3. **Test** JupyterHub access
4. **Verify** OAuth flow works
5. **Monitor** logs for errors

## Troubleshooting

### Common Issues

1. **502 Bad Gateway**: Check if JupyterHub is running
2. **WebSocket errors**: Verify proxy headers are set correctly
3. **OAuth failures**: Check callback URL configuration
4. **Timeout errors**: Adjust proxy timeout settings

### Debug Commands

```bash
# Check nginx status
docker exec sds-gateway-prod-nginx nginx -t

# View nginx logs
docker exec sds-gateway-prod-nginx tail -f /var/log/nginx/error.log

# Test JupyterHub connectivity
curl -I http://jupyter:8000/
```
