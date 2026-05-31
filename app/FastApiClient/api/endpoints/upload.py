from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from FastApiClient.dependencies import get_current_user
from FastApiClient.grpc_clients.attachment import AttachmentGrpcClient
from FastApiClient.models import User

router = APIRouter(prefix="/upload", tags=["Upload"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    try:
        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large (max 5MB)")

        client = AttachmentGrpcClient()
        try:
            response = client.upload_attachment(
                file_name=file.filename,
                mime_type=file.content_type or "application/octet-stream",
                file_data=contents,
                access_token=token
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    return {"attachment_id": response.attachment_id}