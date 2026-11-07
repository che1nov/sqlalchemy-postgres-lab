from alembic import context

from app.db import database_url, make_engine
from app.models import Base


def run_migrations():
    if context.is_offline_mode():
        context.configure(url=database_url(), target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = make_engine(database_url())
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()


run_migrations()
