# Network Configuration

+ [Network Configuration](#network-configuration)
    + [Staging deployment](#staging-deployment)
        + [Override DNS resolution](#override-dns-resolution)
        + [Generate self-signed SSL certificates](#generate-self-signed-ssl-certificates)
        + [Deploy the web application](#deploy-the-web-application)
        + [Deploying the network](#deploying-the-network)
        + [Test the network](#test-the-network)
    + [Production checklist](#production-checklist)

## Staging deployment

### Generate Traefik dashboard credentials

```bash
# sudo dnf install httpd-tools
htpasswd -nB your-user-name >> traefik/credentials.htpasswd
```

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

### Deploy the web application

Follow the [Gateway README](../gateway/README.md) instructions on how to deploy the web application in production mode.

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

## Production checklist

Same process as staging, without the `/etc/hosts` modification and with additional checks.

1. Make sure firewall is up, review rules.

    ```bash
    sudo systemctl status iptables
    sudo iptables --list --line-numbers
    ```

2. Follow the instructions in the [Gateway's README](../gateway/README.md) for deploying the web application in production mode.

3. Deploy the network:

    ```bash
    docker compose down; docker compose up -d; docker compose logs -f
    ```

4. Test requests:

    HTTPS:

    ```bash
    curl https://whoami.sds.crc.nd.edu
    curl https://sds.crc.nd.edu/static/css/project.css
    curl https://sds.crc.nd.edu
    ```

    HTTP redirects:

    ```bash
    # 'Moved Permanently'
    curl http://whoami.sds.crc.nd.edu
    curl http://sds.crc.nd.edu/static/css/project.css
    curl http://sds.crc.nd.edu
    ```

5. Check HTTP and HTTPS ports are allowed from anywhere in the firewall.

    ```bash
    sudo iptables --list --line-numbers | grep '80|443|http'
    ```

6. Test reachability from outside the network.
