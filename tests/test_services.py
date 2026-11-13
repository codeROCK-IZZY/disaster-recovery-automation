"""The Claude runbook converter (real SDK, canned responses), the console and the command line."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from drp.app import Console, create_app, demo_console
from drp.cli import main
from drp.runbook import FALLBACK_BETA, MODEL, Converter

Setup = tuple[Console, str, str, str]


def message(*content: dict[str, Any], stop: str = "tool_use") -> dict[str, Any]:
    return {
        "id": "m",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": list(content),
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


class Script:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses: Iterator[dict[str, Any]] = iter(responses)
        self.requests: list[dict[str, Any]] = []
        self.headers: list[httpx2.Headers] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        self.headers.append(request.headers)
        return httpx2.Response(200, json=next(self.responses))


def converter(script: Script) -> Converter:
    client = anthropic.Anthropic(
        api_key="test",
        base_url="http://api.test",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(script)),
    )
    return Converter(client)


def steps_call(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "tool_use", "id": "t", "name": "record_plan", "input": {"steps": steps}}


def step(i: int, system: str, action: str, after: list[int], quote: str) -> dict[str, Any]:
    return {"id": i, "system": system, "action": action, "after": after, "quote": quote}


@pytest.fixture
def setup() -> Setup:
    console = demo_console()
    est = console.est
    top = next(n for n in sorted(est.systems) if len(est.systems[n].depends_on) == 1)
    (dep,) = est.systems[top].depends_on
    return console, top, dep, f"First restore {dep} from backup.\nThen restore {top} and switch DNS to it."


def test_converter_request_and_a_clean_plan(setup: Setup) -> None:
    console, top, dep, text = setup
    script = Script(
        [
            message(
                steps_call(
                    [
                        step(1, dep, "restore_backup", [], f"restore {dep} from backup"),
                        step(2, top, "restore_backup", [1], f"restore {top}"),
                        step(3, top, "switch_dns", [2], "switch DNS to it"),
                    ]
                )
            )
        ]
    )
    c = converter(script).convert(console.est, text)
    assert c.executable and [s.action for s in c.steps] == ["restore_backup", "restore_backup", "switch_dns"]
    req = script.requests[0]
    assert req["model"] == MODEL and req["output_config"] == {"effort": "low"} and req["fallbacks"] == "default"
    assert "thinking" not in req and "tool_choice" not in req
    assert req["tools"][0]["strict"] is True and req["tools"][0]["name"] == "record_plan"
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"} and top in req["system"][0]["text"]
    assert "<runbook>" in req["messages"][0]["content"]
    assert FALLBACK_BETA in script.headers[0]["anthropic-beta"]


def test_converter_output_is_checked_not_trusted(setup: Setup) -> None:
    console, top, dep, text = setup
    script = Script(
        [
            message(
                steps_call(
                    [
                        step(1, top, "restore_backup", [], f"restore {top}"),
                        step(2, dep, "restore_backup", [], f"restore {dep} from backup"),
                        step(3, "payments-db", "restore_backup", [], "restore the payments database"),
                    ]
                )
            )
        ]
    )
    c = converter(script).convert(console.est, text)
    assert not c.executable
    joined = " | ".join(c.problems)
    assert f"restores {top} without waiting for {dep}" in joined
    assert "payments-db is not in the inventory" in joined
    assert "step 3: its quote is not in the runbook" in joined


def test_refusal_or_no_tool_call_gives_no_plan(setup: Setup) -> None:
    console, _, _, text = setup
    for resp in (
        message({"type": "text", "text": "no"}, stop="refusal"),
        message({"type": "text", "text": "hi"}, stop="end_turn"),
    ):
        c = converter(Script([resp])).convert(console.est, text)
        assert not c.executable and c.problems == ["no plan was produced"]


def test_console_pages_and_apis(setup: Setup) -> None:
    console, top, _, _ = setup
    c = TestClient(create_app(console))
    assert c.get("/healthz").json()["claude"] is False
    for path in ("/", "/systems", f"/systems/{top}", "/recovery/zone-a", "/recovery/everything", "/runbook"):
        assert c.get(path).status_code == 200, path
    assert c.get("/systems/nope").status_code == 404 and c.get("/recovery/mars").status_code == 404
    sched = c.get("/api/schedule").json()
    assert len(sched) == 6 and sched[0]["score"] >= sched[-1]["score"]
    p = c.post("/api/plan", json={"systems": [top]}).json()
    assert p["steps"][0]["system"] == top
    assert c.post("/api/plan", json={"systems": ["nope"]}).status_code == 422
    assert c.post("/api/runbook", json={"text": "x"}).status_code == 503
    assert c.post("/runbook", data={"text": "x"}).status_code == 503
    page = c.get("/runbook").text
    assert "not executable" in page and "ledger-legacy is not in the inventory" in page


def test_console_converts_with_claude(setup: Setup) -> None:
    console, top, dep, text = setup
    console.converter = converter(
        Script(
            [
                message(
                    steps_call(
                        [
                            step(1, dep, "restore_backup", [], f"restore {dep} from backup"),
                            step(2, top, "restore_backup", [1], f"restore {top}"),
                        ]
                    )
                )
            ]
        )
    )
    c = TestClient(create_app(console))
    r = c.post("/runbook", data={"text": text})
    assert r.status_code == 200 and "executable" in r.text and "Converted by Claude" in r.text
    assert c.post("/runbook", data={"text": " "}).status_code == 422


def test_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schedule"]) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 6
    assert main(["plan"]) == 0
    assert "everything back after" in capsys.readouterr().out
    assert main(["plan", "nope"]) == 2
