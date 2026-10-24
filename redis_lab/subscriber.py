"""Запускается до publisher; Ctrl+C завершает чтение."""
import argparse

from redis_lab.connection import connect


def main():
    parser = argparse.ArgumentParser(description="Читать сообщения Redis Pub/Sub")
    parser.add_argument("--channel", default="lab:events")
    parser.add_argument("--count", type=int, default=0, help="Завершиться после N сообщений; 0 — читать постоянно")
    args = parser.parse_args()
    if args.count < 0:
        parser.error("count не может быть отрицательным")
    received = 0
    try:
        with connect() as client, client.pubsub() as pubsub:
            pubsub.subscribe(args.channel)
            for event in pubsub.listen():
                if event["type"] == "subscribe":
                    print(f"Подписка готова: {args.channel}", flush=True)
                elif event["type"] == "message":
                    print(f"Получено: {event['data']}", flush=True)
                    received += 1
                    if args.count and received >= args.count:
                        break
    except KeyboardInterrupt:
        print("Подписчик остановлен")


if __name__ == "__main__":
    main()
