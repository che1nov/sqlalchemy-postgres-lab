import os

from pymongo import MongoClient
from pymongo.errors import OperationFailure
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError


PAYLOAD = "' OR '1'='1' --"


def unsafe_lookup(connection, username):
    """Намеренная уязвимость только для лабораторной работы: так писать нельзя."""
    query = f"SELECT username FROM lab.accounts WHERE username = '{username}' ORDER BY username"
    return list(connection.execute(text(query)).scalars())


def safe_lookup(connection, username):
    # Значение передаётся отдельно от SQL, не конкатенируется с текстом запроса.
    query = text("SELECT username FROM lab.accounts WHERE username = :username ORDER BY username")
    return list(connection.execute(query, {"username": username}).scalars())


def make_engine():
    return create_engine(os.environ["SECURITY_DATABASE_URL"], hide_parameters=True)


def main():
    engine = make_engine()
    try:
        with engine.connect() as connection:
            unsafe = unsafe_lookup(connection, PAYLOAD)
            safe = safe_lookup(connection, PAYLOAD)
            normal = safe_lookup(connection, "alice")
            assert set(unsafe) == {"alice", "bob"}
            assert safe == []
            assert normal == ["alice"]
            print("Вредоносный ввод:", PAYLOAD)
            print("Сырой SQL раскрыл записи:", sorted(unsafe))
            print("Параметризованный SQL:", safe)
            print("Обычный ввод работает:", normal)

        # Даже при ошибке настройки прав DDL откатывается, таблица не теряется.
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("DROP TABLE lab.accounts"))
            except ProgrammingError as error:
                if error.orig.sqlstate != "42501":
                    raise
                print("DROP TABLE запрещён: insufficient_privilege (42501)")
            else:
                raise AssertionError("Роль приложения не должна удалять таблицы")
            finally:
                transaction.rollback()
    finally:
        engine.dispose()

    with MongoClient(os.environ["SECURITY_MONGODB_URI"], serverSelectionTimeoutMS=5000) as client:
        count = client.security_lab.accounts.count_documents({})
        assert count == 2
        print("MongoDB: вход под lab_app успешен, учебных записей:", count)
    with MongoClient(os.environ["SECURITY_MONGODB_NOAUTH_URI"], serverSelectionTimeoutMS=5000) as client:
        try:
            client.security_lab.accounts.find_one({})
        except OperationFailure as error:
            if error.code != 13:
                raise
            print("MongoDB: чтение без аутентификации запрещено (Unauthorized, 13)")
        else:
            raise AssertionError("MongoDB не должна разрешать чтение без аутентификации")


if __name__ == "__main__":
    main()
