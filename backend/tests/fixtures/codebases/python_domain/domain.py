"""电力营销系统 - 核心领域模型"""
from dataclasses import dataclass
from enum import Enum


class CustomerType(str, Enum):
    """客户类型 - 决定电价类别和业务规则"""
    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"


@dataclass
class Customer:
    """用电客户实体"""
    customer_id: str
    name: str
    customer_type: CustomerType
