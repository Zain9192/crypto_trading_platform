# Foundation Architecture

The project follows the layered, microservice-ready architecture defined by the SDD while starting as a modular codebase to keep the MVP manageable.

```text
React SPA
   |
HTTPS / WebSocket
   |
API / Reverse Proxy
   |
FastAPI application
   |-- Authentication module (future feature)
   |-- Market data module (future feature)
   |-- AI prediction module (future feature)
   |-- Portfolio & risk module (future feature)
   |-- Automated trading module (future feature)
   |-- Notification/reporting module (future feature)
   |
   |-- PostgreSQL: users, portfolios, trades, alerts, model metadata
   |-- MongoDB: OHLCV market data and prediction logs
   |-- Redis: real-time cache and transient state
```

## Foundation decisions

- FastAPI is the primary backend runtime so the service layer and ML stack stay in Python.
- PostgreSQL is the source of truth for relational and transactional records.
- MongoDB is reserved for high-volume market/time-series documents.
- Redis is used only for cache/transient data, never as the primary source of truth.
- Each later feature will get its own branch and tests before merge.
