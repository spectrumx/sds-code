# Detailed Deployment Instructions

This file contains additional documentation on the deployment process for the SpectrumX
Data System (SDS) Gateway component, in case the automated script in the main README
does not cover your use case.

+ [Detailed Deployment Instructions](#detailed-deployment-instructions)
    + [Development environment](#development-environment)
    + [Local deploy](#local-deploy)
        + [A. Automated (recommended)](#a-automated-recommended)
        + [B. Manual (if needed)](#b-manual-if-needed)
    + [First deployment: automated](#first-deployment-automated)
    + [First deployment: not automated](#first-deployment-not-automated)
    + [Debugging tips](#debugging-tips)
    + [Production deploy](#production-deploy)
        + [Setting production secrets](#setting-production-secrets)
        + [Deploy the production gateway](#deploy-the-production-gateway)
    + [OpenSearch Query Tips](#opensearch-query-tips)

## Development environment

System dependencies

```bash
# dev bindings for python and postgres
sudo apt install python3-dev libpq-dev # on ubuntu
sudo dnf install python3-devel postgresql-devel # on RHEL

# get psql, createdb, etc.
sudo apt install postgresql-client
sudo dnf install postgresql
```

Python dependencies

`pip` can be used, but the easiest and fastest way is to use `uv` ([installing
`uv`](https://docs.astral.sh/uv/getting-started/installation/)). If you still want to
use `pip`, consider the compatible and faster alternative `uv pip` (e.g. `alias pip=uv
pip`).

```bash
uv sync --frozen --extra local
# --frozen does not upgrade the dependencies
# --extra local installs the required dependencies + 'local' ones (for local development)
```

> [!NOTE]
> When using `uv`, all base, local, and production dependencies are described in
> the `pyproject.toml` file.
>
> If you're using `pip`, refer to the `requirements/` directory.

Install pre-commit hooks to automatically run linters, formatters, etc. before
committing:

```bash
uv run --extra local pre-commit install
```

## Local deploy

Choose the automated or manual deploy method below:

> [!IMPORTANT]
> If you ran the `deploy.sh` script from the main README, skip to the [first deployment:
> not automated](#first-deployment-not-automated) section below.

### A. Automated (recommended)

> [!IMPORTANT]
> Skip this section if you ran the `deploy.sh` script from the main README.

1. Generate secrets:

    > [!TIP]
    > You can ignore "file does not exist" warnings when running the "just"
    > recipe below.

    ```bash
    just generate-secrets local
    # or: ./scripts/generate-secrets.sh local
    ```

    This generates random secure secrets in `.envs/local/*.env` files automatically.

2. Deploy Compose stack

    ```bash
    just redeploy
    ```

Then proceed to the [first deployment steps](#first-deployment-automated) below.

### B. Manual (if needed)

> [!IMPORTANT]
> Skip this section if you ran the `deploy.sh` script from the main README.

1. Set secrets:

    ```bash
    rsync -aP ./.envs/example/ ./.envs/local
    # manually set the secrets in .envs/local/*.env files
    ```

    > [!NOTE]
    > In `minio.env`, set `AWS_SECRET_ACCESS_KEY == MINIO_ROOT_PASSWORD`;
    >
    > In `django.env`, to generate the `API_KEY` get it running first, then navigate to
    > [localhost:8000/users/generate-api-key](http://localhost:8000/users/generate-api-key).
    > Copy the generated key to that file. The key is not stored in the database, so you
    > will only see it at creation time.
    >
    > For CI/ephemeral environments, see
    > [docs/github-actions-ephemeral-env.md](docs/github-actions-ephemeral-env.md)

2. Docker compose deploy:

    Either create an `sds-network-local` network manually, or run the [Traefik
    service](../network/compose.yaml) that creates it:

    ```bash
    docker network create sds-network-local --driver=bridge
    ```

    Then, run the services:

    ```bash
    just up
    ```

    If you have issues with static files, you can check which ones are being generated
    by the node service:

    ```bash
    http://localhost:3000/webpack-dev-server
    ```

3. Make Django migrations and run them:

    ```bash
    just uv run manage.py makemigrations
    just uv run manage.py migrate
    ```

## First deployment: automated

> [!IMPORTANT]
> These are "automated" steps because they are covered by the `deploy.sh` script from
> the main README. If you ran that script, you can skip to the next section.

This applies for both local and production deploys, but the names of the containers will
differ.

1. Create the first superuser:

    ```bash
    just uv run manage.py createsuperuser
    ```

2. Initialize OpenSearch indices

    ```bash
    just uv run manage.py init_indices
    ```

    This also tests the connection between the application and the OpenSearch instance.

3. Create the MinIO bucket:

    Go to [localhost:9001](http://localhost:9001) (or `localhost:19001` in production)
    and create a bucket named `spectrumx` with the credentials set in `minio.env`.
    Optionally apply a storage quota to this bucket (you can modify it later if needed).

## First deployment: not automated

Steps are not covered by the `deploy.sh` script and/or items that walk you through
accessing the Gateway for the first time.

1. Access the web interface:

    Open the web interface at [localhost:8000](http://localhost:8000) (`localhost:18000`
    in production). You can create regular users by signing up there, or:

    You can sign in with the superuser credentials at
    [localhost:8000/admin](http://localhost:8000/admin) (or
    `localhost:18000/<admin-path-set-in-django.env>` in production) to access the admin
    interface.

    > [!TIP]
    > The superuser credentials are the ones provided in a step above, or during an
    > interactive execution of the `deploy.sh` script.
    > If the credentials were lost, you can reset the password with:
    >
    > ```bash
    > just uv run manage.py changepassword <email>
    > ```
    >
    > Or create one:
    >
    > ```bash
    > just uv run manage.py createsuperuser
    > ```

2. Run the test suite:

    ```bash
    just test

    # in production, `node` is not a service, so run only the python tests:
    # just test-py
    ```

    Template checks are also run as part of `just test`.

    Alternatively, run them as:

    ```bash
    just uv run manage.py validate_templates
    just uv run pytest
    ```

## Debugging tips

+ Where are my static files served from?
    + See [localhost:3000/webpack-dev-server](http://localhost:3000/webpack-dev-server).
+ What is the URL to X / how to see my routing table?
    + `just uv run manage.py show_urls`.
    + `show_urls` is provided by `django-extensions`.

## Production deploy

> [!TIP]
>
> The production deploy uses the same host ports as the local one, just prefixed with
> `1`: (`8000` → `18000`).
>
> This means you can deploy both on the same machine e.g. dev/test/QA/staging and
> production as "local" and "prod" respectively. This works as they also use different
> docker container, network, volume, and image names. Traefik may be configured to route
> e.g. `sds.example.com` and `sds-dev.example.com` to the prod and local services
> respectively, using different container names and ports.

Keep this in mind, however:

> [!CAUTION]
>
> Due to the bind mounts of the local deploy, it's still recommended to use different
> copies of the source code between a 'local' and 'production' deploy, even if they are
> on the same machine.
>

### Setting production secrets

```bash
rsync -aP ./.envs/example/ ./.envs/production
# manually set the secrets in .envs/production/*.env files
```

> [!NOTE]
> Follow these steps to set the secrets:

+ Set most secrets, passwords, tokens, etc. to random values. You can use the
    following one-liner and adjust the length as needed:

    ```bash
    echo $(head /dev/urandom | tr -dc 'a-zA-Z0-9' | head -c 40)
    ```

+ In `minio.env`, **`AWS_SECRET_ACCESS_KEY` must be equal to
    `MINIO_ROOT_PASSWORD`**;
+ In `django.env`, the **`DJANGO_ADMIN_URL` must end with a slash `/`**.
+ In `django.env`, to generate the `API_KEY` get it running first, then navigate to
    [localhost:18000/users/generate-api-key-form](http://localhost:18000/users/generate-api-key-form/)
    (or this path under your own domain).
    + **Copy the generated key to that env file**. The key is not stored in the
        database, so you will only see it at creation time.
+ In `django.env`, configure OAuth in Auth0's dashboard and **set the `CLIENT_ID`
    and `CLIENT_SECRET`** accordingly.
+ In `postgres.env`, don't forget to **set `DATABASE_URL` to match the user,
    password, and database name** in that file.
+ If using the Spectrum Visualization Interface (SVI) component:
    + In `django.env`, set the `SVI_SERVER_EMAIL` and `SVI_SERVER_API_KEY` to match the
        values in the SVI's environment variables. Important: `SVI_SERVER_API_KEY` must be
        40 characters.

Add the machine's hostname to `./scripts/prod-hostnames.env`:

```bash
cp ./scripts/prod-hostnames.example.env ./scripts/prod-hostnames.env
hostname >> ./scripts/prod-hostnames.env

# to check the selected environment:
just env
```

### Deploy the production gateway

Either create an `sds-network-prod` network manually, or run the [Traefik
service](../network/compose.yaml) that creates it:

```bash
docker network create sds-network-prod --driver=bridge
```

Generate the OpenSearch certificates:

```bash
opensearch/generate_certs.sh
ls -alh ./opensearch/data/certs/
ls -alh ./opensearch/data/certs-django/
```

Set stricter permissions to config

```bash
chmod -v 600 compose/*/opensearch/opensearch.yaml
```

Build the OpenSearch service with the right env vars to avoid permission errors in
`opensearch`:

```bash
# edit `opensearch.env` with the UID and GID of the host
"${EDITOR:nano}" .envs/production/opensearch.env

# build the modified opensearch image
just dc build opensearch
```

Then, run the services:

```bash
just dc up
```

`just dc` is equivalent to the `docker compose ...` command, but it's
environment-aware, so you can use it for both local and production deploys seamlessly.

Run `just env` to see which environment is currently selected, and change the
`scripts/prod-hostnames.env` to add or remove the current host from the list of
production hosts.

> [!TIP]
>
> When restarting, **don't forget to re-build it**, as this deploy doesn't use a
> bind mount to the source code:
>
> ```bash
> just dc build && just dc down; just dc up -d; just logs
> # this is roughly equivalent to `just redeploy`
> ```

1. Make Django **migrations** and run them:

    ```bash
    just uv run manage.py makemigrations
    just uv run manage.py migrate

    # equivalent to:
    # docker exec -it sds-gateway-prod-app bash -c "uv run manage.py makemigrations && uv run manage.py migrate"
    ```

2. Create the first **superuser**:

    ```bash
    just uv run manage.py createsuperuser
    # equivalent to:
    # docker exec -it sds-gateway-prod-app uv run manage.py createsuperuser

    # if you forget or lose the superuser password, you can reset it with:

    just uv run manage.py changepassword <email>
    # equivalent to:
    # docker exec -it sds-gateway-prod-app uv run manage.py changepassword <email>
    ```

3. Try the **web interface** and **admin panel**:

    Open the web interface at [localhost:18000](http://localhost:18000). You can create
    regular users by signing up there.

    You can sign in with the superuser credentials at `localhost:18000/<admin path set
    in django.env>` to access the admin interface.

4. MinIO setup:

    This is a multi-drive, single-node setup of MinIO. For a distributed setup
    (multi-node), see the [MinIO
    documentation](https://min.io/docs/minio/linux/operations/install-deploy-manage/deploy-minio-multi-node-multi-drive.html#deploy-minio-distributed).

    >[!NOTE]
    >
    > We're using `local` in the example commands below as our MinIO alias. Change it
    > accordingly if you're using a different alias in your MinIO configuration.

    1. Establish the connection alias:

        ```bash
        just dc exec minio mc alias set local http://127.0.0.1:9000 minioadmin
        # paste your MinIO credentials from .envs/production/minio.env;
        # change `minioadmin` above to match that file, if needed.

        # in prod, that is equivalent to:
        # docker exec -it sds-gateway-prod-minio mc alias set local http://127.0.0.1:9000 minioadmin
        ```

        Optionally, set up a local `mc` client if you're managing the cluster remotely:

        ```bash
        mc alias set local http://<minio_host>:19000 <minio_user> <minio_password>
        ```

    2. Set admin settings:

        + [MinIO reference
          document](https://github.com/minio/minio/blob/master/docs/config/README.md)

        ```bash
        # enable object compression for all objects, except the ones excluded by default
        # NOTE: compression is not recommended by MinIO when also using encryption.
        mc admin config set local compression enable=on extensions= mime_types=

        # https://min.io/docs/minio/container/administration/object-management/data-compression.html#id6

        # erasure coding settings
        # refer to the docs for these erasure coding settings, if:
        #   1. You are using multiple nodes; or
        #   2. Targeting a number of disks different than 8; or
        #   3. Targeting a different failure tolerance than 2 failed disks; or
        #   4. Targeting a storage efficiency (usable storage ratio) different than 75%.
        # References:
        # https://min.io/docs/minio/linux/reference/minio-server/settings/storage-class.html#mc-conf.storage_class.standard
        # https://min.io/product/erasure-code-calculator
        mc admin config set local storage_class standard=EC:2
        mc admin config set local storage_class rrs=EC:1

        ```

    3. Create the MinIO bucket:

        ```bash
        mc mb local/spectrumx
        ```

    4. (Optional) Diagnostic checks:

        Check the output of these commands to make sure everything is as expected:

        ```bash
        mc admin info local
        mc admin config get local

        # --- cluster health

        # liveness check
        curl -I "http://localhost:19000/minio/health/live"
        # A response code of 200 OK indicates the MinIO server is online and functional.
        # Any other HTTP codes indicate an issue with reaching the server, such as a
        # transient network issue or potential downtime.

        # write quorum check
        curl -I "http://localhost:19000/minio/health/cluster"
        # a response code of 200 OK indicates that the MinIO cluster has sufficient MinIO
        # servers online to meet write quorum. A response code of 503 Service Unavailable
        # indicates the cluster does not currently have write quorum.

        # --- watching logs
        mc admin trace local
        # press Ctrl-C to stop watching
        ```

    5. (Optional) Prometheus monitoring

        ```bash
        mc admin prometheus generate local
        # paste output to your `prometheus.yaml`
        ```

5. Set correct **permissions for the media volume**:

    The app container uses a different pair of UID and GID than the host machine, which
    prevents the app from writing to the media volume when users upload files. To fix
    this, run the following command:

    ```bash
    # check the uid and gid assigned to the app container
    docker exec -it sds-gateway-prod-app id

    # change the ownership of the media volume to those values
    docker exec -it -u 0 sds-gateway-prod-app chown -R 100:101 /app/sds_gateway/media/
    ```

6. OpenSearch adjustments

    If you would like to modify the OpenSearch user permissions setup (through the
    security configuration), see the files in `compose/production/opensearch/config`
    (and reference the [OpenSearch documentation for these
    files](https://opensearch.org/docs/latest/security/configuration/yaml/)):

    + `internal_users.yml`: In this file, you can set initial users (this is where the
      `OPENSEARCH_USER` and admin user are set).

    + `roles.yml`: Here, you can set up custom roles for users. The extensive list of
      allowed permissions can be found
      [here](https://opensearch.org/docs/latest/security/access-control/permissions/).

    + `roles_mapping.yml`: In this file, you can map roles to users defined in
      `internal_users.yml`. It is necessary to map a role directly to a user by adding
      them to the `users` list when using HTTP Basic Authentication with OpenSearch and
      not an external authentication system.

    You can restart the OpenSearch Docker container to reflect the changes, or run the
    following command to confirm changes:

    ```bash
    docker exec -it sds-gateway-prod-opensearch /usr/share/opensearch/plugins/opensearch-security/tools/securityadmin.sh \
        -cd /usr/share/opensearch/config/opensearch-security/ -icl -nhnv \
        -cacert /usr/share/opensearch/config/certs/root-ca.pem \
        -cert /usr/share/opensearch/config/certs/admin.pem \
        -key /usr/share/opensearch/config/certs/admin-key.pem
    ```

    > [!TIP]
    > If you want to reserve users or permissions so they cannot be changed
    > through the API and only through running the `securityadmin.sh` script, set a
    > parameter on individual entries: `reserved: true`.
    >
    > If you would like to preserve changes to your `.opendistro_security` (e.g. users
    > or roles you have added through the API), add the `-backup` flag before running
    > the script. Use the `-f` flag instead of the `-cd` flag if you would like to only
    > update one of the config files. See the [OpenSearch
    > documentation](https://opensearch.org/docs/latest/security/configuration/security-admin/#a-word-of-caution)
    > on the nuances of this script for more information.

7. Run the Django **test** suite:

    ```bash
    just uv run manage.py test
    # equivalent to:
    # docker exec -it sds-gateway-prod-app uv run manage.py test
    ```

8. Don't forget to **approve users** to allow them to create API keys.

    You can do this by logging in as a superuser in the admin panel and enabling the
    `is_approved` flag in the user's entry. This will give that user permission to
    generate and use API keys to interact with the SDS programmatically.

## OpenSearch Query Tips

The API gives the user the ability to search captures using their metadata properties
indexed in OpenSearch. To do so, you must add `metadata_filters` to your request to the
capture listing endpoint.

The `metadata_filters` parameter is a JSON encoded list of dictionary objects which
    contain: + `field_path`: The path to the document field you want to filter by. +
    `query_type`: The OpenSearch query type defined in the [OpenSearch
    DSL](https://opensearch.org/docs/latest/query-dsl/) + `filter_value`: The value, or
    configuration of values, you want to filter for.

For example:

```json
{
    "field_path": "capture_props.<field_name>",
    "query_type": "match",
    "filter_value": "<field_value_to_match>"
}
```

> [!NOTE]
> You do not have to worry about building nested queries. The API handles
> nesting based on the dot notation in the `field_path`. Only provide the inner-most
> `filter_value`, the actual filter you want to apply to the field, when constructing
> filters for requests.

To ensure your filters are accepted by OpenSearch, you should reference the OpenSearch
query DSL [documentation](https://opensearch.org/docs/latest/query-dsl/) for more
details on how filters are structured. The API leaves this structure up to the user to
construct to allow for more versatility in the search functionality.

Here are some useful examples of advanced queries one might want to make to the SDS:

1. Range Queries

    Range queries may be performed both on numerical fields as well as on date fields.

    Let's say you want to search for captures with a center frequency within the range
    1990000000 and 2010000000. That filter would be constructed like this:

    ```json
        {
            "field_path": "capture_props.center_freq",
            "query_type": "range",
            "filter_value": {
                "gte": 1990000000,
                "lte": 2010000000
            }
        }
    ```

    Or, let's say you want to look up captures uploaded in the last 6 months:

    ```json
        {
            "field_path": "created_at",
            "query_type": "range",
            "filter_value": {
                "gte": "now-6M"
            }
        }
    ```

    >[!Note]
    > `now` is a keyword in OpenSearch that refers to the current date and time.

    More information about `range` queries can be found
    [here](https://opensearch.org/docs/latest/query-dsl/term/range/).

2. Geo-bounding Box Queries

    Geo-bounding box queries are useful for finding captures based on the GPS location
    of the sensor. They allow you to essentially create a geospatial window and query
    for captures within that window. This type of filter can only be performed on
    `geo_point` fields. The SDS creates `coordinates` fields from latitude and longitude
    pairs found in the metadata.

    For example, the following filter will show captures with a latitude that is between
    20° and 25° north, and a longitude that is between 80° and 85° west:

    ```json
        {
            "field_path": "capture_props.coordinates",
            "query_type": "geo_bounding_box",
            "filter_value": {
                "top_left": {
                    "lat": 25,
                    "lon": -85,
                },
                "bottom_right": {
                    "lat": 20,
                    "lon": -80
                }
            }
        }
    ```

    More information about `geo_bounding_box` queries can be found
    [here](https://opensearch.org/docs/latest/query-dsl/geo-and-xy/geo-bounding-box/).

3. Geodistance Queries

    Geodistance queries allow you to filter captures based on their distance to a
    specified GPS location. Another useful query for GPS data.

    The following filter looks for captures with 10 mile radius of the University of
    Notre Dame campus, main building (approximately: 41.703, -86.243):

    ```json
        {
            "field_path": "capture_props.coordinates",
            "query_type": "geo_distance",
            "filter_value": {
                "distance": "10mi",
                "capture_props.coordinates": {
                    "lat": 41.703,
                    "lon": -86.243
                }
            }
        }
    ```

   More information about `geo_distance` queries can be found
   [here](https://opensearch.org/docs/latest/query-dsl/geo-and-xy/geodistance/).
