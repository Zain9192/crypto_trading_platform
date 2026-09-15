from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, field_validator
from app.exchange.contracts import Contract, Credentials, ExchangeName


class ConnectionCreate(Contract):
    exchange: ExchangeName
    label: str = Field(min_length=1, max_length=80)
    sandbox: bool = True
    credentials: Credentials

    @field_validator('label')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Label must not be blank')
        return value.strip()


class ConnectionView(Contract):
    connection_id: UUID
    exchange: ExchangeName
    label: str
    sandbox: bool
    read_only: Literal[True] = True
    credentials_configured: bool = True
    created_at: datetime
    updated_at: datetime
