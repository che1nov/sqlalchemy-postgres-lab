"""Интеграционные тесты Redis с отдельным префиксом ключей на каждый тест."""
import json
import subprocess
import sys
import time
import unittest
from uuid import uuid4

from redis_lab.cache import JsonCache
from redis_lab.connection import connect
from redis_lab.task_queue import TaskQueue


class RedisLabTest(unittest.TestCase):
    def setUp(self):
        self.client = connect()
        self.addCleanup(self.client.close)
        self.client.ping()
        self.prefix = f"test:redis:{uuid4().hex}:"
        self.addCleanup(self.remove_test_keys)

    def remove_test_keys(self):
        keys = list(self.client.scan_iter(match=self.prefix + "*"))
        if keys:
            self.client.delete(*keys)

    def test_cache_hit_and_expiration(self):
        cache = JsonCache(self.client, self.prefix)
        calls = []

        def load():
            calls.append(1)
            return {"version": len(calls)}

        self.assertEqual(cache.get_or_load("user", load, 1), {"version": 1})
        self.assertEqual(cache.get_or_load("user", load, 1), {"version": 1})
        self.assertGreater(self.client.pttl(self.prefix + "user"), 0)
        deadline = time.monotonic() + 4
        while self.client.exists(self.prefix + "user") and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(self.client.exists(self.prefix + "user"))
        self.assertEqual(cache.get_or_load("user", load, 1), {"version": 2})
        self.assertTrue(cache.invalidate("user"))

    def test_cache_falsy_values_and_validation(self):
        cache = JsonCache(self.client, self.prefix)
        for i, value in enumerate([None, False, 0, [], {}]):
            key = str(i)
            self.assertEqual(cache.get_or_load(key, lambda: value), value)
            self.assertEqual(cache.get_or_load(key, lambda: self.fail("Кеш не должен промахнуться")), value)
        with self.assertRaises(ValueError):
            cache.get_or_load("bad", lambda: 1, 0)
        with self.assertRaises(RuntimeError):
            cache.get_or_load("error", lambda: (_ for _ in ()).throw(RuntimeError("Источник недоступен")))
        self.assertFalse(self.client.exists(self.prefix + "error"))

    def test_queue_fifo_results_and_empty(self):
        queue = TaskQueue(self.client, self.prefix + "queue")
        first = queue.enqueue_sum([1, 2, 3])
        second = queue.enqueue_sum([-2, 5])
        self.assertIsNone(queue.get_result(first))
        self.assertEqual(queue.process_one(), {"id": first, "status": "done", "value": 6})
        self.assertEqual(queue.process_one(), {"id": second, "status": "done", "value": 3})
        self.assertEqual(queue.get_result(first)["value"], 6)
        self.assertGreater(self.client.ttl(f"{queue.key}:result:{first}"), 0)
        self.assertIsNone(queue.process_one(timeout=1))

    def test_queue_bad_task_does_not_stop_worker(self):
        queue = TaskQueue(self.client, self.prefix + "queue")
        self.client.rpush(queue.key, "not-json", json.dumps({"id": "bad", "type": "unknown"}))
        task_id = queue.enqueue_sum([10, 20])
        self.assertEqual(queue.process_one()["status"], "failed")
        self.assertEqual(queue.process_one()["status"], "failed")
        self.assertEqual(queue.get_result("bad")["status"], "failed")
        self.assertEqual(queue.process_one()["id"], task_id)
        self.assertEqual(queue.get_result(task_id)["value"], 30)

    def test_producer_and_worker_scripts(self):
        key = self.prefix + "queue"
        subprocess.run([sys.executable, "-m", "redis_lab.task_queue", "4", "5", "--queue", key],
                       capture_output=True, text=True, timeout=10, check=True)
        process = subprocess.run([sys.executable, "-m", "redis_lab.worker", "--once", "--queue", key],
                                 capture_output=True, text=True, timeout=10, check=True)
        result = json.loads(process.stdout.splitlines()[-1])
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["value"], 9)
        self.assertEqual(TaskQueue(self.client, key).get_result(result["id"]), result)

    def test_pubsub_separate_processes(self):
        channel = self.prefix + "events"
        # До подписки Redis не сохраняет событие для будущих подписчиков.
        self.assertEqual(self.client.publish(channel, "before subscription"), 0)
        subscriber = subprocess.Popen(
            [sys.executable, "-m", "redis_lab.subscriber", "--channel", channel, "--count", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            deadline = time.monotonic() + 5
            while self.client.pubsub_numsub(channel)[0][1] == 0 and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(self.client.pubsub_numsub(channel)[0][1], 1)
            publisher = subprocess.run(
                [sys.executable, "-m", "redis_lab.publisher", "Привет из теста", "--channel", channel],
                capture_output=True, text=True, timeout=10, check=True,
            )
            output, errors = subscriber.communicate(timeout=5)
            self.assertEqual(subscriber.returncode, 0, errors)
            self.assertIn("Привет из теста", output)
            self.assertIn("подключённых подписчиков: 1", publisher.stdout)
            self.assertNotIn("before subscription", output)
        finally:
            if subscriber.poll() is None:
                subscriber.kill()
            subscriber.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
