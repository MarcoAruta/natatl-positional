"""Standalone positional-search model checker for memoryless NatATL."""
from .checker import Checker, check, verify_strategy
from .errors import ModelError, FormulaError, InadmissibleStrategy, ResourceLimit
from .limits import Limits
from .model import Game
from .pos2nat import pos2nat, reachability_layers
from .strategy import NaturalStrategy, Rule, left_write, import_profile, export_profile

__version__ = "0.1.0"


def model_checking(formula, model_path, *, return_all_states=True, **options):
    """Formula-first convenience entry point; returns this project's JSON schema."""
    return check(model_path, formula, all_states=return_all_states, **options)


__all__ = ["Checker", "Game", "Limits", "check", "model_checking", "verify_strategy",
           "pos2nat", "reachability_layers", "left_write", "NaturalStrategy", "Rule",
           "import_profile", "export_profile", "ModelError", "FormulaError",
           "InadmissibleStrategy", "ResourceLimit"]
