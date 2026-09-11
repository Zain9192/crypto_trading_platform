from unittest.mock import Mock

import psycopg
from fastapi.testclient import TestClient

from app.api.routes.portfolio import get_portfolio_service
from app.auth.dependencies import get_auth_service, get_current_user
from app.main import app


def test_portfolio_requires_authentication():
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_auth_service] = lambda: Mock()
    app.dependency_overrides[get_portfolio_service] = lambda: Mock()
    try:
        assert TestClient(app).get('/api/v1/portfolios').status_code == 401
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_database_failure_has_safe_response():
    previous = app.dependency_overrides.copy()
    service = Mock()
    service.list.side_effect = psycopg.OperationalError('private connection details')
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 1}
    app.dependency_overrides[get_portfolio_service] = lambda: service
    try:
        response = TestClient(app).get('/api/v1/portfolios')
        assert response.status_code == 503
        assert response.json() == {'detail': 'Portfolio storage is unavailable'}
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
