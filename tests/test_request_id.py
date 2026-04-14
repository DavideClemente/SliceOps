class TestRequestIDMiddleware:
    async def test_response_has_request_id(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        # Should be a valid UUID4
        import uuid
        uuid.UUID(resp.headers["X-Request-ID"])

    async def test_echoes_provided_request_id(self, client):
        custom_id = "my-custom-request-id-123"
        resp = await client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
        assert resp.headers["X-Request-ID"] == custom_id
