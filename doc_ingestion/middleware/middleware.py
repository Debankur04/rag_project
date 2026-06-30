import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.api_key = os.getenv("JAVA_BACKEND_API_KEY")

    async def dispatch(self, request: Request, call_next):
        # Allow Swagger + health routes
        if request.url.path in [
            "/", 
            "/health", 
            "/docs", 
            "/openapi.json", 
            "/docs/oauth2-redirect"
        ]:
            return await call_next(request)

        if not self.api_key:
            return JSONResponse(
                status_code=500,
                content={"detail": "API Key not configured on server"}
            )

        api_key_header = request.headers.get("X-API-KEY")
        if not api_key_header or api_key_header != self.api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API Key"}
            )
        
        return await call_next(request)