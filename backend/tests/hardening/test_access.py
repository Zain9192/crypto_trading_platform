from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.admin import router
from app.auth.dependencies import get_current_user


def test_all_admin_routes_reject_nonadmin_before_storage_or_provider_calls():
    app=FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':2,'role':'trader'}
    with TestClient(app) as client:
        for method,path in [('GET','/admin/users'),('GET','/admin/overview'),('GET','/admin/models'),('GET','/admin/operations'),('GET','/admin/audit'),('POST','/admin/health/check'),('POST','/admin/models/1/check'),('PUT','/admin/users/1')]:
            assert client.request(method,path,json={'role':'admin','is_active':True}).status_code==403
