from __future__ import annotations

import importlib
import os
import pkgutil
from logging.config import fileConfig

from alembic import context
from interview_evidence.shared.database import metadata
from interview_evidence.shared import persistence as shared_persistence
from sqlalchemy import MetaData, engine_from_config, pool

del shared_persistence

DOMAIN_PACKAGES = (
    "interview_evidence.company_management.domain",
    "interview_evidence.submission_analysis.domain",
    "interview_evidence.interview_engine.domain",
    "interview_evidence.reporting.domain",
)


def load_domain_metadata() -> MetaData:
    """Compose lane ORM metadata only inside Alembic's Integration boundary."""
    for package_name in DOMAIN_PACKAGES:
        try:
            package = importlib.import_module(package_name)
        except ModuleNotFoundError as error:
            if error.name is not None and package_name.startswith(error.name):
                continue
            raise
        package_path = getattr(package, "__path__", None)
        if package_path is None:
            continue
        for module in pkgutil.walk_packages(package_path, prefix=f"{package_name}."):
            importlib.import_module(module.name)
    return metadata


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# Every lane maps its tables through the shared public registry.
target_metadata = load_domain_metadata()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
