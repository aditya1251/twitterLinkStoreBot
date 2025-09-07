# utils/redis_client.py
import os
import redis

_redis = None

def get_redis():
    """
    Return a process-wide Redis client (decode_responses=True).
    Reads REDIS_HOST/REDIS_PORT/REDIS_DB from env if present.
    """
    global _redis
    if _redis is None:
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db   = int(os.getenv("REDIS_DB", "0"))
        # sensible defaults for network hiccups in VPS/multiprocess setups
        _redis = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_timeout=3,
            socket_connect_timeout=3,
            health_check_interval=30,
            retry_on_timeout=True,
        )
    return _redis
