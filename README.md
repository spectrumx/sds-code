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
