from fastapi import Request, UploadFile, Form, File
from typing import Optional

from app.models.request import SliceRequest


async def ingest_file(
    request: Request,
    file: Optional[UploadFile] = File(None),
    file_url: Optional[str] = Form(None),
) -> tuple[bytes, str]:
    """Extract STL file content from upload or URL. Returns (content, filename)."""
    if file is not None and file.filename:
        content = await file.read()
        return content, file.filename

    if file_url is not None:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            resp.raise_for_status()
            filename = file_url.split("/")[-1] or "model.stl"
            return resp.content, filename

    raise ValueError("Either 'file' or 'file_url' must be provided")
