"""FIFO: RPUSH добавляет справа, BLPOP забирает слева."""
import argparse
import json
from uuid import uuid4

from redis import Redis

from redis_lab.connection import connect


class TaskQueue:
    def __init__(self, client: Redis, key: str = "lab:tasks", result_ttl: int = 300):
        if result_ttl <= 0:
            raise ValueError("TTL результата должен быть положительным")
        self.client = client
        self.key = key
        self.result_ttl = result_ttl

    def enqueue_sum(self, numbers):
        if not isinstance(numbers, list) or not all(type(n) is int for n in numbers):
            raise ValueError("Ожидается список целых чисел")
        task_id = uuid4().hex
        task = {"id": task_id, "type": "sum", "numbers": numbers}
        self.client.rpush(self.key, json.dumps(task))
        return task_id

    def get_result(self, task_id):
        raw = self.client.get(f"{self.key}:result:{task_id}")
        return json.loads(raw) if raw is not None else None

    def process_one(self, timeout: int = 2):
        """None при пустой очереди. Задача удаляется из очереди до выполнения."""
        if timeout <= 0:
            raise ValueError("timeout должен быть положительным")
        item = self.client.blpop(self.key, timeout=timeout)
        if item is None:
            return None
        task_id = None
        try:
            task = json.loads(item[1])
            if not isinstance(task, dict) or not isinstance(task.get("id"), str):
                raise ValueError("Неверный формат задачи")
            task_id = task["id"]
            numbers = task.get("numbers")
            if task.get("type") != "sum":
                raise ValueError("Неизвестный тип задачи")
            if not isinstance(numbers, list) or not all(type(n) is int for n in numbers):
                raise ValueError("Ожидается список целых чисел")
            result = {"id": task_id, "status": "done", "value": sum(numbers)}
        except ValueError as error:
            # Ошибка данных не останавливает обработку следующих задач.
            result = {"id": task_id, "status": "failed", "error": str(error)}
        if task_id is not None:
            self.client.set(f"{self.key}:result:{task_id}", json.dumps(result, ensure_ascii=False), ex=self.result_ttl)
        return result


def main():
    parser = argparse.ArgumentParser(description="Добавить задачу суммирования в Redis")
    parser.add_argument("numbers", nargs="+", type=int)
    parser.add_argument("--queue", default="lab:tasks")
    args = parser.parse_args()
    with connect() as client:
        queue = TaskQueue(client, args.queue)
        task_id = queue.enqueue_sum(args.numbers)
        print(f"Задача добавлена: {task_id}")
        print(f"Ключ результата: {args.queue}:result:{task_id} (TTL после обработки: 300 секунд)")


if __name__ == "__main__":
    main()
