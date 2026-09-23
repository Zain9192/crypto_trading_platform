from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.core.request_security import RequestSecurity
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.admin import router as admin_router
from app.api.routes.health import router as health_router
from app.api.routes.market import router as market_router
from app.api.routes.prediction import router as prediction_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.exchange import router as exchange_router
from app.api.routes.trading import router as trading_router
from app.api.routes.notifications import router as notifications_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.7.0",
    description="Backend API for the AI Crypto Trading Platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[value.strip() for value in settings.cors_origins.split(",") if value.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestSecurity,settings=settings)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request,exc):
    return JSONResponse(status_code=422,content={'detail':[
        {'loc':list(error['loc']),'type':error['type'],'msg':error['msg']}
        for error in exc.errors()]})


app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)
app.include_router(market_router, prefix=settings.api_v1_prefix)
app.include_router(prediction_router, prefix=settings.api_v1_prefix)
app.include_router(portfolio_router, prefix=settings.api_v1_prefix)
app.include_router(exchange_router, prefix=settings.api_v1_prefix)
app.include_router(trading_router, prefix=settings.api_v1_prefix)
app.include_router(notifications_router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
