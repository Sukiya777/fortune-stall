"""问心处 · 独立启动壳 fortune-stall

用法:  python server.py        (默认 127.0.0.1:3900, 无鉴权)
环境:  HOST / PORT / FORTUNE_TOKEN(设了就要求 Bearer) / PERSONA / SKILLS_DIR / FORTUNE_DB
放公网前请自行加一层认证(反代 Basic Auth / Cloudflare Access), 或设 FORTUNE_TOKEN。
"""
import os
import re
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

import fortune

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
TOKEN = os.environ.get("FORTUNE_TOKEN", "").strip()

app = FastAPI(title="问心处 fortune-stall", docs_url=None, redoc_url=None)


def require_auth(authorization: str = Header(default="")) -> None:
    if not TOKEN:
        return
    if authorization.removeprefix("Bearer ").strip() != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "fortune.html",
                        headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/static/tarot/{fname}", include_in_schema=False)
async def tarot_img(fname: str) -> FileResponse:
    if not re.fullmatch(r"[a-z]+[0-9]{2}\.webp", fname):
        raise HTTPException(status_code=404)
    root = (STATIC / "tarot").resolve()
    p = (root / fname).resolve()
    if p.parent != root or not p.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(p, media_type="image/webp",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}


fortune.register(app, require_auth)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "3900")))
