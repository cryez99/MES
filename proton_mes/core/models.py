from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class Order:
    id: str  # AUFNR
    material_code: str
    quantity: float
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    status: str
    tech_card: Optional[str] = None


@dataclass
class Workplace:
    id: str  # ARBID
    code: str  # ARBPL
    name: str
    capacity_per_day: float  
    start_time: int  
    end_time: int
    break_time: int
    utilization: float 


@dataclass
class Operation:
    tech_card: str  # AUFPL
    counter: str  # APLZL
    operation_id: str  # VORNR
    description: str
    workplace_id: str  # ARBID
    work_type: str  # LAR01
    norm_time: float  # VGW01
    norm_unit: str
    quantity: float  # MGVRG
    confirmed_quantity: float  # GMNGA
    planned_labor: float
    actual_labor: float
    order_id: str = ''  # AUFNR 


@dataclass
class ProductionPlan:
    assignments: List['Assignment']
    total_profit: float
    total_setup_cost: float


@dataclass
class Assignment:
    order_id: str
    operation_id: str
    workplace_id: str
    period: int  
    start_time: datetime
    end_time: datetime
    quantity_produced: float
    labor_hours: float 
    setup_cost: float = 0.0


@dataclass
class EmergencyStop:
    workplace_id: str
    start_time: datetime
    end_time: datetime
    reason: str
    impact: Optional[str] = None