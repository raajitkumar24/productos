import json

from fastapi.testclient import TestClient

from productos.api import create_app
from productos.config import Settings


def _app():
    return create_app(
        Settings(database_url="sqlite+aiosqlite:///:memory:", database_auto_create=True)
    )


def _events(response_text: str) -> list[tuple[str, dict[str, object]]]:
    parsed = []
    for block in response_text.strip().split("\n\n"):
        lines = block.splitlines()
        parsed.append(
            (
                lines[0].removeprefix("event: "),
                json.loads(lines[1].removeprefix("data: ")),
            )
        )
    return parsed


def test_explicit_preference_is_recalled_and_new_preference_preserves_history() -> None:
    with TestClient(_app()) as client:
        first = _events(
            client.post("/v1/chat", json={"message": "I prefer concise responses."}).text
        )
        first_complete = first[-1][1]
        first_memory_id = first_complete["memory_updates"][0]["memory_id"]
        first_conversation_id = first_complete["conversation_id"]

        second = _events(
            client.post("/v1/chat", json={"message": "I prefer detailed responses."}).text
        )
        second_complete = second[-1][1]
        second_memory_id = second_complete["memory_updates"][0]["memory_id"]

        memories = client.get("/v1/memories").json()
        second_detail = client.get(f"/v1/memories/{second_memory_id}").json()
        conversation = client.get(f"/v1/sessions/{first_conversation_id}").json()

        recall = _events(
            client.post("/v1/chat", json={"message": "How should you answer me?"}).text
        )
        recall_run_id = recall[0][1]["run_id"]
        traces = client.get(f"/v1/runs/{recall_run_id}/traces").json()["events"]

    by_id = {item["id"]: item for item in memories}
    assert by_id[first_memory_id]["status"] == "superseded"
    assert by_id[second_memory_id]["status"] == "active"
    assert by_id[second_memory_id]["content"] == "detailed responses"
    assert second_complete["memory_updates"][0]["outcome"] == "superseded"
    assert second_detail["outgoing"][0]["relationship_type"] == "supersedes"
    assert second_detail["outgoing"][0]["to_memory_id"] == first_memory_id
    assert [message["role"] for message in conversation["messages"]] == [
        "user",
        "assistant",
    ]
    context_trace = next(
        event for event in traces if event["event_type"] == "context.build_completed"
    )
    assert second_memory_id in context_trace["attributes"]["memory_ids"]
    assert first_memory_id not in context_trace["attributes"]["memory_ids"]


def test_memory_correction_creates_new_record_and_archive_is_non_destructive() -> None:
    with TestClient(_app()) as client:
        created = client.post(
            "/v1/memories",
            json={
                "memory_type": "semantic",
                "content": "The planning day is Monday",
                "source_type": "user",
            },
        ).json()
        original_id = created["memory"]["id"]

        corrected = client.patch(
            f"/v1/memories/{original_id}",
            json={"content": "The planning day is Tuesday"},
        ).json()
        corrected_id = corrected["memory"]["id"]
        original = client.get(f"/v1/memories/{original_id}").json()
        correction = client.get(f"/v1/memories/{corrected_id}").json()

        archived = client.patch(f"/v1/memories/{corrected_id}", json={"status": "archived"}).json()

    assert corrected_id != original_id
    assert original["memory"]["content"] == "The planning day is Monday"
    assert original["memory"]["status"] == "superseded"
    assert correction["memory"]["content"] == "The planning day is Tuesday"
    assert any(
        relationship["relationship_type"] == "corrects" for relationship in correction["outgoing"]
    )
    assert archived["memory"]["status"] == "archived"


def test_working_session_and_accepted_decision_are_persisted() -> None:
    with TestClient(_app()) as client:
        work = client.post(
            "/v1/work",
            json={
                "title": "Agent quality strategy",
                "objective": "Decide how ProductOS should evaluate agent quality",
                "workflow_type": "strategy",
                "open_questions": ["Which dimensions matter?"],
            },
        )
        decision = client.post(
            "/v1/decisions",
            json={
                "title": "Runtime architecture",
                "problem": "Choose orchestration ownership",
                "context": "The system must be inspectable",
                "decision": "Use an application-owned runtime",
                "rationale": "It keeps execution authority deterministic",
                "status": "accepted",
            },
        )
        work_list = client.get("/v1/work").json()
        decisions = client.get("/v1/decisions").json()
        decision_memories = client.get(
            "/v1/memories", params={"memory_type": "decision", "status": "active"}
        ).json()

    assert work.status_code == 201
    assert work_list[0]["objective"].startswith("Decide how ProductOS")
    assert decision.status_code == 201
    assert decisions[0]["status"] == "accepted"
    assert decisions[0]["memory_id"] == decision_memories[0]["id"]


def test_new_belief_state_supersedes_but_does_not_erase_prior_belief() -> None:
    with TestClient(_app()) as client:
        first = client.post(
            "/v1/beliefs",
            json={
                "statement": "Enterprise buyers value configurability most",
                "confidence": 0.55,
                "belief_key": "enterprise_value_driver",
                "supporting_evidence": ["Interview synthesis A"],
            },
        ).json()
        second = client.post(
            "/v1/beliefs",
            json={
                "statement": "Enterprise buyers value reliability most",
                "confidence": 0.7,
                "belief_key": "enterprise_value_driver",
                "supporting_evidence": ["Interview synthesis B"],
                "contradicting_evidence": ["Interview synthesis A"],
            },
        ).json()
        beliefs = client.get("/v1/beliefs").json()
        memories = client.get("/v1/memories", params={"memory_type": "belief"}).json()

    beliefs_by_id = {item["id"]: item for item in beliefs}
    memories_by_id = {item["id"]: item for item in memories}
    assert beliefs_by_id[first["id"]]["status"] == "superseded"
    assert beliefs_by_id[second["id"]]["status"] == "active"
    assert memories_by_id[first["memory_id"]]["status"] == "superseded"
    assert memories_by_id[second["memory_id"]]["status"] == "active"
