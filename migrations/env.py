from alembic import context

from orm_lab.db import make_engine
from orm_lab.models import Base


def include_name(name, type_, parent_names):
    # Управляем только учебной ORM-схемой, не трогаем public.users из Core.
    if type_ == "schema":
        return name == "orm_lab"
    return True


def configure(connection=None, url=None):
    context.configure(
        connection=connection,
        url=url,
        target_metadata=Base.metadata,
        include_schemas=True,
        include_name=include_name,
        version_table_schema="orm_lab",
        compare_type=True,
        literal_binds=connection is None,
    )


engine = make_engine()
try:
    if context.is_offline_mode():
        configure(url=engine.url)
        with context.begin_transaction():
            context.execute("CREATE SCHEMA IF NOT EXISTS orm_lab")
            context.run_migrations()
    else:
        with engine.connect() as connection:
            # Схема нужна до создания служебной таблицы alembic_version.
            connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS orm_lab")
            connection.commit()
            configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
finally:
    engine.dispose()
