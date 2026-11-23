"""Input and contract errors. Comparison results are reports, not exceptions."""


class SynthCheckError(Exception):
    """Base error. `category` is a stable machine code. `message` is for people."""

    exit_code = 2

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


class InvalidInput(SynthCheckError):
    """The bundle, contract, or path cannot be evaluated."""

    exit_code = 2
