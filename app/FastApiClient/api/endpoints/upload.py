# app/FastApiClient/api/endpoints/upload.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from FastApiClient.dependencies import get_current_user
from FastApiClient.grpc_clients.attachment import AttachmentGrpcClient
from FastApiClient.models import Users as User

router = APIRouter(prefix="/upload", tags=["Upload"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    try:
        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File too large, max 5MB",
            )

        client = AttachmentGrpcClient()
        try:
            # ВАЖНО: позиционные аргументы
            response = client.upload_attachment(
                file.filename,
                file.content_type or "application/octet-stream",
                contents,
                token,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        return {"attachment_id": response.attachment_id}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))