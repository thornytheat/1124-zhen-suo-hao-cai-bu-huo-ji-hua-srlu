"""残差区间。"""
from .service import evaluate

__all__ = ["evaluate"]

from .weekly_replay import replay_weekly_backtest
__all__ += ["replay_weekly_backtest"]
