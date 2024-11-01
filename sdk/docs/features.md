# Features

## Asset types

The SDK provides classes for the following asset types:

| Asset Type   | Description                                                                                                                                                                       |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `File`       | Represents a file that was uploaded to SDS. It may be one of a variety of formats allowed. It is the smallest addressable unit in SDS.                                            |
| `Directory`  | A directory is a unique attribute of a file in the form of a path and does not match how files are stored on the server. It is merely used to arrange files on the client side.\* |
| `Capture`    | Special type of file that refers to an RF capture and is indexed and searchable. Uses the same ID as the file it represents.                                                      |
| `Dataset`    | Logical grouping of files in the SDS with metadata and a unique identifier. Ideal for sharing collections of files.                                                               |
| `Experiment` | Logical grouping of zero or more datasets, captures, and files. It is a logical grouping of datasets and captures.                                                                |
