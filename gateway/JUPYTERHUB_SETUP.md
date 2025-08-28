# JupyterHub Setup: Local vs Production

## 🎯 **Authentication Strategy**

### **Local Development** 🚀

- **Simple authentication** with username/password
- **No external dependencies** required
- **Quick setup** for development and testing
- **Login**: `admin` / `admin`

### **Production** 🔒

- **OAuth authentication** via Auth0
- **Secure enterprise authentication**
- **SSL/TLS encryption**
- **Professional user management**

## 📁 **File Structure**

```text
gateway/
├── compose/
│   ├── local/jupyter/           # Local development (no OAuth)
│   │   ├── Dockerfile
│   │   ├── jupyterhub_config.py # DummyAuthenticator
│   │   ├── requirements.txt     # No oauthenticator
│   │   └── README.md
│   └── production/jupyter/      # Production (with OAuth)
│       ├── Dockerfile
│       ├── jupyterhub_config.py # Auth0OAuthenticator
│       ├── requirements.txt     # Includes oauthenticator
│       └── README.md
├── .envs/
│   ├── local/jupyterhub.env     # Local env (minimal)
│   └── production/jupyterhub.env # Production env (OAuth config)
└── compose.local.yaml            # Local services
    └── compose.production.yaml  # Production services
```

## 🔧 **Local Development**

### **Current Status**: ✅ Working

- **Port**: 8888
- **URL**: <http://localhost:8888>
- **Authentication**: Simple local
- **Dependencies**: Minimal

### **Start Local Services**

```bash
cd gateway
docker-compose -f compose.local.yaml up -d
```

### **Access JupyterHub**

- Open <http://localhost:8888>
- Login: `admin` / `admin`
- Start creating notebooks!

## 🚀 **Production Deployment**

### **Current Status**: ✅ Ready

- **Port**: 18888
- **Authentication**: OAuth via Auth0
- **Security**: SSL/TLS ready
- **Dependencies**: Full OAuth stack

### **Configure Production**

1. **Edit** `.envs/production/jupyterhub.env`
2. **Set** Auth0 credentials
3. **Configure** SSL certificates
4. **Deploy** with production compose

### **Start Production Services**

```bash
cd gateway
docker-compose -f compose.production.yaml up -d
```

## 🔄 **Switching Between Configurations**

### **Local → OAuth (for testing)**

1. Edit `compose/local/jupyter/jupyterhub_config.py`
2. Change to `oauthenticator.auth0.Auth0OAuthenticator`
3. Add `oauthenticator` to `requirements.txt`
4. Configure Auth0 in `.envs/local/jupyterhub.env`
5. Restart JupyterHub

### **Production → Local (not recommended)**

- Production should always use OAuth
- Only for emergency maintenance

## 📋 **Environment Variables**

### **Local** (`.envs/local/jupyterhub.env`)

```bash
# Minimal configuration
JUPYTERHUB_CRYPT_KEY=v+TxsSbEdubzX7WT4/7R7cxKXre4NjiGSuXG07xWLWA=
```

### **Production** (`.envs/production/jupyterhub.env`)

```bash
# OAuth configuration
AUTH0_CLIENT_ID=your-production-client-id
AUTH0_CLIENT_SECRET=your-production-client-secret
AUTH0_DOMAIN=your-production-domain.auth0.com
JUPYTERHUB_CRYPT_KEY=v+TxsSbEdubzX7WT4/7R7cxKXre4NjiGSuXG07xWLWA=
JUPYTERHUB_SSL_CERT=/path/to/ssl/cert.pem
JUPYTERHUB_SSL_KEY=/path/to/ssl/key.pem
JUPYTERHUB_HOST=your-domain.com:18888
```

## ✅ **Current Status Summary**

- **Local Development**: ✅ Working with simple auth
- **Production Ready**: ✅ OAuth configuration prepared
- **No OAuth locally**: ✅ Simple development setup
- **Easy switching**: ✅ Configurable for testing OAuth locally
- **Security**: ✅ Production-grade OAuth ready

## 🎉 **Ready to Use!**

Your JupyterHub is now set up for both local development and production deployment:

- **Local**: <http://localhost:8888> (admin/admin)
- **Production**: Configure Auth0 and deploy to port 18888
