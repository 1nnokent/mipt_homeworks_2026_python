import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar
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


def is_positive_number(value: int) -> bool:
    return type(value) is int and value > 0


def validate_breaker_args(critical_count: int, time_to_recover: int) -> None:
    errors = []

    if not is_positive_number(critical_count):
        errors.append(ValueError(INVALID_CRITICAL_COUNT))

    if not is_positive_number(time_to_recover):
        errors.append(ValueError(INVALID_RECOVERY_TIME))

    if errors:
        raise ExceptionGroup(VALIDATIONS_FAILED, errors)


@dataclass
class BreakerState:
    failed_calls: int = 0
    blocked_at: datetime | None = None


class CircuitBreaker:
    def __init__(
        self,
        critical_count: int = 5,
        time_to_recover: int = 30,
        triggers_on: type[Exception] = Exception,
    ):
        validate_breaker_args(critical_count, time_to_recover)
        self.critical_count: int = critical_count
        self.time_to_recover: int = time_to_recover
        self.triggers_on: type[Exception] = triggers_on

    def __call__(self, func: CallableWithMeta[P, R_co]) -> Callable[P, R_co]:
        state = BreakerState()

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R_co:
            self._check_block(func, state)

            try:
                result = func(*args, **kwargs)
            except Exception as error:
                self._save_error(func, state, error)
                raise

            state.failed_calls = 0
            state.blocked_at = None
            return result

        return wrapper

    def _check_block(self, func: CallableWithMeta[P, R_co], state: BreakerState) -> None:
        if state.blocked_at is None:
            return

        now = datetime.now(UTC).replace(microsecond=0)
        seconds_from_block = (now - state.blocked_at).total_seconds()
        if seconds_from_block < self.time_to_recover:
            raise BreakerError(self._func_name(func), state.blocked_at)

        state.failed_calls = 0
        state.blocked_at = None

    def _save_error(
        self,
        func: CallableWithMeta[P, R_co],
        state: BreakerState,
        error: Exception,
    ) -> None:
        if not isinstance(error, self.triggers_on):
            return

        state.failed_calls += 1
        if state.failed_calls < self.critical_count:
            return

        state.blocked_at = datetime.now(UTC).replace(microsecond=0)
        raise BreakerError(self._func_name(func), state.blocked_at) from error

    def _func_name(self, func: CallableWithMeta[P, R_co]) -> str:
        return f"{func.__module__}.{func.__name__}"


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
