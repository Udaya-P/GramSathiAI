from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routes import auth, meetings

app = FastAPI(title="GramSathi AI", version="0.1.0",
              description="Manual, evidence-linked Gram Sabha minutes. Verification is prototype user confirmation, not government approval.")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                   allow_credentials=True, allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Authorization", "Content-Type"])
app.include_router(auth.router)
app.include_router(meetings.router)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "GramSathi AI", "version": "0.1.0"}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    # Do not echo submitted passwords or tokens in validation responses.
    errors = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
              for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})
