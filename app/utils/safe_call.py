from functools import wraps
from app.config import logger

def safe_call(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            if isinstance(result, dict):
                return {"estado": "ok", **result}
            return {"estado": "ok", "resultado": result}
        except Exception as e:
            logger.error(f"Error en {func.__name__}: {e}")
            return {"estado": "error", "detalle": str(e)}
    return wrapper