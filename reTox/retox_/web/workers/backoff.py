import random


class ExponentialBackoff:
    def __init__(
        self,
        base_delay_s: float = 1.0,
        factor: float = 2.0,
        max_delay_s: float = 60.0,
        jitter: float = 0.15,
    ):
        self.base = max(0.0, float(base_delay_s))
        self.factor = max(1.0, float(factor))
        self.max = max(0.0, float(max_delay_s))
        self.jitter = max(0.0, float(jitter))
        self.attempt = 0

    def reset(self) -> None:
        self.attempt = 0

    def next_delay(self) -> float:
        delay = min(self.max, self.base * (self.factor ** self.attempt))
        self.attempt += 1
        if delay <= 0:
            return 0.0
        j = delay * self.jitter
        return max(0.0, delay + random.uniform(-j, j))