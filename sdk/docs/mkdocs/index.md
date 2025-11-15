# SpectrumX Data System | Python SDK

[![PyPI -
Version](https://img.shields.io/pypi/v/spectrumx)](https://pypi.org/project/spectrumx/)
[![PyPI - Python
Versions](https://img.shields.io/pypi/pyversions/spectrumx)](https://pypi.org/project/spectrumx/)
[![Pepy Total
Downloads](https://img.shields.io/pepy/dt/spectrumx)](https://pypi.org/project/spectrumx/)

[![GitHub](https://img.shields.io/badge/GitHub-Repo-blue)](https://github.com/spectrumx/sds-code/blob/master/sdk/README.md)
[![SDK Code Quality
Checks](https://github.com/spectrumx/sds-code/actions/workflows/sdk-code-quality.yaml/badge.svg)](https://github.com/spectrumx/sds-code/actions/workflows/sdk-code-quality.yaml)
[![SDK Tests
Checks](https://github.com/spectrumx/sds-code/actions/workflows/sdk-cross-platform-tests.yaml/badge.svg)](https://github.com/spectrumx/sds-code/actions/workflows/sdk-cross-platform-tests.yaml)

The SpectrumX Data System (SDS) SDK is a Python package that provides a simple interface
for interacting with the SDS Gateway. The SDK is designed to be easy to use and to
provide a high-level interface for common tasks, such as uploading and downloading
files, searching for files, and managing RF datasets.

## The Gateway

The **Gateway** hosts the user data in the SpectrumX Data System. It is a Django web
application to manage the data store and expose an API for clients to interact with the
system.

The Gateway is the closest interface to the stored data. It provides a RESTful API for
clients to authenticate, push and pull data, and discover assets stored. It also
features a web-based user interface for clients to interact with the system.

## The SDK

The **SDK** (Software Dev Kit) here is a reference implementation in Python to interact
with the API exposed by the Gateway.

The SDK is the primary form that Python clients interact with SDS by
installing the [Python package from PyPI](https://pypi.org/project/spectrumx/).

Clients may use the SDK to authenticate, to push and pull data from SDS, and to discover
assets stored in the system. In general, basic CRUD (Create, Read, Update, Delete)
operations on SDS entities are to be eventually supported by this system.

## See Next

+ [Getting Started](getting-started.md)
+ [Common Workflows](common-workflows.md)
+ [FAQ](faq.md)
+ [Terminology](terminology.md)
+ [Changelog](changelog.md)
