# Phase 5 — Portfolio and Risk

Branch: `feature/portfolio-risk`, based on merged PR #8 and successful main CI.

- [x] 1. PostgreSQL migration: owned paper portfolios, holdings, reservations, immutable fills, risk settings.
- [x] 2. Decimal accounting: cash, available balances, average cost, fees, realized/unrealized P&L, allocation.
- [x] 3. Risk validation: investment bounds, maximum positions/pending trades, stop-loss/take-profit settings.
- [x] 4. Authenticated APIs: overview, risk settings, order preview/reserve/cancel/paper fill, paginated history.
- [x] 5. Frontend: sign-in, portfolio creation, holdings/allocation, paper trades, risk form and history.
- [x] 6. Tests: financial invariants, missing quotes, ownership, retries, concurrent reservations, frontend workflows.
- [x] 7. Documentation: migration, local walkthrough, phase boundaries and verification results.
- [x] 8. Push feature branch, pass CI, open PR for owner review.

Phase boundary: virtual USD only; user-entered simulation prices are explicitly labeled. No exchange orders or real deposits. Stop-loss/take-profit values are stored and displayed; automated monitoring/execution belongs to Phase 7. Public market quotes value holdings but are never silently substituted for missing prices. Tests use synthetic prices and a disposable PostgreSQL database.

Verification:
- 85 backend tests passed in CI, including six disposable PostgreSQL integration tests.
- 10 frontend tests, TypeScript checking and production build passed.
- Final implementation CI: https://github.com/Zain9192/crypto_trading_platform/actions/runs/34636244117
- Review PR: https://github.com/Zain9192/crypto_trading_platform/pull/9
- PR #9 merged on 2026-09-11. Phase 6 has started on `feature/exchange-integration`.
- Live deployment and provider integration were not exercised here; README contains the migration and frontend walkthrough.
