import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.agent.tools import calculator


def test_calculator_tool():
    assert calculator("2 + 2") == "4"
    assert calculator("(10 * 5) / 2") == "25.0"
    assert calculator("2 ** 3") == "8"
    assert "Error" in calculator("import os")


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


@pytest.mark.asyncio
async def test_chat_multi_turn_memory():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        thread_id = "test-pytest-session-001"

        # Turn 1: Save secret number
        r1 = await ac.post(
            "/api/v1/chat",
            json={"message": "My lucky number is 77.", "thread_id": thread_id},
        )
        assert r1.status_code == 200
        assert r1.json()["thread_id"] == thread_id

        # Turn 2: Query memory and perform calculation
        r2 = await ac.post(
            "/api/v1/chat",
            json={
                "message": "What is my lucky number multiplied by 2?",
                "thread_id": thread_id,
            },
        )
        assert r2.status_code == 200
        assert "154" in r2.json()["response"]


@pytest.mark.asyncio
async def test_correlation_id_propagation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Case 1: Server generates correlation ID
        res1 = await ac.get("/health")
        assert "x-request-id" in res1.headers
        assert len(res1.headers["x-request-id"]) > 0

        # Case 2: Client provides custom correlation ID
        custom_id = "client-req-9999"
        res2 = await ac.get("/health", headers={"X-Request-ID": custom_id})
        assert res2.headers["x-request-id"] == custom_id


@pytest.mark.asyncio
async def test_error_handling_response():
    from unittest.mock import patch
    from openai import RateLimitError
    import httpx

    # Simulate an OpenAI RateLimitError on the graph
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        fake_response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
        with patch("app.api.v1.routes.agent_graph.ainvoke", side_effect=RateLimitError("Rate limit hit", response=fake_response, body=None)):
            res = await ac.post(
                "/api/v1/chat",
                json={"message": "hello", "thread_id": "err-test"},
                headers={"X-Request-ID": "test-err-req-1"},
            )
            assert res.status_code == 429
            data = res.json()
            assert "error" in data
            assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"
            assert data["error"]["request_id"] == "test-err-req-1"
            assert res.headers["x-request-id"] == "test-err-req-1"


@pytest.mark.asyncio
async def test_streaming_ttft_and_events():
    import time
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        thread_id = "test-stream-ttft-001"
        start_time = time.perf_counter()
        first_token_time = None
        tokens_received = []

        async with ac.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"message": "Count from 1 to 5.", "thread_id": thread_id},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    raw_data = line.replace("data:", "").strip()
                    if raw_data:
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                        tokens_received.append(raw_data)

        total_time = time.perf_counter() - start_time
        assert first_token_time is not None, "Did not receive any streamed tokens"
        ttft = first_token_time - start_time

        # Verify TTFT occurred and was properly tracked before total completion
        assert ttft > 0
        assert ttft <= total_time
        assert len(tokens_received) > 0
