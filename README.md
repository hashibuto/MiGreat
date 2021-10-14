# MiGreat
A schema isolated Postgres migrator for shared database micro services

## Philosophy
Several micro services may share the same database backend, but it's important to provide namespace isolation between said services.  This is where schema level isolation is effective.  The schema provides a namespace in which a given service can create tables, indices, types, etc.  The default namespace in postgres is the `public` namespace.  When writing queries, it's convenient to not have to qualify every item by namespace.

**MiGreat** provides the convenience of preparing schema isolation, bound to a non-privileged service account within the database.  This means that migrations carried out by MiGreat for a particular service, do not require queries to be schema-qualified, as they are executed by the service user to which the schema is implicitly bound, via a combination of schema privileges, and the schema search order.  Additionally, the micro service is locked by access grant to its own schema and cannot intentionally or otherwise clobber data that does not belong to it.

## Installation
```
pip install MiGreat-cli
```

## How to migrate (and be great)
Run the following:
```
migreat upgrade
```

This configures an unconfigured database, and executes unexecuted migrations.  This should run standalone, outside of your application.  In a kubernetes environment, you may have a dedicated pod spin up to execute the script as part of a rollout hook.  In a compose, or local environment, you may want to execute it before your service starts.  What you don't want to do however, is tighly couple migreat's execution to that of your microservice process.  In an environment where your service runs in multiple processes or even on multiple hardware/virtual nodes, tight coupling will have undesired consequences (think everybody transacting on the same migration script at once).

**TL;DR:** Keep the migration execution and the application execution separate!

## Usage
From a location of your choosing (example: the root of your microservice's directory structure), perform the basic intialization.  **NOTE**, initialization does not communication with the databse, it merely provides the initial configuration.  All database communication happens at migration time.

```
migreat init
```
This creates a configuration file `MiGreat.yaml`, which stores database connection information, as well as some basic operational parameters.

Basic example:
```
hostname: localhost
port: 5432
database: my_db

priv_db_username: postgres
priv_db_password: ${PRIVELEGED_DB_PASSWORD}

service_db_username: checkout_svc
service_db_password: ${SERVICE_DB_PASSWORD}

service_schema: checkout
```

This example illustrates a minimal configuration, in which a service user called `checkout_svc`, will be bound to a schema called `checkout`.  The privileged user id and password are used to perform the initial configuration, but all subsequent operations are performed by the service user unless otherwise explicitly specified.  The micro service which then consumes the database need only be aware of the `checkout_svc` user.

You'll notice as well that the passwords have some string interpolation syntax.  While it's entirely possibly to pass strings directly into the config file, it is recommended to use this string interpolation syntax for sensitive data such as passwords.  MiGreat will then insert values from the process environment.

In addition to the config file, a directory called `versions` is created.  This will initially be empty, but is where migration scripts are stored.

### Creating a first migration script

From the same directory where `migreat init` was invoked in the previous step, invoke the following command:

```
migreat create
```
This will create a new migration script in the form of `XXXX_unnamed_migrator.py`, where `XXXX` is the next version in the sequence of migrators (or `0001` if this is the first.)  This operation does not communicate with the database, it only concerns itself with what scripts already exist.

Feel free to copy and paste migration scripts instead of executing `migreat create`.  This is merely a convenience command which exposes a fresh migration script template.

### The migration script template
```
CONFIG_OPTIONS = {
    "transact": True,           # Transact this migrator automatically
    "run_as_priv": False,       # Run as the privileged database user (instead of the service user)
}
"""
    These are all the available options on a per-migrator basis.  The options present have all
    been defaulted.  You don't need to include this dict, though if you do, the options you specify
    will be overlayed onto the defaults.
"""

def upgrade(conn):
    """
        Upgrades the database to the current defined migration version.
    """

def downgrade(conn):
    """
        *** DOWNGRADE SQL GOES HERE ***
    """
```

The template should be fairly self explanatory, but we'll re-iterate here.  `CONFIG_OPTIONS` shown are the defaults, your migrator script does not need to include that variable unless your intent is to override a default.  Overrides are mapped overtop the defaults.  Not all options have to be specified when overriding, only the overridden ones.

The `upgrade` method uses an SQLAlchemy session for the `conn` argument, and the `downgrade` method does nothing but facilitate a convenient spot to specify downgrade SQL.  Do what you like with this method.

### Advanced options
There are a few advanced options exposed in the `MiGreat.yaml` config.  They are as follows (defaults shown):

```
# Legacy sqlalchemy style (pre v2)
legacy_sqlalchemy: false

# Max connection retries
max_conn_retries: 10

# Connection retry interval (seconds)
conn_retry_interval: 5

# Migration table name
migration_table: migrate_version
```

`legacy_sqlalchemy` assumes the pre v2 way of writing SQL queries (meaning, largely, they don't need to be wrapped in `text()`).  The other options should be fairly self explanatory.

## FAQ

Q) Why called migreat?

A) Because this functionality is great... why else :)

Q) What if I absolutely need to do something outside the scope of the schema, in a given migrator

A) Honestly, I'm not sure how this plays from a philosophical standpoint, but the ability exists for use cases I haven't conceived yet.  This is what the `run_as_priv` option is for in the migrator's `CONFIG_OPTIONS`.  Maybe a service decides that it needs to include a Postgres extension, after the fact... Maybe some cross-schema fix needs to happen.  I don't know your use case, but it sounds dangerous.
