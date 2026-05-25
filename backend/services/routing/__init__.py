"""Copilot 语义路由子模块。

子模块按需直接 import（如 ``from services.routing.domain_router import ...``），
避免包 ``__init__``  eager import 与 ``context_builder`` 循环依赖。
"""
