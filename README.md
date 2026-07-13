# SpectrumX Data System | SDK and Gateway

> Code for the SpectrumX Data System SDK and Gateway.

---------------------------------------------------------

> [!NOTE] The SDK and Gateway are under active development and features might not be
> implemented or change. Reach out to the maintainers for more information.

The SpectrumX Data System (SDS) is a system for storing and managing radio-frequency
data in a distributed, scalable, and secure manner. The SDS consists of two main
components that are in this project:

## The Gateway

The **Gateway** is a Django web application to manage the data store and expose an API
for clients to interact with the system.

The Gateway is the closest interface to the stored data. It provides a RESTful API for
clients to authenticate, push and pull data, and discover assets stored in the system.
The Gateway also features a web-based user interface for clients to interact with the
system.

### Container Image

Pre-built Docker images for the Gateway are published to GitHub Container Registry:

```text
ghcr.io/spectrumx/sds-gateway
```

> **URL:** <https://github.com/spectrumx/sds-code/pkgs/container/sds-gateway>

Two main tags are available:

| Tag | Source | Use Case |
|-----|--------|----------|
| `:stable` | [Promoted](https://github.com/spectrumx/sds-code/actions/workflows/gwy-promote-stable.yaml) from a verified `dev-<sha>` build | **Recommended for production deployments.** A specific commit manually promoted after passing all checks. |
| `:dev` | Latest build from the `master` branch | Latest code, may include unreviewed changes. Suitable for staging, testing, or early evaluation. |
| `:dev-<sha>` | Per-commit builds from `master` | Pinned to a specific commit for traceability. Useful when you need an exact version between `dev` and a `stable` promotion. |

> [!TIP] Production deployments should use the `:stable` tag. The Gateway's production
> Compose file defaults to `:stable` (`SDS_GATEWAY_TAG=stable`), and the
> `gwy-promote-stable` workflow is used to promote verified builds from `master`.

## The SDK

The **SDK** (Software Dev Kit) here is a reference implementation in Python to interact
with the API exposed by the Gateway.

The SDK is the primary form that Python clients interact with SDS: either directly by
installing the [Python package from PyPI](https://pypi.org/project/spectrumx/), or
indirectly by using the [SpectrumX Visualization
Platform](https://github.com/spectrumx/svi-code).

Clients may use the SDK to authenticate, to push and pull data from SDS, and to discover
assets stored in the system. In general, basic CRUD operations on SDS entities are to be
eventually supported by this system.

## More docs

+ [Gateway Readme](./gateway/README.md)
+ [SDK README](./sdk/README.md)
+ [SpectrumX Visualization Platform](https://github.com/spectrumx/svi-code)
