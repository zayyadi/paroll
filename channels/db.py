from functools import wraps


async def aclose_old_connections():
    return None


def database_sync_to_async(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper
