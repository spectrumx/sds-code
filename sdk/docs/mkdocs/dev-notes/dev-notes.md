# SDK Development Notes

+ [SDK Development Notes](#sdk-development-notes)
    + [Supported Python Versions](#supported-python-versions)
    + [Design Goals](#design-goals)
    + [Directories as Attributes](#directories-as-attributes)

## Supported Python Versions

Maintaining older Python versions has a cost. The SpectrumX SDK aims to support the
**4 most recent stable versions of Python at any given time**, dropping support to the
oldest Python versions, in accordance to the [Scientific Python Ecosystem Coordination
recommendation](https://scientific-python.org/specs/spec-0000/).

Current SDK support is for Python 3.11, 3.12, 3.13, and 3.14. When support to a
new Python version becomes stable, support to the oldest interpreter will be dropped in
new releases.

Support for Python 3.10 will be dropped in late 2025 and for Python 3.11 in late 2026.

+ [Python release calendar](https://devguide.python.org/versions/)

## Design Goals

For a stable "v1" release and in no particular order:

1. **Unified APIs for File Operations**

    Implement a cohesive and simplified set of methods for common file operations such
    as upload, download, delete, list, and move.

2. **Object-Oriented Approach**

    The SDK handles files and directories as objects, making their properties (metadata)
    and methods (actions) easily available and discoverable in text editors and IDEs.

3. **Multipart Down/Uploads and Fault Tolerance**

    Implement support for multipart transfers, especially useful for large files.
    Uploads and downloads should be resumable if possible. Uploads and downloads should
    be fault-tolerant, meaning they are to be made idempotent and atomic at the smallest
    unit of operation (file contents + metadata). Integration tests should cover these
    scenarios.

4. **Access Control and Authentication**

    Token-based authentication and authorization will be used for secure access to SDS
    assets. In the stable release of the SDK, all requests must use TLS (HTTPS
    enforced). Assets are only editable by their owners or SDS administrators.
    Enforcement of these access control policies will be done at the server level (SDS
    Gateway).

5. **Caching and Optimization**

    Requests that return iterators should be paginated and/or lazy-loaded (e.g. with
    generators). Caching should be used to reduce the number of requests to the server
    and reduce bandwidth usage. The SDK must offer a global flag to disable all SDK
    caching (e.g. for tests, debugging, or even user control). The SDK must
    automatically skip operations that were already performed (when possible to tell)
    _and_ are idempotent (e.g. re-downloading or re-uploading the same file, recreating
    the same dataset). As with caching, the user should be able to manually disable this
    SDK's auto-skip optimization with an optional flag passed to the method e.g.
    `force_download=True`.

6. **Scalability and Concurrency**

    The SDK should be able to handle multiple network requests concurrently, especially
    for large file transfers. This can be achieved with a connection pool and `asyncio`.

    **Impl. idea:** to prevent larger file transfers taking all connections and improve
    the instant file throughput, we could run two kinds of pools concurrently: one long
    (for the larger files) and one short (for the smaller ones).

    **Note on concurrent writes / warning to users:** do not run concurrent scripts
    and/or multiple processes that use SDS SDK clients for writes. It is out of the
    scope for the SDK to protect data from concurrent writes from multiple processes
    that use the SDK connected to the same host (as in running the same SDK script more
    than once and concurrently). In that case, the system is likely to enter a
    "last-writer-wins" conflict resolution, which may incur loss of data. Since writes
    are limited to the data owner, this potential data loss is limited to a single user
    running instances writing to the same locations. Preventing this would require the
    implementation of ACID-like transactions for resource locking at the server side,
    thus increasing development time.

7. **Error handling and user feedback**

    The SDK should handle warnings and errors from the server in a user-friendly way.
    Warnings deliver information that might require user action soon, while errors
    require immediate attention. Success messages, when enabled, should be informative
    and concise. On exceptions, the SDK should raise exceptions related to the operation
    that failed, for example, if a dataset metadata update failed, prefer something like
    `DatasetUpdateError` over a generic `HTTPError` with code status code 400.

8. **Data content and space management**

    User feedback should be provided when the user is about to exceed their storage
    quota. The SDK should also provide a way to check the user's storage usage and
    quota. The SDK should skip forbidden file extensions and MIME types automatically
    and warn the user about them. Both quota limits and content types are enforced at
    the server level, the SDK merely provides a more user-friendly and contextual
    interface.

## Directories as Attributes

There are many benefits of treating directories as attributes (assume `<path>` equals to
`<directory>/<filename>`):

1. **Separation of concerns:** SDS and clients have different goals when it comes to
   file organization. Directories as attributes let users organize their files in ways
   that make sense to them without affecting SDS.
2. **Update performance:** when users change their file trees and tell the SDK
   "re-upload" them, all the SDK has to do is detect the files moved, then issue the
   proper commands for the server to update those attributes. This prevents same content
   re-upload and updating database attributes is also faster than moving files.
3. **Access performance:** querying rows from a database is faster than traversing a
   file system when listing files and directories. Directory attributes can be sorted,
   cached, indexed, and filtered efficiently. Storing these files in a file system _as
   well as_ creating their database entries would lead to multiple sources of truth and
   potential inconsistencies over time.
4. **Reliability:** in case of interruption, a move operation is harder to recover from
   than an attribute update; the latter is also easier to model as an atomic database
   transaction and give immediate feedback to the user.
5. **No empty directories:** a path (and its directory) only exists if there is a file
   "in" it.
6. **Orthogonal soft deletions:** the directory attribute can be preserved in the case
   of deletions, making "un-deletions" faster and more reliable.
7. **File versioning for free:** if a new file has the same path as an existing one, the
   server will store both by their checksums and the SDK can indicate there are multiple
   versions available when listing by path.
8. **File duplication:** if a file the server already has is re-uploaded, the SDK can
   avoid the extraneous data transfer and an additional "file" row can be created
   pointing to an already existing file on the server's disk.
