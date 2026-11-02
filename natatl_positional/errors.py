"""Errors are not negative model-checking results."""


class ModelError(ValueError):
    pass


class FormulaError(ValueError):
    pass


class InadmissibleStrategy(ValueError):
    pass


class ResourceLimit(RuntimeError):
    """The search has not decided the requested problem."""

