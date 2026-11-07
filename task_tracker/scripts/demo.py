"""Exercise the running HTTP service; never writes directly to its database."""
import argparse
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def run(base_url: str, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    token = None

    def call(method, path, body=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers, method=method,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            if response.headers.get_content_type() == "image/png":
                return raw
            return json.loads(raw) if raw else None

    credentials = {"username": f"demo_{secrets.token_hex(4)}", "password": secrets.token_urlsafe(24)}
    user = call("POST", "/auth/register", credentials)
    token = call("POST", "/auth/login", credentials)["access_token"]
    topics = ["Database", "API", "Tests"]
    statuses = ["done"] * 6 + ["in_progress"] * 3 + ["new"] * 2 + ["cancelled"]
    for i, status in enumerate(statuses):
        task = call("POST", "/tasks", {"title": f"Demo task {i + 1:02d}", "topic": topics[i % 3], "assignee_id": user["id"] if i % 2 == 0 else None})
        call("PATCH", f"/tasks/{task['id']}", {"status": status})
    temporary = call("POST", "/tasks", {"title": "CRUD delete demonstration"})
    call("GET", f"/tasks/{temporary['id']}")
    call("DELETE", f"/tasks/{temporary['id']}")
    filtered = call("GET", "/tasks?status=done&topic=Database")
    assert filtered["total"] == 2
    summaries = {}
    for group in ("status", "topic", "assignee"):
        summaries[group] = call("GET", f"/analytics/tasks?group_by={group}")
        (output / f"by_{group}.png").write_bytes(call("GET", f"/analytics/tasks.png?group_by={group}"))
    assert summaries["status"]["total"] == 12
    assert summaries["status"]["completion_rate"] == 50
    (output / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + "\n")
    call("POST", "/auth/logout")
    try:
        call("GET", "/tasks")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("Logout must revoke access")
    print(f"Demo passed: 12 tasks, 6 done, completion 50%. Artifacts: {output}")
    print("Created a separate demo account; password and token were not saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("output/demo"))
    args = parser.parse_args()
    run(args.url, args.output)
