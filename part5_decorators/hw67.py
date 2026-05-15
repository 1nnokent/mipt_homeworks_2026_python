import json
import re
from datetime import datetime, timedelta, timezone
from functools import wraps
import inspect
from typing import Any, ParamSpec, Protocol, TypeVar, cast
from urllib.request import urlopen

INVALID_CRITICAL_COUNT = "Breaker count must be positive integer!"
INVALID_RECOVERY_TIME = "Breaker recovery time must be positive integer!"
VALIDATIONS_FAILED = "Invalid decorator args."
TOO_MUCH = "Too much requests, just wait."

P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)


class CallableWithMeta(Protocol[P, R_co]):
    __name__: str
    __module__: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R_co: ...


class BreakerError(Exception):
    def __init__(self, func_name: str, block_time: datetime):
        super().__init__(TOO_MUCH)
        self.func_name = func_name
        self.block_time = block_time


class CircuitBreaker:
    def __init__(
        self,
        critical_count: int = 5,
        time_to_recover: int = 30,
        triggers_on: type[Exception] = Exception,
    ):
        errors = []
        if type(critical_count) is not int or critical_count <= 0:
            errors.append(ValueError(INVALID_CRITICAL_COUNT))
        if type(time_to_recover) is not int or time_to_recover <= 0:
            errors.append(ValueError(INVALID_RECOVERY_TIME))
        if errors:
            raise ExceptionGroup(VALIDATIONS_FAILED, errors)

        self.critical_count: int = critical_count
        self.time_to_recover: int = time_to_recover
        self.triggers_on: type[Exception] = triggers_on

    def __call__(self, func: CallableWithMeta[P, R_co]) -> CallableWithMeta[P, R_co]:
        failures_count = 0
        block_time: datetime | None = None

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R_co:
            nonlocal failures_count, block_time

            now = datetime.now(timezone.utc).replace(microsecond=0)
            if block_time is not None:
                if now < block_time + timedelta(seconds=self.time_to_recover):
                    raise BreakerError(f"{func.__module__}.{func.__name__}", block_time)
                failures_count = 0
                block_time = None

            try:
                res = func(*args, **kwargs)
            except Exception as error:
                if isinstance(error, self.triggers_on):
                    failures_count += 1
                    if failures_count >= self.critical_count:
                        block_time = datetime.now(timezone.utc).replace(microsecond=0)
                        raise BreakerError(
                            f"{func.__module__}.{func.__name__}",
                            block_time,
                        ) from error
                raise

            failures_count = 0
            return res

        return cast(CallableWithMeta[P, R_co], wrapper)


circuit_breaker = CircuitBreaker(5, 30, Exception)


# @circuit_breaker
def get_comments(post_id: int) -> Any:
    """
    Получает комментарии к посту

    Args:
        post_id (int): Идентификатор поста

    Returns:
        list[dict[int | str]]: Список комментариев
    """
    response = urlopen(f"https://jsonplaceholder.typicode.com/comments?postId={post_id}")
    return json.loads(response.read())


if __name__ == "__main__":
    comments = get_comments(1)
