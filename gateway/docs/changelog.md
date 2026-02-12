# SpectrumX Gateway Changelog

> This document is meant to communicate breaking changes for administrator and operators
> of SDS Gateway deployments, and its contributors.
>
> It focuses on back-end changes that impact data integrity, and does not usually
> include new features that do not require special attention from operators when
> upgrading.
>
> Generally, an SDS Gateway upgrade is just a few steps:
>
> 1. Run a backup.
>
>       Run `just snapshot` to create your daily snapshot of database, secrets, and
>       uncommitted changes (if any). Optionally transfer the snapshot to a safe
>       location.
>
> 2. Pull the changes.
>
>       Make sure you're on the `stable` branch and pull the changes:
>
>       `git pull --autostash --ff-only origin stable`
>
>       Explaining the flags:
>
>       - `--autostash` will automatically stash uncommitted changes you might have
>           locally before the pull and re-apply them after the pull is complete. This
>           allows you to keep your local changes without having to manage the stash
>           yourself.
>       - `--ff-only` will refuse to merge if the merge can't be resolved as a
>           fast-forward. Unless you have local commits that are unique to your
>           deployment, this is usually the case for production upgrades. If you do have
>           local commits, you can use `git pull --autostash --rebase` to apply them on
>           top of the latest changes (but be aware that this can lead to merge
>           conflicts).
>
> 3. Check special instructions for this upgrade.
>
>       Follow instructions in this changelog for any manual steps required for the
>       upgrade. This may include running management commands.
>
> 4. Restart the services.
>
>       Run `just redeploy`
>
>       The redeploy subcommand will minimize downtime by building the images before
>       stopping the services currently running.
>
>       If you wish to build the images now and deploy later (e.g. when traffic is low),
>       run `just build` to verify it builds, and then `just redeploy` when ready.
>       `redeploy` will then use the Docker images in the cache, if they are still
>       valid. You may monitor the logs for warnings or errors as messages start coming;
>       but generally, this is expected to be a smooth process.
>
> **Releases and the `stable` branch:** note the gateway does not currently issue point
> releases. The tip of the `stable` branch is the only source meant to be used for
> production deployments. Updates are fast-forwarded to that branch when ready, so
> `stable` has always a linear history that makes it easier to traverse if needed. Not
> all commits in `origin/stable` are buildable, but its `HEAD` (the latest commit at any
> time) is expected to be. That means you should be able to pull the latest changes from
> `origin/stable` and build the project without issues. Just check these release notes
> for any manual steps needed to complete the upgrade process.
>

---

> [!NOTE]
>
> If you have issues during the upgrade process, please reach out to the developers
> before attempting a rollback or a fix of your own. A rollback may not be possible, or
> may cause data integrity issues that will demand a custom fix.

## 2026-01-08

- Fixes:
    - [**Added M2M relationships for assets to
        datasets**](https://github.com/spectrumx/sds-code/pull/226): Currently the
        foreign key (FK) relationships only allow assets to be connected to a single
        dataset. This PR expands the schema (with future contraction planned) to correct
        the schema issues.
        - Requires a data migration for existing datasets (and captures) from the FK
            field to M2M field. Run management command `migrate_fk_to_m2m` to transfer
            foreign key model relationship to many-to-many field (only adds, does NOT
            nullify FK).
        - This is meant to be run on systems with data under the current schema that
            require migrations to new schema.
