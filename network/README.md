# Network Configuration

+ [Network Configuration](#network-configuration)
    + [Staging deployment](#staging-deployment)
        + [Override DNS resolution](#override-dns-resolution)
        + [Generate self-signed SSL certificates](#generate-self-signed-ssl-certificates)
        + [Deploying the network](#deploying-the-network)
        + [Test the network](#test-the-network)

## Staging deployment

### Override DNS resolution

Overriding the DNS in our staging machine let us use the same configuration file between staging and production environment.

Get the internal IP address of the DNS server:

```bash
ip addr show $(route | grep '^default' | grep -o '[^ ]*$' | head -n 1) | grep -o 'inet [0-9\.+]*' | cut -f2 -d' '
```

Add an entry to `/etc/hosts`:

```bash
# ...
<dns_ip>    sds.crc.nd.edu
# ...
```

Test the DNS resolution, make sure it matches your local IP:

```bash
dig sds.crc.nd.edu
```

### Generate self-signed SSL certificates

```bash
cd traefik/data/certs

openssl req -x509 -newkey rsa:4096 \
    -keyout private_key.pem -out public_key.crt \
    -days 365 -nodes -subj '/CN=issuer'
```

Use cURL's `--insecure` flag to bypass SSL verification in development environment:

### Deploying the network

```bash
docker compose up -d; docker compose logs -f
```

Restarting / redeploying the network:

```bash
docker compose down; docker compose up -d; docker compose logs -f
```

### Test the network

HTTPS requests:

```bash
curl --insecure https://whoami.sds.crc.nd.edu
curl --insecure https://sds.crc.nd.edu/static/css/project.css
curl --insecure https://sds.crc.nd.edu
```

HTTP redirects:

```bash
# 'Moved Permanently'
curl --insecure http://whoami.sds.crc.nd.edu
curl --insecure http://sds.crc.nd.edu/static/css/project.css
curl --insecure http://sds.crc.nd.edu
```
