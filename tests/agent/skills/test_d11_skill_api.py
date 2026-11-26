"""D11 endpoint tests: router uses Java-authoritative authentication before reads."""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.skills import api


def test_catalog_requires_java_identity(monkeypatch):
    async def reject(auth):raise HTTPException(401,'unauthorized')
    monkeypatch.setattr(api.workflow_api,'_authenticated_user',reject)
    app=FastAPI();app.include_router(api.router)
    client=TestClient(app)
    assert client.get('/api/agent/skills').status_code==401


def test_execute_never_runs_before_auth(monkeypatch):
    async def reject(auth):raise HTTPException(401,'unauthorized')
    async def forbidden(*args):raise AssertionError('never execute skill')
    monkeypatch.setattr(api.workflow_api,'_authenticated_user',reject)
    monkeypatch.setattr(api,'run_skill',forbidden)
    app=FastAPI();app.include_router(api.router)
    response=TestClient(app).post('/api/agent/skills/skill_account_snapshot/execute',json={})
    assert response.status_code==401
