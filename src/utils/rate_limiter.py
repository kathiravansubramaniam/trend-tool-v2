import logging
from tenacity import (
    retry,
    wait_random_exponential,
    stop_after_attempt,
    retry_if_exception_type,
    before_sleep_log,
)
from openai import RateLimitError, APITimeoutError, APIConnectionError

logger = logging.getLogger(__name__)


def retry_with_backoff(func):
    return retry(
        wait=wait_random_exponential(min=1, max=60),
        stop=stop_after_attempt(6),
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )(func)
