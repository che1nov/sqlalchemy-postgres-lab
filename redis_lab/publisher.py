"""Отдельный процесс публикации сообщений."""
import argparse
import json
from datetime import datetime, timezone

from redis_lab.connection import connect


def main():
    parser = argparse.ArgumentParser(description="Опубликовать сообщение Redis Pub/Sub")
    parser.add_argument("message")
    parser.add_argument("--channel", default="lab:events")
    args = parser.parse_args()
    message = {"text": args.message, "sent_at": datetime.now(timezone.utc).isoformat()}
    with connect() as client:
        subscribers = client.publish(args.channel, json.dumps(message, ensure_ascii=False))
    print(f"Сообщение опубликовано; подключённых подписчиков: {subscribers}")


if __name__ == "__main__":
    main()
