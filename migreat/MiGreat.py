import argparse
from glob import glob
import importlib
import logging
import os
from pydantic import BaseModel
import re
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
import sys
import time
import yaml

# Log config
logger = logging.getLogger('MiGreat')
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(levelname)s: %(asctime)s - %(message)s"))
logger.addHandler(ch)


class Config(BaseModel):
    """
        Config file schema
    """
    hostname: str
    port: int = 5432
    database: str
    priv_db_username: str
    priv_db_password: str
    service_db_username: str
    service_db_password: str
    service_schema: str
    legacy_sqlalchemy: bool = False
    max_conn_retries: int = 10
    conn_retry_interval: int = 5
    migration_table: str = "migrate_version"


class MiGreat:
    """
        Encapsulates MiGreat functionality.
    """

    OPER_CREATE = "create"
    OPER_INIT = "init"
    OPER_UPGRADE = "upgrade"
    """ CLI operations """

    SCRIPTS_DIR = os.path.abspath(
        os.path.join(
            os.curdir,
            "versions"
        )
    )
    """ Migration scripts directory """

    CONFIG_FILE = os.path.abspath(
        os.path.join(
            os.curdir,
            "MiGreat.yaml"
        )
    )
    """ MiGreat configuration file """

    TEMPLATES_DIR = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "templates"
        )
    )
    """ Templates directory """

    @staticmethod
    def cli():
        """
            Runs the migration batch.
        """
        parser = argparse.ArgumentParser(description="MiGreat CLI")
        parser.add_argument(
            "oper",
            type=str,
            choices=(
                MiGreat.OPER_CREATE,
                MiGreat.OPER_INIT,
                MiGreat.OPER_UPGRADE,
            ),
        )
        parser.add_argument(
            "--version",
            type=int,
            default=None,
            help="Version to downgrade to if downgrading",
        )

        args = parser.parse_args()
        if args.oper == MiGreat.OPER_INIT:
            logger.info("Initializing MiGreat")
            os.mkdir(MiGreat.SCRIPTS_DIR)
            with open(MiGreat.TEMPLATES_DIR, "rt") as config_file:
                config_template = config_file.read()
            with open(MiGreat.CONFIG_FILE, "wt") as config_file:
                config_file.write(config_template)
            logger.info("MiGreat initialized at ./")
            logger.info("Please adjust defaults in ./MiGreat.yaml")

        elif args.oper == MiGreat.OPER_CREATE:
            mg = MiGreat.from_yaml()
            mg.create()

        else:
            assert args.oper == MiGreat.OPER_UPGRADE
            mg = MiGreat.from_yaml()
            mg.upgrade()

    @staticmethod
    def from_yaml() -> "MiGreat":
        """
            Initializes and returns a MiGreat instance from the yaml configuration file.
        """
        if not os.path.exists(MiGreat.CONFIG_FILE):
            logger.error("Couldn't find MiGreat config file.  Try initializing the space first.")
            sys.exit(1)

        if not os.path.exists(MiGreat.SCRIPTS_DIR):
            logger.error("Couldn't find MiGreat scripts directory.  Try initializing the space first.")
            sys.exit(1)

        with open(MiGreat.CONFIG_FILE) as config_file:
            the_yaml = yaml.safe_load(config_file)
            annotations = Config.__annotations__
            for key, value in the_yaml.items():
                match = MiGreat.__VAR_SUBST_MATCHER.match(str(value))
                if match is not None:
                    var_name = match.groups()[0]
                    var = os.environ.get(var_name, "")
                    if key in annotations:
                        # Convert to the proper type since all environment variables are strings
                        the_yaml[key] = annotations[key](var)

            config = Config(**the_yaml)

        return MiGreat(config)

    def __init__(self, config: Config):
        """
            Initializes an instance of MiGreat.
        """
        self.__config = config

    @property
    def config(self) -> Config:
        """
            Returns the configuration object.
        """
        return self.__config

    def create(self):
        """
            Creates a new migration script from the template.
        """
        highest_version, _ = self.__validate_migrator_scripts()
        next_version = highest_version + 1
        migrator = f"{str(next_version).zfill(4)}_unnamed_migrator.py"
        with open(os.path.join(MiGreat.TEMPLATES_DIR, "migrator.tmpl"), "rt") as m_tmpl:
            template = m_tmpl.read()
        with open(os.path.join(MiGreat.SCRIPTS_DIR, migrator), "wt") as m_script:
            m_script.write(template)
        logger.info(f"Wrote new migrator {migrator}")

    def upgrade(self):
        """
            Runs migrators in order, starting with the next version.  Each migrator is
            independently transacted.  Migrations are always executed by the service user.
        """
        self.__check_and_apply_migration_controls()
        highest_version, scripts = self.__validate_migrator_scripts()
        config = self.config

        priv_engine = self.__connect(
            config.hostname,
            config.port,
            config.database,
            config.priv_db_username,
            config.priv_db_password,
            config.conn_retry_interval,
            config.max_conn_retries,
            config.legacy_sqlalchemy,
        )

        service_engine = self.__connect(
            config.hostname,
            config.port,
            config.database,
            config.service_db_username,
            config.service_db_password,
            config.conn_retry_interval,
            config.max_conn_retries,
            config.legacy_sqlalchemy,
        )
        with service_engine.connect() as conn:
            query = f"SELECT version FROM \"{config.service_schema}\".\"{config.migration_table}\""
            if not config.legacy_sqlalchemy:
                query = text(query)

            result = conn.execute(query)
            row = result.fetchone()
            curr_ver = row[0]
            if curr_ver == highest_version:
                logger.info("Migrations are already up to date")
                sys.exit(0)

            if curr_ver > highest_version:
                logger.error("Migration version in database exceeds that of the migration scripts")
                sys.exit(1)

        next_version = curr_ver + 1
        for script in scripts[curr_ver:]:
            spec = importlib.util.spec_from_file_location(
                script[:-3],
                os.path.join(
                    MiGreat.SCRIPTS_DIR,
                    script,
                ),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, 'upgrade'):
                logger.error(f"Migrator {script} does not have an upgrade method")
                sys.exit(1)

            if not hasattr(module, 'downgrade'):
                logger.error(f"Migrator {script} does not have a downgrade method")
                sys.exit(1)

            if hasattr(module, 'CONFIG_OPTIONS'):
                CONFIG_OPTIONS = module.CONFIG_OPTIONS
            else:
                CONFIG_OPTIONS = {}

            transact = CONFIG_OPTIONS.get('transact', True)
            run_as_priv = CONFIG_OPTIONS.get('run_as_priv', False)

            engine = priv_engine if run_as_priv else service_engine
            session = Session(engine, future=not config.legacy_sqlalchemy)

            logger.info(f"Migrating {next_version - 1} to {next_version}")
            try:
                if transact:
                    with session.begin():
                        module.upgrade(session)
                        self.__update_version(session, next_version)
                else:
                    module.upgrade(session)
                    with session.begin():
                        self.__update_version(session, next_version)
            except:
                logger.error("Migration failed", exc_info=1)
                sys.exit(1)

            next_version += 1

    def __update_version(self, conn, next_version: int):
        """
            Updates the schema version.
        """
        config = self.config
        # This is fully qualified in case the privileged user has been selected to perform
        # the operation.
        query = f"""
            UPDATE \"{config.service_schema}\".\"{config.migration_table}\"
            SET version = :next_version
        """
        if not self.config.legacy_sqlalchemy:
            query = text(query)

        conn.execute(
            query, {
                "next_version": next_version
            }
        )

    def __validate_migrator_scripts(self) -> int:
        """
            Validates and returns information about the current migrator scripts.
        """
        highest_version = 0
        scripts_by_version = {}
        scripts = []
        existing_scripts = glob(os.path.join(MiGreat.SCRIPTS_DIR, "*.py"))
        for full_path in sorted(existing_scripts):
            _, filename = os.path.split(full_path)
            match = MiGreat.__SCRIPT_MATCHER.match(filename)
            if match is not None:
                ver = int(match.groups()[0])
                if ver in scripts_by_version:
                    logger.error(f"Multiple migrators share version number {ver}")
                    sys.exit(1)
                scripts_by_version[ver] = filename
                highest_version = max(highest_version, ver)

        # Make sure there are no holes in the scripts:
        if highest_version:
            for ver in range(1, highest_version + 1):
                if ver not in scripts_by_version:
                    logger.error(f"Migrator {ver} is missing from the series")
                    sys.exit(1)
                scripts.append(scripts_by_version[ver])

        return highest_version, scripts

    def __connect(
        self,
        hostname,
        port,
        database,
        username,
        password,
        retry_interval,
        max_retries,
        legacy_sqlalchemy,
    ):
        """
            Returns a connection to the target databse.
        """
        engine = create_engine(
            f"postgresql://{username}:{password}@{hostname}:{port}/{database}",
            future=not legacy_sqlalchemy,
        )

        # Attempt to connect, and retry on failure
        for _ in range(max_retries+1):
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                    break
            except OperationalError:
                logger.info(f"Connection failed, waiting {retry_interval}s before retrying")
                time.sleep(retry_interval)
        else:
            logger.error(f"Unable to establish connection after {max_retries+1} attempts")
            sys.exit(1)

        return engine

    def __check_and_apply_migration_controls(self):
        """
            Checks to determine if MiGreat's migration controls have been applied to the target
            database, and applies them if they have not already been applied.
        """
        engine = self.__connect(
            self.config.hostname,
            self.config.port,
            self.config.database,
            self.config.priv_db_username,
            self.config.priv_db_password,
            self.config.conn_retry_interval,
            self.config.max_conn_retries,
            False,
        )
        config = self.config
        with engine.begin() as conn:
            # Check if the service user exists
            result = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname=:username"),
                {
                    "username": config.service_db_username,
                }
            )
            row = result.fetchone()
            if row is None:
                logger.info(f'Creating user "{config.service_db_username}"')
                conn.execute(
                    text(
                        f"CREATE USER \"{config.service_db_username}\" WITH ENCRYPTED PASSWORD :password"
                    ), {
                        "password": config.service_db_password,
                    }
                )

            # Check if the service schema exists
            result = conn.execute(
                text("""
                    SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema
                """), {
                    "schema": config.service_schema
                }
            )
            row = result.fetchone()
            if row is None:
                logger.info(f'Creating schema "{config.service_schema}"')
                conn.execute(text(f"CREATE SCHEMA \"{config.service_schema}\""))

                conn.execute(text(f"""
                    GRANT ALL PRIVILEGES ON SCHEMA \"{config.service_schema}\"
                    TO \"{config.service_db_username}\"
                """))

                conn.execute(text(f"""
                    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA \"{config.service_schema}\"
                    TO \"{config.service_db_username}\"
                """))

                conn.execute(text(f"""
                    ALTER ROLE \"{config.service_db_username}\" SET search_path
                    TO \"{config.service_schema}\", PUBLIC
                """))

            # Check if migration tracking table exists
            result = conn.execute(text("""
                SELECT FROM pg_catalog.pg_class cat
                JOIN pg_catalog.pg_namespace ns ON ns.oid = cat.relnamespace
                WHERE
                    ns.nspname = :service_schema AND
                    cat.relname = :migration_table AND
                    cat.relkind = 'r'
            """), {
                "service_schema": config.service_schema,
                "migration_table": config.migration_table,
            })
            row = result.fetchone()
            if row is None:
                conn.execute(text(f"""
                    CREATE TABLE \"{config.service_schema}\".\"{config.migration_table}\" (
                        repository_id TEXT NOT NULL,
                        repository_path TEXT NOT NULL,
                        version INT NOT NULL
                    );
                """))

                conn.execute(text(f"""
                    INSERT INTO \"{config.service_schema}\".\"{config.migration_table}\" (
                        repository_id,
                        repository_path,
                        version
                    ) VALUES (
                        :service_schema,
                        :migrator_dir,
                        :version
                    )
                """),  {
                    "service_schema": config.service_schema,
                    "migrator_dir": MiGreat.SCRIPTS_DIR,
                    "version": 0,
                })

                conn.execute(text(f"""
                    GRANT ALL PRIVILEGES ON TABLE \"{config.service_schema}\".\"{config.migration_table}\"
                    TO \"{config.service_db_username}\"
                """))

    __SCRIPT_MATCHER = re.compile("^(\d+)_.+.py$")
    """ Regular expression to match active migrator scripts """

    __VAR_SUBST_MATCHER = re.compile("^\$\{(.+)\}$")
    """ Regular expression to perform environment variable injection """
