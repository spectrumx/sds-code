# Concurrent Access

The SDS client-server interaction is stateless, meaning that each request contains all
the information needed to complete that request. One positive outcome is that it allows
multiple clients to interact with the SDS Gateway at the same time. However, this opens
up the possibility of having multiple clients writing to the same locations
simultaneously, causing loss of data by overruling each other's writes (race condition).

> For example, if two clients are uploading files with the same directory, file names,
> and at the same time, only the last file successfully uploaded (from the Gateway's
> perspective) is guaranteed to be kept, which might not be aligned with the user's
> expectations.

To avoid potential race conditions, it is not recommended to have multiple clients
writing to the same locations simultaneously. Neither the SDK nor the Gateway currently
take any measure to detect this, in part, because any measure towards it would either be
incomplete, or it would make our APIs stateful and significantly increase code
complexity.

If this is needed, SDK users have a few options:

1. Restructure their architecture to forward writes to a single centralized client
   responsible for them.
2. Restructure the code by writing to different locations and/or at different
    application stages. The latter assumes all conflicting clients are part of the same
    application.
3. Implement a custom locking mechanism for writes to serve their specific use case.

One writer (an SDK client that creates, updates, and/or deletes contents) and multiple
readers are generally safe.
