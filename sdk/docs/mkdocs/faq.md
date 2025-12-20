# Frequently Asked Questions

And others not as much.

+ [Frequently Asked Questions](#frequently-asked-questions)
    + [Getting Started](#getting-started)
        + [What is SDS?](#what-is-sds)
        + [So is the SDS like a Google Drive for RF data?](#so-is-the-sds-like-a-google-drive-for-rf-data)
        + [What is an SDK?](#what-is-an-sdk)
        + [How do I install the SDK?](#how-do-i-install-the-sdk)
        + [What Python versions are supported?](#what-python-versions-are-supported)
        + [How do I set up authentication?](#how-do-i-set-up-authentication)
        + [How to generate a secret token?](#how-to-generate-a-secret-token)
        + [Why can't I generate an API key?](#why-cant-i-generate-an-api-key)
        + [Why is my data not uploaded? | What is dry-run mode?](#why-is-my-data-not-uploaded--what-is-dry-run-mode)
        + [Where can I find code examples?](#where-can-i-find-code-examples)
    + [File Operations](#file-operations)
        + [How do I upload files to the SDS?](#how-do-i-upload-files-to-the-sds)
        + [How do I download files from the SDS?](#how-do-i-download-files-from-the-sds)
        + [Can I resume interrupted uploads or downloads?](#can-i-resume-interrupted-uploads-or-downloads)
        + [How do I handle errors during file operations?](#how-do-i-handle-errors-during-file-operations)
    + [Asset Types and Organization](#asset-types-and-organization)
        + [What is a File | Directory | Capture | Dataset | Experiment?](#what-is-a-file--directory--capture--dataset--experiment)
        + [What are Draft and Final Datasets?](#what-are-draft-and-final-datasets)
        + [Can we share a draft dataset?](#can-we-share-a-draft-dataset)
        + [What's the difference between a Directory and a Dataset?](#whats-the-difference-between-a-directory-and-a-dataset)
        + [What is the difference between a Capture and a Dataset?](#what-is-the-difference-between-a-capture-and-a-dataset)
    + [Data Sharing and Collaboration](#data-sharing-and-collaboration)
        + [How can I share files with other users?](#how-can-i-share-files-with-other-users)
        + [Can I add files to a dataset that was shared with me?](#can-i-add-files-to-a-dataset-that-was-shared-with-me)
    + [Concurrency and Data Safety](#concurrency-and-data-safety)
        + [Can multiple clients write to the same location simultaneously?](#can-multiple-clients-write-to-the-same-location-simultaneously)
        + [Is it safe to have multiple clients reading from the same location?](#is-it-safe-to-have-multiple-clients-reading-from-the-same-location)
        + [Why is the SDK stateless?](#why-is-the-sdk-stateless)
        + [What protections help prevent accidental deletions?](#what-protections-help-prevent-accidental-deletions)
    + [Troubleshooting](#troubleshooting)
        + [I'm getting an `AuthError` when trying to authenticate. What should I check?](#im-getting-an-autherror-when-trying-to-authenticate-what-should-i-check)
        + [I'm getting a `NetworkError`. What does this mean?](#im-getting-a-networkerror-what-does-this-mean)
        + [I'm getting a `ServiceError`. What should I do?](#im-getting-a-serviceerror-what-should-i-do)
        + [My upload/download is very slow or seems stalled. What can I do?](#my-uploaddownload-is-very-slow-or-seems-stalled-what-can-i-do)
        + [I'm seeing an `Internal Server Error` from the Gateway. What now?](#im-seeing-an-internal-server-error-from-the-gateway-what-now)
    + [Advanced Topics](#advanced-topics)
        + [What should I know about concurrent access?](#what-should-i-know-about-concurrent-access)
        + [How do I contribute to the SDK?](#how-do-i-contribute-to-the-sdk)
        + [Does the SDK have a higher verbosity mode for debugging?](#does-the-sdk-have-a-higher-verbosity-mode-for-debugging)
        + [Is there a CLI mode for a quick upload/download?](#is-there-a-cli-mode-for-a-quick-uploaddownload)
        + [Are you planning to support other programming languages?](#are-you-planning-to-support-other-programming-languages)
        + [What are some best practices for using the SDK?](#what-are-some-best-practices-for-using-the-sdk)
    + [Federation](#federation)
        + [What is Federation in SDS?](#what-is-federation-in-sds)
        + [What is the current status of Federation support?](#what-is-the-current-status-of-federation-support)

## Getting Started

### What is SDS?

The SpectrumX Data System (SDS) is a data management platform designed to facilitate the
storage, organization, sharing, and analysis of large-scale Radio Frequency (RF) data.
We aim to provide a unified interface for users to interact with their RF data,
regardless of its source or format.

### So is the SDS like a Google Drive for RF data?

In some ways, yes. The SDS is a platform for storing and managing RF data, similar to
how Google Drive allows users to store and manage files in the cloud. We took
inspiration from them to design some of our features, so onboarding and usage feels
familiar to new users.

However, SDS is specifically tailored for RF data management, and as we mature the
system, we will be adding more specialized features that go beyond general-purpose file
storage solutions. Metadata search, Jupyter Notebooks, and [Federation](#federation) are
some of the key differences between SDS and traditional file storage services.

### What is an SDK?

An SDK, or Software Development Kit, is a collection of tools, libraries, documentation,
and code samples that developers use to create applications for specific platforms or
services.

In this case, the SpectrumX SDK provides a Python interface to interact with the
SpectrumX Data System (SDS) Gateway, allowing users to manage and manipulate RF
data stored within the SDS.

### How do I install the SDK?

You can install the SpectrumX SDK using any of the following package managers:

```bash
uv add spectrumx
poetry add spectrumx
pip install spectrumx
```

The SDK is available on [PyPI](https://pypi.org/project/spectrumx/).

### What Python versions are supported?

The SDK supports the **4 most recent stable versions of Python**. Currently, this
includes Python 3.11, 3.12, 3.13, and 3.14. Support for older versions is dropped when
new Python releases become stable, following the [Scientific Python Ecosystem
Coordination recommendation](https://scientific-python.org/specs/spec-0000/).

Support for Python 3.10 will be dropped in late 2025 and for Python 3.11 in late 2026.

### How do I set up authentication?

The SDK uses token-based authentication. You can provide your secret token in one of two
ways:

**Option 1:** Using a `.env` file (recommended for keeping tokens out of version
control)

Create a `.env` file in your project directory:

```ini
SDS_SECRET_TOKEN=your-secret-token-no-quotes
```

The SDK will automatically load this file when initialized.

/// danger | Important
Do not commit this `.env` file to version control (e.g., Git)!
///

**Option 2:** Using an environment variable

```bash
export SDS_SECRET_TOKEN=your-secret-token
```

Environment variables take precedence over `.env` files.

**Option 3:** Passing directly in code

```python
from spectrumx.client import Client

sds = Client(
    host="sds.crc.nd.edu",
    env_config={"SDS_SECRET_TOKEN": "my-custom-token"}
)
```

### How to generate a secret token?

First, your account needs to be approved. Reach out to support or to an admin directly
on Slack if you can't generate a token following these steps:

1. In [`sds.crc.nd.edu`](https://sds.crc.nd.edu/), log into your account.
2. Navigate to ["API Keys"](https://sds.crc.nd.edu/users/view-api-key/).
3. Click on "Generate API Key".
4. Optionally give it a name, description, and set an expiration date.
5. Copy the generated token and store it securely. You won't be able to see it again.

Note all files uploaded using this token will be associated with your SDS account.

/// danger | Important

Do not share your secret token publicly or commit it to version control.
Treat it like a password.
///

### Why can't I generate an API key?

Your account may not yet be approved to access the SDS. Please contact support or an
admin directly on Slack if you can't generate a token following the steps above.

### Why is my data not uploaded? | What is dry-run mode?

By default, the SDK operates in dry-run mode, which means **no changes are made to the**
**SDS or local filesystem**. This is useful for testing your code before actually
uploading or downloading files.

To enable actual file operations:

```python
sds = Client(host="sds.crc.nd.edu")
sds.dry_run = False  # Enable actual operations
sds.authenticate()
sds.upload(local_path="my_files", sds_path="remote_path")
```

### Where can I find code examples?

Check out:

+ **[SpectrumX SDK
    Walkthrough](https://github.com/crcresearch/spx-events/blob/main/demos/data_system/walkthrough.ipynb)**:
    An example Jupyter notebook
+ **[More
    Examples](https://github.com/spectrumx/sds-code/blob/master/sdk/tests/e2e_examples/check_build_acceptance.py)**:
    A live, up-to-date Python script showing basic operations

## File Operations

![File Transfer | xkcd 949](https://imgs.xkcd.com/comics/file_transfer.png)

### How do I upload files to the SDS?

```python
from pathlib import Path
from spectrumx.client import Client

sds = Client(host="sds.crc.nd.edu")
sds.authenticate()

# Upload a single file or entire directory
upload_results = sds.upload(
    local_path=Path("my_files"),
    sds_path="remote_directory",
    verbose=True  # Shows progress bar
)
```

The `upload()` method returns a list of `Result` objects. Each result contains either
the uploaded `File` object or an exception if the upload failed.

### How do I download files from the SDS?

```python
from pathlib import Path
from spectrumx.client import Client

sds = Client(host="sds.crc.nd.edu")
sds.authenticate()

# Download files to a local directory
sds.download(
    from_sds_path="remote_directory",
    to_local_path=Path("local_downloads"),
    overwrite=False,  # Don't overwrite existing local files
    verbose=True  # Shows progress bar
)
```

### Can I resume interrupted uploads or downloads?

Yes! The SDK is designed to be fault-tolerant, so this happens automatically when an
upload or download operation on multiple files is interrupted. All you need to do is
design your script to call the upload or download methods again on failure to
automatically handle transient failures.

However, the specific upload or download of a file that was interrupted will be started
from the beginning. So it's better to operate on smaller files (e.g. < 1GB) to minimize
the impact of interruptions.

/// tip | If an operation is interrupted:

+ **Uploads**: `sds.upload()` will restart a partial file transfer from where it left
    off, but won't re-upload files that are already complete. It might take a while to
    check with the server it has all the files, but this check is much faster than
    re-uploading everything.
+ **Downloads**: Similarly, the download process can resume from interruption points.

///

### How do I handle errors during file operations?

The SDK provides specific exception types for different error scenarios:

```python
from spectrumx.client import Client
from spectrumx.errors import AuthError, NetworkError, Result, SDSError, ServiceError

sds = Client(host="sds.crc.nd.edu")

try:
    sds.authenticate()
except NetworkError as err:
    print(f"Failed to connect to the SDS: {err}")
    # Check your host parameter and network connection
except AuthError as err:
    print(f"Failed to authenticate: {err}")
    # Check your authentication token

try:
    upload_results = sds.upload(local_path="my_files", sds_path="remote")

    # Check individual file results
    success_results = [r for r in upload_results if r]  # Successful uploads
    failed_results = [r for r in upload_results if not r]  # Failed uploads

    # Calling a failed result will raise its exception
    for result in failed_results:
        result()  # Raises the exception it holds
except (NetworkError, ServiceError) as err:
    # Transient errors - consider retry logic
    print(f"Temporary failure: {err}")
except SDSError as err:
    # Other SDS-specific errors
    print(f"SDS error: {err}")
```

See the [Getting Started](getting-started.md) guide for a complete retry example.

## Asset Types and Organization

### What is a File | Directory | Capture | Dataset | Experiment?

See the [Terminology](terminology.md) guide for detailed definitions of each asset.

### What are Draft and Final Datasets?

A **Draft Dataset** is a work-in-progress collection of files and metadata that is not
yet finalized. It allows users to organize and collaborate on their data before it is
considered "published". Draft Datasets can be modified, and files can be added or
removed as needed. A dataset may remain in draft status indefinitely.

A **Final Dataset**, on the other hand, is a completed collection of files and metadata
that has -- ideally -- been reviewed and approved for publication or sharing. Making a
Datasets final means it becomes locked for edits and it's intended for distribution to a
wider audience. In the future we might have mechanisms to release a new version of a
final dataset; and to retract a final dataset if needed, signalling to other
collaborators that the dataset is no longer valid.

### Can we share a draft dataset?

Yes, draft datasets can be shared with other users for collaboration. A common use case
is when multiple team members are working together to compile and refine data before
finalizing it for publication or sharing. Sharing a draft dataset allows collaborators
to contribute, review, and provide feedback on the data before it is locked as a final
dataset.

### What's the difference between a Directory and a Dataset?

+ A **Directory** is like a folder in your local machine. Except that it is a completely
    virtual concept on SDS: files are stored in a flat structure on the server, and
    directories are just a way for clients to organize files logically and make it
    easier to browse them. You can't share a directory in SDS.
+ A **Dataset** can hold files (named artifact files), captures, and can hold metadata
    about its creation date, authors, DOI, and other relevant information. Datasets are
    ideal for exporting collections of files and captures for sharing with
    collaborators and for publication. A dataset may hold data from multiple users too.

### What is the difference between a Capture and a Dataset?

+ A **Capture** is a collection of files that represent a single data acquisition event.
    A capture has a type (e.g. Digital-RF or RadioHound), and it groups files
    that are likely to be read or analyzed together. The exact files that become part
    of a capture are determined automatically, so if you need to add files with
    arbitrary contents, consider using a Dataset instead.
+ **Datasets** on the other hand, can hold any files uploaded into SDS that you want to
    group together for sharing, publication, or just for organization purposes. A
    dataset can contain files from multiple captures, directories, or standalone files,
    a.k.a. artifact files.

## Data Sharing and Collaboration

### How can I share files with other users?

You can share files in SDS by creating Datasets. Datasets are designed to group files
together for sharing and publication. Once you create a Dataset, you can share it with
other users by providing them with the Dataset's unique identifier or DOI (if assigned).

### Can I add files to a dataset that was shared with me?

Yes, you can add files to a dataset that was shared with you, but you must have the
appropriate permissions to do so. This typically means you need to be granted explicit
write permissions by the owner of the Dataset.

+ [Can we share a draft dataset?](#can-we-share-a-draft-dataset)

## Concurrency and Data Safety

### Can multiple clients write to the same location simultaneously?

**No, this is not recommended.**

However, note the "same location" caveat. That is to avoid race conditions: when
multiple clients try to upload a file with the same path and name but different
contents, it's unclear which one should be kept. So you might not keep the data you
expect when reading it back.

If you can guarantee the files being uploaded by these scripts don't have overlapping
names and paths, then it should be fine.

/// tip | To avoid this:

1. **Restructure your architecture** to forward writes to a single centralized client
2. **Use different locations or application stages** for writes from different clients
3. **Implement a custom locking mechanism** for your specific use case
///

### Is it safe to have multiple clients reading from the same location?

Yes! One writer and multiple readers are generally safe. You can have multiple clients
downloading or reading from the same SDS locations without issues.

### Why is the SDK stateless?

A stateless design allows multiple clients to interact with the SDS Gateway
simultaneously without the complexity of session management. However, this means each
request must contain all information needed to complete it, and the SDK cannot detect or
prevent concurrent writes to the same location.

### What protections help prevent accidental deletions?

SDS layers several safeguards to keep assets from being removed unintentionally:

+ Sharing defaults to **Viewer** access. Granting write permissions always requires an explicit choice.
+ Files that belong to captures or datasets cannot be deleted until they are unlinked from that grouping. Captures linked into datasets are equally protected while that relationship exists.
+ **Final** datasets are read-only, even for their owners. This is the recommended state for broader distribution once contents are stable. See [What are Draft and Final Datasets?](#what-are-draft-and-final-datasets) for details.
+ All SDS assets use soft deletion. Administrators can restore items for a short window after removal if contacted promptly. Reach out to support if needed.
+ When working in the SDK, keep shared-asset listings distinct from your own to reduce the chance of edits in the wrong context.

## Troubleshooting

### I'm getting an `AuthError` when trying to authenticate. What should I check?

1. **Verify your token**: Make sure your `SDS_SECRET_TOKEN` is correct and hasn't
    expired
2. **Check token location**: Ensure the `.env` file or environment variable is being
    read correctly
3. **Verify the host**: Confirm you're connecting to the correct SDS Gateway host
4. **Network access**: Ensure your machine can reach the SDS Gateway

### I'm getting a `NetworkError`. What does this mean?

A `NetworkError` indicates a connection issue between your client and the SDS Gateway.
Check:

1. **Network connectivity**: Verify your internet connection
2. **Host address**: Confirm the `host` parameter is correct and accessible
3. **Gateway status**: If you're hosting the SDS Gateway locally, ensure it's running
    and accessible
4. **Firewall/proxy**: Check if any firewall or proxy is blocking the connection

### I'm getting a `ServiceError`. What should I do?

Wait.

Unless you are managing the Gateway instance yourself, that's probably on us. Reach out
to support if the issue persists for more than an hour during business hours (ET).

### My upload/download is very slow or seems stalled. What can I do?

+ **Check the progress bar**: The `verbose=True` parameter shows a progress bar during
    operations
+ **Network issues**: Slow speeds may indicate network congestion. Consider retrying
    later
+ **File size**: Large files take longer to transfer
+ **Multipart support**: The SDK supports multipart uploads for better performance with
    large files
+ **Concurrency**: The SDK handles multiple network requests concurrently for improved
    throughput

### I'm seeing an `Internal Server Error` from the Gateway. What now?

This indicates an unexpected error on the server side. If you are not the Gateway
administrator, please contact support with details of the operation you were attempting.

If this is happening during capture creation, it may be due to an issue with the data or
the capture configuration. Try different capture creation parameters. We are working to
forward data validation and Digital-RF errors to clients in future SDK and Gateway
releases.

## Advanced Topics

### What should I know about concurrent access?

See the [Concurrent Access](advanced/concurrent-access.md) guide for detailed
information about:

+ Race conditions and how to avoid them
+ Safe patterns for multiple clients (one writer + multiple readers)
+ Strategies for handling concurrent writes if needed

### How do I contribute to the SDK?

Refer to the [Contributing Guide](dev-notes/contributing.md) for information on how to
contribute to the SpectrumX SDK development.

It can be in any form, even to improve this FAQ with a question we missed.

### Does the SDK have a higher verbosity mode for debugging?

I'm glad you asked!

```python
import spectrumx

spectrumx.enable_logging()
```

Some operations also take a `verbose=True` parameter -- check their definitions and
docstrings.

### Is there a CLI mode for a quick upload/download?

Unfortunately not. But let us know if you want this feature!

### Are you planning to support other programming languages?

Not in the foreseeable future.

### What are some best practices for using the SDK?

1. **Keep your SDK up to date**: Regularly check for updates to the SDK and incorporate
    them into your project to benefit from the latest features and bug fixes.
2. **Implement error handling**: Gracefully handle errors and exceptions in your
    application to improve user experience and facilitate troubleshooting.
3. **Use loggers instead of print**: They have timestamps that might be helpful when
   reading the output after long runs.
4. **Use environment variables**: Store sensitive information, such as API keys and
    tokens, in environment variables instead of hardcoding them in your source code.

## Federation

### What is Federation in SDS?

Federation in the SpectrumX Data System (SDS) refers to the capability of connecting
multiple SDS instances or gateways to allow seamless data sharing and collaboration
across different organizations or geographical locations. This enables users to access
and manage data stored in different SDS deployments as if they were part of a single
system, facilitating broader data accessibility and collaboration.

### What is the current status of Federation support?

Federation support is currently under development and is not available as of late 2025.

It will be rolled out to production in 2026 and it will be further detailed in SDS
Gateway documentation as more architecture decisions are made.
