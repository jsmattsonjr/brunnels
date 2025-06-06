import typing
from typing import Callable, List
from .brunnel import FilterReason
# from .brunnel_way import BrunnelWay # Moved under TYPE_CHECKING

if typing.TYPE_CHECKING:
    from .brunnel_way import BrunnelWay

class FilterPipeline:
    def __init__(self):
        self.filters = []

    def add_filter(self, filter_func: Callable[['BrunnelWay'], FilterReason]):
        self.filters.append(filter_func)
        return self

    def apply(self, brunnels: List['BrunnelWay']) -> List['BrunnelWay']:
        for brunnel in brunnels:
            for filter_func in self.filters:
                reason = filter_func(brunnel)
                if reason != FilterReason.NONE:
                    brunnel.filter_reason = reason
                    break
        return brunnels
