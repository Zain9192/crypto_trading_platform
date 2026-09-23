import hashlib
import ipaddress
import time

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from redis.exceptions import RedisError

from app.db.redis_store import get_redis_client


LUA = """
local value=redis.call('INCR',KEYS[1])
if value==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end
return value
"""


class RequestSecurity:
    def __init__(self, app, settings, limiter=None):
        self.app,self.settings,self.limiter=app,settings,limiter or self.count

    @staticmethod
    def count(key,seconds):
        return int(get_redis_client().eval(LUA,1,key,seconds))

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http','websocket'):
            return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]))
        async def secured_send(message):
            if message['type']=='http.response.start':
                message.setdefault('headers',[]).extend([
                    (b'x-content-type-options',b'nosniff'),(b'x-frame-options',b'DENY'),
                    (b'referrer-policy',b'no-referrer'),(b'cache-control',b'no-store')])
            await send(message)
        async def reject(code,detail,extra=None):
            if scope['type']=='websocket':
                await send({'type':'websocket.close','code':4429 if code==429 else 4403})
            else:
                await JSONResponse({'detail':detail},status_code=code,headers=extra)(scope,receive,secured_send)
        if scope['type']=='http':
            try:
                if int(headers.get(b'content-length',b'0'))>self.settings.request_max_bytes:
                    return await reject(413,'Request is too large')
            except ValueError:
                return await reject(400,'Invalid content length')
        if self.settings.rate_limit_enabled:
            peer=(scope.get('client') or ('unknown',0))[0]
            try:
                trusted=any(ipaddress.ip_address(peer) in ipaddress.ip_network(c.strip()) for c in self.settings.trusted_proxy_cidrs.split(',') if c.strip())
                if trusted and b'x-real-ip' in headers:
                    peer=str(ipaddress.ip_address(headers[b'x-real-ip'].decode()))
            except ValueError:
                pass
            path=scope.get('path','')
            group='auth' if '/auth/' in path and not path.endswith('/me') else 'api'
            limit=self.settings.auth_rate_limit_per_minute if group=='auth' else self.settings.api_rate_limit_per_minute
            identity=hashlib.sha256(peer.encode()).hexdigest()
            key=f'http-limit:{group}:{identity}:{int(time.time())//60}'
            try:
                count=await run_in_threadpool(self.limiter,key,60)
            except RedisError:
                return await reject(503,'Request protection is temporarily unavailable')
            if count>limit:
                return await reject(429,'Too many requests',{'Retry-After':'60'})
        # Bound chunked bodies as well as Content-Length, before parsing JSON.
        if scope['type']=='http':
            body=[]
            size=0
            while True:
                message=await receive()
                if message['type']=='http.disconnect':
                    return
                size+=len(message.get('body',b''))
                if size>self.settings.request_max_bytes:
                    return await reject(413,'Request is too large')
                body.append(message)
                if not message.get('more_body',False):
                    break
            async def buffered_receive():
                return body.pop(0) if body else await receive()
            return await self.app(scope,buffered_receive,secured_send)
        return await self.app(scope,receive,secured_send)
