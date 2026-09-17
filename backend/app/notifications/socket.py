import asyncio

import psycopg
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from psycopg.rows import dict_row

from app.auth.repository import PostgresUserRepository
from app.auth.service import AuthService, AuthenticationError
from app.core.config import get_settings
from app.core.security import TokenError
from app.notifications.repository import NotificationRepository


def snapshot(token):
    settings = get_settings()
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as connection:
        user = AuthService(PostgresUserRepository(connection), settings).current_user(token)
    return NotificationRepository(settings.postgres_dsn).listing(user['user_id'], limit=25)


async def notification_socket(socket: WebSocket):
    await socket.accept()
    try:
        # Credentials travel in the first frame, never in URLs or access logs.
        frame = await asyncio.wait_for(socket.receive_text(), timeout=10)
        if not frame or len(frame) > 8192:
            await socket.close(code=4401)
            return
        token = frame
        while True:
            # Revalidate account status and token expiry before each snapshot.
            data = await asyncio.to_thread(snapshot, token)
            await asyncio.wait_for(socket.send_json(jsonable_encoder({'type': 'notifications', **data})), timeout=10)
            try:
                await asyncio.wait_for(socket.receive_text(), timeout=5)
                # No client messages are needed after authentication.
                await socket.close(code=4400)
                return
            except asyncio.TimeoutError:
                pass
    except (TokenError, AuthenticationError):
        await socket.close(code=4401)
    except psycopg.Error:
        await socket.close(code=1013)
    except asyncio.TimeoutError:
        await socket.close(code=4408)
    except (WebSocketDisconnect, RuntimeError):
        pass
