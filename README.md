# SpectrumX Data System | SDK and Gateway

**Code for the SpectrumX Data System (SDS) SDK and Gateway.**

The SDK (Software Dev Kit) here is a reference implementation in Python to interact with the API exposed by the Gateway.

The SDK is the primary form that clients interact with SDS: either directly by installing the Python package from PyPI, or indirectly by using the SDS Web UI or the Visualization Component.

Clients may use the SDK to authenticate, to push and pull data from SDS, and to discover assets stored in the system. In general, basic CRUD operations on SDS entities are to be eventually supported by this system. At a high level:

```txt
+-----------+          +--------+            +---------+            +---------------+
|           | 1. Auth  |        | 2. API     |         | 3. Data    |               |
|           |<-------->|        | Requests+  |         | Requests+  |               |
|  Client   |          |  SDK   | responses  | Gateway | responses  | SDS Data Store|
|           |          |        |            |         |            |               |
|           |<-------->|        |<---------->|         |<---------->|               |
|           | 4. User  |        |            |         |            |               |
|           |    Reqs. |        |            |         |            |               |
|           |          |        |            |         |            |               |
+-----------+          +--------+            +---------+            +---------------+
```

## More docs

+ [Gateway](./gateway/README.md)
+ [SDK](./sdk/README.md)

## Auth0

1. Add the following to the `.envs/local/django.env` file:

    ```txt
    AUTH0_DOMAIN=https://[DOMAIN].us.auth0.com
    ```

2. Add a `Social Application` in the Django Admin for Auth0

    + Provider: `Auth0`
    + Provider ID: `auth0`
    + Name: `SpectrumX Auth0 Provider`
    + Client ID: `[CLIENT_ID]`
    + Secret: `[SECRET]`
    + Key: `auth0`
    + Sites: `[CONFIGURED SITE]` (localhost:8000, etc.)

3. Login through the social application by visiting the login page at `/accounts/auth0/login`
