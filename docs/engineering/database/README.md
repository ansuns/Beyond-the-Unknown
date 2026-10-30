# Database engineering files

`server/schema/0001_initial_schema.sql` is the executable source used by Alembic 0001. The same-named SQL file in this directory is a review/documentation mirror.

When changing the initial snapshot, update both copies and pass the CI `cmp` check. Never rewrite a migration already shared with an environment; append a new migration instead.
