"""Простой обработчик очереди; Ctrl+C для остановки."""
import argparse
import json

from redis_lab.connection import connect
from redis_lab.task_queue import TaskQueue


def main():
    parser = argparse.ArgumentParser(description="Обрабатывать задачи Redis")
    parser.add_argument("--queue", default="lab:tasks")
    parser.add_argument("--once", action="store_true", help="Одна попытка чтения с ожиданием до 2 секунд")
    args = parser.parse_args()
    try:
        with connect() as client:
            queue = TaskQueue(client, args.queue)
            print(f"Обработчик готов: {args.queue}", flush=True)
            while True:
                result = queue.process_one(timeout=2)
                if result is not None:
                    print(json.dumps(result, ensure_ascii=False), flush=True)
                if args.once:
                    if result is None:
                        print("Очередь пуста")
                    break
    except KeyboardInterrupt:
        print("Обработчик остановлен")


if __name__ == "__main__":
    main()
