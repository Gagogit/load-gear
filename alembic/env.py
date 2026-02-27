import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add src/ to path so we can import load_gear
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from load_gear.core.database import Base  # noqa: E402
from load_gear.models import analysis, control, data  # noqa: E402, F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Ignore PostGIS/TimescaleDB system tables
EXCLUDE_TABLES = {"spatial_ref_sys", "geography_columns", "geometry_columns", "raster_columns", "raster_overviews"}


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in EXCLUDE_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
