"""HTML pages: upload form and result."""

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

from app.api.templating import templates
from app.config import get_settings
from app.pipeline.orchestrator import analyze
from app.pipeline.validate import ValidationError, validate_upload

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"settings": get_settings()})


@router.post("/check", response_class=HTMLResponse)
async def check(request: Request, file: UploadFile = File(...)):
    settings = get_settings()
    # Read at most limit+1 bytes so huge uploads are refused cheaply.
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        vf = validate_upload(data, file.filename or "", settings)
    except ValidationError as exc:
        return templates.TemplateResponse(request, "_error.html", {"message": str(exc)}, status_code=400)
    # Model inference is slow and blocking: run it off the event loop.
    result = await run_in_threadpool(analyze, vf, settings)
    return templates.TemplateResponse(request, "_result.html", {"r": result, "settings": settings})
