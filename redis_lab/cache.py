"""Запуск: python -m redis_lab.cache --ttl 3."""
import argparse
import json
import time
from uuid import uuid4

from redis import Redis

from redis_lab.connection import connect


class JsonCache:
    def __init__(self, client: Redis, prefix: str = "lab:cache:"):
        self.client = client
        self.prefix = prefix

    def get_or_load(self, key, loader, ttl_seconds=30):
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or ttl_seconds <= 0:
            raise ValueError("TTL должен быть положительным целым числом секунд")
        redis_key = self.prefix + key
        cached = self.client.get(redis_key)
        # JSON null, false и 0 — допустимые значения, а None от GET — промах.
        if cached is not None:
            return json.loads(cached)
        value = loader()
        self.client.set(redis_key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)
        return value

    def invalidate(self, key):
        return bool(self.client.delete(self.prefix + key))


def main():
    parser = argparse.ArgumentParser(description="Демонстрация кеша с TTL")
    parser.add_argument("--ttl", type=int, default=3)
    args = parser.parse_args()
    if args.ttl <= 0:
        parser.error("TTL должен быть больше нуля")
    loads = 0

    def load_user():
        nonlocal loads
        loads += 1
        print(f"Чтение из источника, вызов №{loads}")
        return {"id": 1, "name": "Анна", "source_call": loads}

    with connect() as client:
        cache = JsonCache(client)
        key = f"demo:{uuid4().hex}"
        try:
            print("Первый запрос:", cache.get_or_load(key, load_user, args.ttl))
            print("Повторный запрос:", cache.get_or_load(key, load_user, args.ttl))
            print("TTL в Redis:", client.ttl(cache.prefix + key))
            time.sleep(args.ttl + 0.1)
            print("После истечения TTL:", cache.get_or_load(key, load_user, args.ttl))
        finally:
            cache.invalidate(key)


if __name__ == "__main__":
    main()
