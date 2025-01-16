# Features

## Asset types

The SDK provides classes for the following asset types:

| Asset Type   | Description                                                                                                                                                                     |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `File`       | Represents a file that was uploaded to SDS. It may be one of a variety of formats allowed. It is the smallest addressable unit in SDS.                                          |
| `Directory`  | A directory is a unique attribute of a file in the form of a path and does not match how files are stored on the server. It is merely used to arrange files on the client side. |
| `Capture`    | Represents an RF capture that is indexed and searchable. It follows some specification like Digital-RF or RadioHound and may consist in a group of files + domain metadata.     |
| `Dataset`    | Logical grouping of files in the SDS with metadata and a unique identifier. Ideal for exporting collections of files or captures.                                               |
| `Experiment` | Logical grouping of datasets and/or captures plus other artifacts that stem from data processing on a dataset, like derived data, reports, scripts, etc.                        |
