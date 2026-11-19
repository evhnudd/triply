from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, geo, places, trips
from app.core.config import settings
from app.core.errors import install_error_handlers

app = FastAPI(
    title="Triply API",
    version="0.1.0 (КТ-1)",
    description=(
        "Бэкенд веб-приложения для планирования путешествий. "
        "Чтобы попробовать защищённые методы: зарегистрируйтесь или войдите, "
        "скопируйте access_token и нажмите кнопку Authorize."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(app)

API_PREFIX = "/api/v1"
for module in (auth, trips, places, geo):
    app.include_router(module.router, prefix=API_PREFIX)


@app.get("/health", tags=["Служебное"], summary="Проверка, что сервер жив")
def health():
    return {"status": "ok"}
