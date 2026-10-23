"""Simple, host-free builder registry for optional future RC modules."""
from __future__ import annotations
from typing import Any
from .contracts import RCBuilder,RCElementKind,RCModelPlan


class RCModuleRegistry:
    def __init__(self):
        self._builders: dict[RCElementKind,RCBuilder]={}

    def register(self,kind:RCElementKind,builder:RCBuilder) -> None:
        if kind in self._builders:
            raise ValueError(f'{kind.value} builder registered twice')
        self._builders[kind]=builder

    def build(self,kind:RCElementKind,parameters:Any) -> RCModelPlan:
        if kind not in self._builders:
            raise KeyError(f'No registered {kind.value} builder')
        result=self._builders[kind].build(parameters)
        if result.element_kind!=kind:
            raise ValueError('Module builder returned incorrect element kind')
        return result

    def available(self) -> tuple[RCElementKind,...]:
        return tuple(self._builders)
