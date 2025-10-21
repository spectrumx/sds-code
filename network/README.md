# Network Configuration

+ [Network Configuration](#network-configuration)
    + [Introduction](#introduction)
    + [Quick recipe lookup](#quick-recipe-lookup)
    + [Staging/Production deployment](#stagingproduction-deployment)
    + [Production checklist](#production-checklist)

## Introduction

> [!TIP]
> If deploying SDS in production, start with this README.

This `network` component is a pre-configured deploy of Traefik to act as a reverse proxy
and TLS terminator for the SDS Gateway. It handles incoming HTTP/HTTPS requests, routes
them to the appropriate backend services, and manages TLS certificates.

It is a separate component to allow more flexibility when deploying SDS, as you may
choose a different setup, or not use Traefik at all, depending on your infrastructure
and environment.

## Quick recipe lookup

Install [`just`](https://github.com/casey/just) to use the task runner for high-level
commands:

```bash
just --list
```

```bash
Available recipes:
    build *args      # pulls the required images and rebuilds services with your local changes.
    build-full *args # forces a rebuild without cache for troubleshooting persistent container issues.
    dc *args         # forwards arguments to `docker compose` for ad-hoc commands e.g. `just dc ps`
    down *args       # stops and removes the compose stack
    logs *args       # tails the logs; use `just logs-once` for a single snapshot
    logs-once *args  # shows the logs without tailing
    redeploy         # chains build, down, up, and logs for a full refresh after updates
    restart *args    # restarts running services without rebuilding
    up *args         # starts the stack in detached mode, creating the network if needed [alias: run]
```

## Staging/Production deployment

> [!NOTE]
> Traefik's configuration uses `sds.crc.nd.edu` as the domain name. Replace it with a
> domain you own for a self-hosted deployment. This documentation refers to
> `sds.example.com` as your custom production domain name, and `sds-dev.example.com` as
> your custom staging domain name.

1. Generate Traefik dashboard credentials

    Credentials to access sds.example.com/dashboard/:

    ```bash
    # sudo dnf install httpd-tools
    htpasswd -nB your-user-name >> traefik/credentials.htpasswd
    ```

    Then try it out e.g.:

    ```bash
    curl -u your-user-name:your-password http://sds.example.com/dashboard/
    ```

    > [!IMPORTANT]
    > The trailing slash `/` is required when accessing the dashboard URL.

    or by navigating to the URL in a web browser.

1. Override DNS resolution (optional)

    Overriding the DNS in our staging machine let us use the same configuration file between
    staging and production environment.

    Get the internal IP address of the DNS server:

    ```bash
    ip addr show $(route | grep '^default' | grep -o '[^ ]*$' | head -n 1) | grep -o 'inet [0-9\.+]*' | cut -f2 -d' '
    ```

    Add an entry to `/etc/hosts`:

    ```bash
    # ...
    <dns_ip>    sds.example.com
    # ...
    ```

    Test the DNS resolution, make sure it matches your local IP:

    ```bash
    dig sds.example.com
    ```

1. Update [Traefik's configuration](./traefik/traefik.toml).

    Make sure the domain name, email, and credentials file path match your deployment in
    [./traefik/traefik.toml](./traefik/traefik.toml).

    Changes are applied by Traefik immediately after saving the file. You can confirm
    that by tailing the logs with `just logs`.

1. Generate TLS certificates

    Probably the best option is to use Let's Encrypt in production. The Traefik
    configuration is already set for this use case. If you need more details, check the
    instructions in the [Traefik
    documentation](https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/).
    Note this requires your domain to be publicly reachable.

    Alternatively 1: obtain valid certificates from a trusted Certificate Authority,
    place them in `traefik/data/certs/`, and make sure [Traefik's
    configuration](./traefik/traefik.toml) matches the filenames.

    Alternative 2: use self-signed certificates for development purposes:

    ```bash
    cd traefik/data/certs

    openssl req -x509 -newkey rsa:4096 \
        -keyout private_key.pem -out public_key.crt \
        -days 365 -nodes -subj '/CN=issuer'
    ```

    Use cURL's `--insecure` flag to bypass SSL verification in development environment.

1. (Re-)deploying `network`

    ```bash
    # cd /<repo-root>/network
    just redeploy

    # or alternatively:
    #$ just build
    #$ just down
    #$ just up
    #$ just logs
    ```

    If everything goes well, you should see some Traefik logs. Press Ctrl+C to exit the
    logs and leave the services running in the background.

1. Deploy the web application

    Before reaching SDS, we need to deploy the Gateway, which has our web application:

    Follow the [Gateway README](../gateway/README.md) instructions on how to deploy the web
    application in production mode.

1. Test `network`

    Regular HTTPS requests:

    ```bash
    # static files
    curl --insecure https://sds.example.com/static/css/project.css

    # main application
    curl --insecure https://sds.example.com
    ```

    HTTP redirects:

    ```bash
    # should see 'Moved Permanently'
    curl --insecure http://sds.example.com/static/css/project.css
    curl --insecure http://sds.example.com
    ```

## Production checklist

1. Make sure firewall is up, review rules.

    ```bash
    sudo systemctl status iptables
    sudo iptables --list --line-numbers
    ```

2. Follow the instructions in the [Gateway's README](../gateway/README.md) for deploying
   the web application in production mode.

3. Deploy the network:

    ```bash
    just redeploy
    ```

4. Test requests:

    Check regular HTTPS requests:

    ```bash
    curl https://sds.example.com/static/css/project.css
    curl https://sds.example.com
    ```

    Check HTTP redirects:

    ```bash
    # 'Moved Permanently'
    curl http://sds.example.com/static/css/project.css
    curl http://sds.example.com
    ```

5. Check HTTP and HTTPS ports are allowed from anywhere in the firewall.

    ```bash
    sudo iptables --list --line-numbers | grep '80|443|http'
    ```

6. Test reachability from outside your network, if applicable.
