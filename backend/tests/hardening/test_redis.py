import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from redis import Redis
from app.core.request_security import LUA


@pytest.mark.skipif(not os.getenv('REDIS_TEST_URL'),reason='Disposable Redis required')
def test_redis_limit_is_atomic_with_expiry():
    r=Redis.from_url(os.environ['REDIS_TEST_URL'])
    key='qa:'+uuid4().hex
    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            counts=list(pool.map(lambda _:int(r.eval(LUA,1,key,60)),range(100)))
        assert sorted(counts)==list(range(1,101))
        assert 0<r.ttl(key)<=60
    finally:
        r.delete(key); r.close()
