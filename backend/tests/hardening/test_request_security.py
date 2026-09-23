from collections import Counter
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError

from app.core.config import Settings
from app.core.request_security import RequestSecurity
from app.core.security import TokenError, decode_token


def protected(limiter, **settings):
    app=FastAPI()
    @app.get('/api/v1/auth/login')
    def endpoint():
        return {'ok':True}
    app.add_middleware(RequestSecurity,settings=Settings(rate_limit_enabled=True,**settings),limiter=limiter)
    return TestClient(app)


def test_auth_limit_and_forged_forwarding_headers():
    counts=Counter()
    def increment(key,seconds):
        counts[key]+=1
        return counts[key]
    client=protected(increment,auth_rate_limit_per_minute=2)
    for i in range(2):
        assert client.get('/api/v1/auth/login',headers={'X-Forwarded-For':f'1.2.3.{i}'}).status_code==200
    response=client.get('/api/v1/auth/login',headers={'X-Real-IP':'8.8.8.8'})
    assert response.status_code==429 and response.headers['retry-after']=='60'
    assert response.headers['x-content-type-options']=='nosniff'


def test_redis_outage_fails_closed():
    def unavailable(*args):
        raise ConnectionError('sensitive-redis-url')
    response=protected(unavailable).get('/api/v1/auth/login')
    assert response.status_code==503
    assert 'sensitive' not in response.text


def test_body_limit():
    response=protected(lambda *_:1,request_max_bytes=1024).post('/api/v1/auth/login',content='a'*1025)
    assert response.status_code==413


@pytest.mark.parametrize('change',[{'exp':None},{'iat':None},{'sub':'bad'},{'sub':'0'},{'jti':'bad'},{'exp':0},{'type':'refresh'}])
def test_malformed_signed_tokens_are_rejected(change):
    settings=Settings(jwt_secret_key='a'*40,auth_data_encryption_key='65ujGo4u-rd5tR5SJEB0mvwCv4DZIuk6S7jgpQ8xOEc=')
    payload={'sub':'1','type':'access','iat':datetime.now(timezone.utc),'exp':datetime.now(timezone.utc)+timedelta(minutes=1)}
    payload.update(change)
    payload={k:v for k,v in payload.items() if v is not None}
    with pytest.raises(TokenError):
        decode_token(jwt.encode(payload,settings.jwt_secret_key,algorithm='HS256'),'access',settings)
