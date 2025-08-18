# Gateway Development Notes

+ [Handling migration conflicts](#handling-migration-conflicts)
    + [Rebasing the migration](#rebasing-the-migration)
    + [Workflow](#workflow)

## Handling migration conflicts

At times, you might need to merge two branches with conflicting changes to
`max_migrations.txt`. This file is created by
[`django-linear-migrations`](https://github.com/adamchainz/django-linear-migrations),
which we use to help manage and resolve migration conflicts.

This installed app will nudge you to rebase the migrations, linearizing them in the
process. This is done to prevent problems with running migrations in different order and
complicated rollbacks.

### Rebasing the migration

```bash
# docker exec -it sds-gateway-<local/prod>-app python manage.py rebase_migration <app_name>
docker exec -it sds-gateway-local-app python manage.py rebase_migration users
docker exec -it sds-gateway-local-app python manage.py rebase_migration api_methods
```

Then, manually check the altered files look right and continue the rebase.

The command uses the conflict information in the `max_migration.txt` file to determine
which migration to rebase. It automatically detects whether a Git merge or rebase
operation is in progress, assuming rebase if a Git repository cannot be found. The
command then:

1. Renames the migration
2. Edits it to depend on the new migration from your main branch
3. Updates `max_migration.txt`.

> [!NOTE]
> Rebasing the migration might not always be the correct thing to do. If the
> migrations in your default and feature branches have both affected the same models,
> rebasing the migration to the end may not make sense. However, such parallel changes
> would normally cause conflicts in your model files or other parts of the source code
> as well.

### Workflow

Below is a workflow example with `users` as the app with migration conflicts between
the default branch and the feature branch.

```bash
# bring the default branch up-to-date:
git switch master
git pull

# switch to the feature branch that has a new migration:
git switch feat-branch
docker exec -it sds-gateway-local-app python manage.py migrate users

# rebase branches and migrations
git rebase main
# if no conflict, you're set; otherwise, you might see a conflict on max_migration.txt:
# CONFLICT (content): Merge conflict in users/migrations/max_migration.txt
# ...

# so on conflict, rebase the migrations too:
docker exec -it sds-gateway-local-app python manage.py rebase_migration users

# then CHECK THE FILES, making manual changes if needed
git diff users/migrations/

# if ok, add them, and continue the migration
git add users/migrations/
git rebase --continue

# finally, migrate your local env to continue development
docker exec -it sds-gateway-local-app python manage.py migrate users
```
