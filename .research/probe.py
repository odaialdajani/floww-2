import fastapi
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient
r = APIRouter()
@r.get('/api/thing/{t}')
def thing(t: str): return {'t': t}
app = FastAPI()
app.include_router(r)
paths = sorted({x.path for x in app.routes if hasattr(x,"path")})
flat = '/api/thing/{t}' in paths
with TestClient(app) as c:
    code = c.get('/api/thing/x').status_code
import starlette
print(f"fastapi={fastapi.__version__} starlette={starlette.__version__} include_router_flattens_into_app.routes={flat} request_status={code}")
