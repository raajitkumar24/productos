import json

from fastapi.testclient import TestClient

from productos.api import create_app
from productos.config import Settings


def _app():
    return create_app(
        Settings(database_url="sqlite+aiosqlite:///:memory:", database_auto_create=True)
    )


def _sse_payloads(response_text: str) -> list[tuple[str, dict[str, object]]]:
    results = []
    for block in response_text.strip().split("\n\n"):
        lines = block.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        results.append((event, data))
    return results


def test_health_reports_runtime_metadata() -> None:
    with TestClient(_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["runtime_version"] == "0.8.0"
    assert response.json()["memory_policy_version"] == "1.0.0"
    assert response.json()["retrieval_policy_version"] == "1.0.0"
    assert response.json()["tool_contract_version"] == "1.0.0"


def test_chat_stream_has_run_delta_complete_and_inspectable_trace() -> None:
    with TestClient(_app()) as client:
        response = client.post("/v1/chat", json={"message": "What should we build?"})
        events = _sse_payloads(response.text)
        run_id = events[0][1]["run_id"]
        trace_response = client.get(f"/v1/runs/{run_id}/traces")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert events[0][0] == "run"
    assert any(event == "delta" for event, _ in events)
    assert events[-1][0] == "complete"
    assert trace_response.status_code == 200
    trace_types = [item["event_type"] for item in trace_response.json()["events"]]
    assert trace_types == [
        "run.started",
        "intent.classified",
        "workflow.selected",
        "context.build_started",
        "memory.search_started",
        "memory.search_completed",
        "context.build_completed",
        "retrieval.started",
        "retrieval.completed",
        "evidence.packet_created",
        "model.stream_started",
        "model.stream_completed",
        "memory.candidates_extracted",
        "memory.write_completed",
        "run.completed",
    ]


def test_chat_rejects_empty_message() -> None:
    with TestClient(_app()) as client:
        response = client.post("/v1/chat", json={"message": ""})

    assert response.status_code == 422
