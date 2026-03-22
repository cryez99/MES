import pulp
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from .models import Order, Workplace, Operation, ProductionPlan, Assignment, EmergencyStop
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class MESOptimizer:
    def __init__(self, orders: List[Order], workplaces: List[Workplace],
                 operations: List[Operation], planning_horizon: int = 7,
                 investment_limit: float = 1e6,
                 emergency_stops: List[EmergencyStop] = None,
                 order_prices: Optional[Dict[str, float]] = None):
        self.orders = orders
        self.workplaces = workplaces
        self.operations = operations
        self.T = planning_horizon
        self.investment_limit = investment_limit
        self.emergency_stops = emergency_stops or []
        self.order_prices = order_prices or {}

        self.order_ids = [o.id for o in orders]
        self.workplace_ids = [w.id for w in workplaces]
        self.operation_ids = [op.operation_id for op in operations]

        self.order_by_id = {o.id: o for o in orders}
        self.workplace_by_id = {w.id: w for w in workplaces}
        self.operation_by_id = {op.operation_id: op for op in operations}

        self.processing_time = self._compute_processing_times()

        self.revenue = self._compute_revenue()

        self.setup_cost = self._compute_setup_costs()

        self.availability = self._compute_availability()

        self.work_type_to_workplaces = self._build_work_type_mapping()

        self.changeover_costs = {wp.id: 0.0 for wp in workplaces}

    def set_changeover_costs(self, costs: Dict[str, float]) -> None:
        for wp_id, cost in costs.items():
            if wp_id in self.workplace_by_id:
                self.changeover_costs[wp_id] = cost

    def set_order_prices(self, prices: Dict[str, float]) -> None:
        for order_id, revenue in prices.items():
            if order_id in self.order_by_id:
                self.order_prices[order_id] = revenue
        self.revenue = self._compute_revenue()

    def _build_work_type_mapping(self) -> Dict[str, List[str]]:
        from collections import defaultdict
        mapping = defaultdict(set)
        for op in self.operations:
            if op.work_type and op.workplace_id:
                mapping[op.work_type].add(op.workplace_id)
        return {wt: list(wp_set) for wt, wp_set in mapping.items()}

    def get_alternative_workplaces(self, operation: Operation) -> List[str]:
        if not operation.work_type:
            return [operation.workplace_id] if operation.workplace_id else []
        alternatives = self.work_type_to_workplaces.get(operation.work_type, [])
        if operation.workplace_id and operation.workplace_id not in alternatives:
            alternatives.append(operation.workplace_id)
        return alternatives

    def _compute_processing_times(self) -> Dict[Tuple[str, str], float]:
        times = {}
        for op in self.operations:
            for wp in self.workplaces:
                key = (op.operation_id, wp.id)
                if op.workplace_id and op.workplace_id != wp.id:
                    times[key] = 1e9
                    continue
                hours = op.planned_labor / 60.0 if op.planned_labor else 0.0
                times[key] = hours
        return times

    def _compute_revenue(self) -> Dict[str, float]:
        revenue = {}
        for order in self.orders:
            if order.id in self.order_prices:
                revenue[order.id] = self.order_prices[order.id]
            else:
                revenue[order.id] = order.quantity * 1000
        return revenue

    def _compute_setup_costs(self) -> Dict[Tuple[str, str], float]:
        return {}

    def _compute_availability(self) -> Dict[Tuple[str, int], float]:
        from datetime import datetime, timedelta
        base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        availability = {}
        for wp in self.workplaces:
            daily_capacity = wp.capacity_per_day
            for i in range(self.T):
                period_start = base_date + timedelta(days=i)
                period_end = period_start + timedelta(days=1)
                is_unavailable = False
                for stop in self.emergency_stops:
                    if stop.workplace_id != wp.id:
                        continue
                    if not (stop.end_time < period_start or stop.start_time >= period_end):
                        is_unavailable = True
                        break
                capacity = 0.0 if is_unavailable else daily_capacity
                availability[(wp.id, i)] = capacity
        return availability

    def optimize(self) -> ProductionPlan:
        logger.info("Запуск оптимизации по максимизации прибыли...")
        from collections import defaultdict
        import datetime as dt

        base_date = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        horizon_end = base_date + dt.timedelta(days=self.T)

        calendar = defaultdict(list)  

        for stop in self.emergency_stops:
            calendar[stop.workplace_id].append((stop.start_time, stop.end_time))

        order_ops = defaultdict(list)
        for op in self.operations:
            order_ops[op.order_id].append(op)

        order_info = {}
        for order_id, ops in order_ops.items():
            total_hours = sum(op.planned_labor / 60.0 for op in ops if op.planned_labor)
            revenue = self.revenue.get(order_id, 0.0)
            density = revenue / total_hours if total_hours > 0 else 0.0
            from collections import defaultdict
            workplace_hours = defaultdict(float)
            for op in ops:
                if op.workplace_id:
                    workplace_hours[op.workplace_id] += op.planned_labor / 60.0
            dominant = max(workplace_hours.items(), key=lambda x: x[1])[0] if workplace_hours else ''
            order_info[order_id] = {
                'ops': ops,
                'total_hours': total_hours,
                'revenue': revenue,
                'density': density,
                'dominant': dominant,
            }

        sorted_order_ids = sorted(
            order_info.keys(),
            key=lambda oid: (-order_info[oid]['density'], order_info[oid]['dominant'])
        )

        order_last_end = {}
        order_start_date = {}
        for order in self.orders:
            if order.start_date:
                order_start_date[order.id] = order.start_date.replace(hour=0, minute=0, second=0)
            else:
                order_start_date[order.id] = base_date

        assignments = []
        accepted_order_ids = []

        for order_id in sorted_order_ids:
            info = order_info[order_id]
            ops = info['ops']
            def get_counter(op):
                try:
                    return int(op.counter) if op.counter else 0
                except ValueError:
                    return op.counter if op.counter else ''
            ops_sorted = sorted(ops, key=get_counter)

            order_accepted = True
            order_assignments = []
            temp_calendar = {wp_id: list(calendar.get(wp_id, [])) for wp_id in self.workplace_ids}

            for op in ops_sorted:
                workplace_id = op.workplace_id
                if not workplace_id:
                    alternatives = self.get_alternative_workplaces(op)
                    if not alternatives:
                        order_accepted = False
                        break
                    workplace_id = alternatives[0]

                wp = self.workplace_by_id.get(workplace_id)
                if not wp:
                    order_accepted = False
                    break

                start_sec = wp.start_time
                end_sec = wp.end_time
                pause_sec = wp.break_time

                duration_hours = op.planned_labor / 60.0 if op.planned_labor else 0.0
                if duration_hours <= 0:
                    duration_hours = 0.1
                duration = dt.timedelta(hours=duration_hours)

                order_start = order_start_date.get(order_id, base_date)
                earliest_start = max(order_start, order_last_end.get(order_id, order_start))

                busy_intervals = sorted(temp_calendar.get(workplace_id, []))
                def generate_available_intervals(start_dt, end_dt):
                    current_date = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    while current_date < end_dt:
                        day_start = current_date + dt.timedelta(seconds=wp.start_time)
                        day_end = current_date + dt.timedelta(seconds=wp.end_time)
                        if pause_sec > 0:
                            pause_start = day_end - dt.timedelta(seconds=pause_sec)
                            if day_start < pause_start:
                                yield (max(day_start, start_dt), min(pause_start, end_dt))
                            after_pause = pause_start + dt.timedelta(seconds=pause_sec)
                            if after_pause < day_end:
                                yield (max(after_pause, start_dt), min(day_end, end_dt))
                        else:
                            yield (max(day_start, start_dt), min(day_end, end_dt))
                        current_date += dt.timedelta(days=1)
                search_start = earliest_start
                search_end = horizon_end
                found = False
                candidate_start = None
                day_offset = None

                for day_offset in range(self.T):
                    current_date = earliest_start.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=day_offset)
                    if current_date >= horizon_end:
                        break
                    day_start = current_date + dt.timedelta(seconds=wp.start_time)
                    day_end = current_date + dt.timedelta(seconds=wp.end_time)
                    if pause_sec > 0:
                        pause_start = day_end - dt.timedelta(seconds=pause_sec)
                        working_intervals = [(day_start, pause_start),
                                             (pause_start + dt.timedelta(seconds=pause_sec), day_end)]
                    else:
                        working_intervals = [(day_start, day_end)]

                    for interval_start, interval_end in working_intervals:
                        if interval_end <= search_start:
                            continue
                        interval_start = max(interval_start, search_start)
                        interval_end = min(interval_end, search_end)
                        if interval_start >= interval_end:
                            continue
                        relevant_busy = [(bs, be) for bs, be in busy_intervals
                                         if be > interval_start and bs < interval_end]
                        relevant_busy.sort(key=lambda x: x[0])
                        current = interval_start
                        for bs, be in relevant_busy:
                            if bs > current:
                                gap_start = current
                                gap_end = bs
                                if gap_end - gap_start >= duration:
                                    candidate_start = gap_start
                                    found = True
                                    break
                            current = max(current, be)
                            if current >= interval_end:
                                break
                        if found:
                            break
                        if current < interval_end and interval_end - current >= duration:
                            candidate_start = current
                            found = True
                            break
                    if found:
                        break

                if not found:
                    last_busy_end = earliest_start
                    if busy_intervals:
                        last_busy_end = max(be for _, be in busy_intervals)
                    candidate_start = max(last_busy_end, earliest_start)
                    if candidate_start + duration <= horizon_end:
                        found = True
                        day_offset = (candidate_start.date() - earliest_start.date()).days
                        logger.debug(f"Резервный слот для операции {op.operation_id} в {candidate_start} (вне рабочих часов)")
                    else:
                        logger.debug(f"Операция {op.operation_id} на рабочем месте {workplace_id} не может быть запланирована в пределах горизонта (earliest_start={earliest_start}, horizon_end={horizon_end})")
                        order_accepted = False
                        break

                labor_hours = duration_hours
                assignment = Assignment(
                    order_id=op.order_id if hasattr(op, 'order_id') else '',
                    operation_id=op.operation_id,
                    workplace_id=workplace_id,
                    period=day_offset,
                    start_time=candidate_start,
                    end_time=candidate_start + duration,
                    quantity_produced=op.quantity if hasattr(op, 'quantity') else 0.0,
                    labor_hours=labor_hours,
                    setup_cost=0.0
                )
                order_assignments.append(assignment)
                temp_calendar[workplace_id].append((candidate_start, candidate_start + duration))
                order_last_end[order_id] = candidate_start + duration

            if order_accepted:
                assignments.extend(order_assignments)
                for wp_id, intervals in temp_calendar.items():
                    existing = calendar[wp_id]
                    for iv in intervals:
                        if iv not in existing:
                            existing.append(iv)
                accepted_order_ids.append(order_id)
                logger.info(f"Заказ {order_id} принят, выручка {info['revenue']:.2f}")
            else:
                logger.info(f"Заказ {order_id} отклонен (не может быть запланирован в пределах горизонта)")

        total_revenue = sum(order_info[oid]['revenue'] for oid in accepted_order_ids)

        total_changeover_cost = 0.0
        for wp_id, cost_per_switch in self.changeover_costs.items():
            if cost_per_switch == 0:
                continue
            wp_assignments = [a for a in assignments if a.workplace_id == wp_id]
            wp_assignments.sort(key=lambda a: a.start_time)
            switches = 0
            prev_order_id = None
            for a in wp_assignments:
                if prev_order_id is not None and a.order_id != prev_order_id:
                    switches += 1
                prev_order_id = a.order_id
            total_changeover_cost += switches * cost_per_switch

        total_profit = total_revenue - total_changeover_cost
        total_setup_cost = 0.0

        plan = ProductionPlan(
            assignments=assignments,
            total_profit=total_profit,
            total_setup_cost=total_setup_cost
        )
        logger.info(
            f"Оптимизация прибыли завершена: принято {len(accepted_order_ids)} заказов, "
            f"{len(assignments)} назначений, общая прибыль = {total_profit:.2f}, "
            f"стоимость переналадки = {total_changeover_cost:.2f}"
        )
        return plan

    def optimize_makespan(self) -> ProductionPlan:
        logger.info("Запуск оптимизации по минимизации времени выполнения...")

        base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        from collections import defaultdict
        calendar = defaultdict(list)

        for stop in self.emergency_stops:
            calendar[stop.workplace_id].append((stop.start_time, stop.end_time))

        from collections import defaultdict
        order_ops = defaultdict(list)
        for op in self.operations:
            order_ops[op.order_id].append(op)
        
        order_priority = []
        for order_id, ops in order_ops.items():
            order = self.order_by_id.get(order_id)
            due_date = order.end_date if order and order.end_date else datetime.max
            start_date = order.start_date if order and order.start_date else datetime.min
            total_labor = sum(op.planned_labor for op in ops if op.planned_labor)
            order_priority.append((order_id, due_date, start_date, total_labor, ops))
        
        order_priority.sort(key=lambda x: (-x[3], x[2]))
        
        op_list = []
        for order_id, due_date, start_date, total_labor, ops in order_priority:
            def get_counter(op):
                try:
                    return int(op.counter) if op.counter else 0
                except ValueError:
                    return op.counter if op.counter else ''
            ops_sorted = sorted(ops, key=get_counter)
            op_list.extend(ops_sorted)

        order_last_end = {}
        order_start_date = {}
        for order in self.orders:
            if order.start_date:
                order_start_date[order.id] = order.start_date.replace(hour=0, minute=0, second=0)
            else:
                order_start_date[order.id] = base_date

        assignments = []
        makespan = base_date

        for op in op_list:
            workplace_id = op.workplace_id
            if not workplace_id:
                alternatives = self.get_alternative_workplaces(op)
                if not alternatives:
                    logger.warning(f"Операция {op.operation_id} не имеет рабочего места, пропускаем")
                    continue
                workplace_id = alternatives[0]

            wp = self.workplace_by_id.get(workplace_id)
            if not wp:
                logger.warning(f"Рабочее место {workplace_id} не найдено, пропускаем")
                continue

            duration_hours = op.planned_labor / 60.0 if op.planned_labor else 0.0
            if duration_hours <= 0:
                duration_hours = 0.1
            duration = timedelta(hours=duration_hours)

            order_id = op.order_id
            order_start = order_start_date.get(order_id, base_date)
            earliest_start = max(order_start, order_last_end.get(order_id, order_start))

            max_days = 60
            found = False
            assigned_workplace_id = None
            candidate_start = None
            day_offset = None

            start_date_midnight = earliest_start.replace(hour=0, minute=0, second=0, microsecond=0)

            start_sec = wp.start_time
            end_sec = wp.end_time
            pause_sec = wp.break_time
            work_day_length = end_sec - start_sec - pause_sec
            if work_day_length <= 0:
                work_day_length = 8 * 3600

            for day_offset in range(max_days):
                current_date = start_date_midnight + timedelta(days=day_offset)
                day_start = current_date + timedelta(seconds=start_sec)
                day_end = current_date + timedelta(seconds=end_sec)
                if pause_sec > 0:
                    pause_start = day_end - timedelta(seconds=pause_sec)
                    available_periods = [(day_start, pause_start),
                                         (pause_start + timedelta(seconds=pause_sec), day_end)]
                else:
                    available_periods = [(day_start, day_end)]

                for period_start, period_end in available_periods:
                    candidate_start = period_start
                    for busy_start, busy_end in sorted(calendar[workplace_id]):
                        if busy_end <= candidate_start:
                            continue
                        if busy_start >= candidate_start + duration:
                            break
                        candidate_start = max(candidate_start, busy_end)
                    candidate_start = max(candidate_start, earliest_start)
                    if candidate_start + duration <= period_end:
                        assigned_workplace_id = workplace_id
                        found = True
                        break
                if found:
                    break

            if found:
                labor_hours = duration_hours
                assignment = Assignment(
                    order_id=op.order_id if hasattr(op, 'order_id') else '',
                    operation_id=op.operation_id,
                    workplace_id=assigned_workplace_id,
                    period=day_offset,  
                    start_time=candidate_start,
                    end_time=candidate_start + duration,
                    quantity_produced=op.quantity if hasattr(op, 'quantity') else 0.0,
                    labor_hours=labor_hours,
                    setup_cost=0.0
                )
                assignments.append(assignment)
                calendar[assigned_workplace_id].append((candidate_start, candidate_start + duration))
                order_last_end[order_id] = candidate_start + duration
                if candidate_start + duration > makespan:
                    makespan = candidate_start + duration
            else:
                alternatives = self.get_alternative_workplaces(op)
                primary_workplace_id = op.workplace_id
                if not primary_workplace_id and alternatives:
                    primary_workplace_id = alternatives[0]
                if not primary_workplace_id:
                    logger.warning(f"Операция {op.operation_id} не может быть размещена, пропускаем")
                    continue
                wp = self.workplace_by_id.get(primary_workplace_id)
                if wp:
                    start_sec = wp.start_time
                    end_sec = wp.end_time
                    pause_sec = wp.break_time
                else:
                    start_sec = 28800
                    end_sec = 61200
                    pause_sec = 3600
                last_end = base_date
                if calendar[primary_workplace_id]:
                    last_end = max(end for _, end in calendar[primary_workplace_id])
                else:
                    day_midnight = earliest_start.replace(hour=0, minute=0, second=0, microsecond=0)
                    day_start = day_midnight + timedelta(seconds=start_sec)
                    last_end = max(day_start, earliest_start)
                last_end = max(last_end, earliest_start)
                labor_hours = duration_hours
                assignment = Assignment(
                    order_id=op.order_id if hasattr(op, 'order_id') else '',
                    operation_id=op.operation_id,
                    workplace_id=primary_workplace_id,
                    period=int((last_end - base_date).days),
                    start_time=last_end,
                    end_time=last_end + duration,
                    quantity_produced=op.quantity if hasattr(op, 'quantity') else 0.0,
                    labor_hours=labor_hours,
                    setup_cost=0.0
                )
                assignments.append(assignment)
                calendar[primary_workplace_id].append((last_end, last_end + duration))
                order_last_end[order_id] = last_end + duration
                if last_end + duration > makespan:
                    makespan = last_end + duration
                logger.warning(f"Не найден слот для операции {op.operation_id} на любом рабочем месте, размещена в {last_end} на {primary_workplace_id}")

        total_profit = 0.0
        total_setup_cost = 0.0

        plan = ProductionPlan(
            assignments=assignments,
            total_profit=total_profit,
            total_setup_cost=total_setup_cost
        )
        logger.info(f"Оптимизация времени выполнения завершена: {len(assignments)} назначений, общее время = {makespan}")
        return plan

    def _resolve_overlaps(self, assignments: List[Assignment]) -> List[Assignment]:
        from collections import defaultdict
        groups = defaultdict(list)
        for a in assignments:
            groups[(a.workplace_id, a.period)].append(a)

        resolved = []
        for (wp_id, period), group in groups.items():
            group.sort(key=lambda x: x.start_time)
            wp = self.workplace_by_id.get(wp_id)
            if not wp:
                wp_start_seconds = 8 * 3600 
                wp_end_seconds = 17 * 3600  
            else:
                wp_start_seconds = wp.start_time
                wp_end_seconds = wp.end_time
            base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            period_date = base_date + timedelta(days=period)
            work_start = period_date + timedelta(seconds=wp_start_seconds)
            work_end = period_date + timedelta(seconds=wp_end_seconds)
            current_time = work_start
            for a in group:
                duration = a.end_time - a.start_time
                a.start_time = current_time
                a.end_time = current_time + duration
                current_time = a.end_time
                resolved.append(a)
        return resolved

    def export_to_dataframe(self, plan: ProductionPlan) -> pd.DataFrame:
        rows = []
        for a in plan.assignments:
            rows.append({
                'order': a.order_id,
                'operation': a.operation_id,
                'workplace': a.workplace_id,
                'period': a.period,
                'start': a.start_time,
                'end': a.end_time,
                'quantity': a.quantity_produced,
                'setup_cost': a.setup_cost
            })
        return pd.DataFrame(rows)


def create_optimizer_from_dataframes(orders_df: pd.DataFrame,
                                     resources_df: pd.DataFrame,
                                     processing_df: pd.DataFrame,
                                     emergency_stops: List[EmergencyStop] = None,
                                     order_prices: Optional[Dict[str, float]] = None,
                                     planning_horizon: int = 7) -> MESOptimizer:
    orders = []
    for _, row in orders_df.iterrows():
        order = Order(
            id=str(row.get('order_id', '')),
            material_code=str(row.get('product_code', '')),
            quantity=float(row.get('order_qty', 0)),
            start_date=pd.to_datetime(row.get('start_date'), errors='coerce'),
            end_date=pd.to_datetime(row.get('end_date'), errors='coerce'),
            status='',
            tech_card=None
        )
        orders.append(order)

    workplaces = []
    for _, row in resources_df.iterrows():
        start = int(row.get('BEGZT', 28800))
        end = int(row.get('ENDZT', 61200))
        pause = int(row.get('PAUSE', 3600))
        available_seconds = max(0, end - start - pause)
        capacity_hours = available_seconds / 3600.0
        utilization = float(row.get('NGRAD', 100)) / 100.0
        wp = Workplace(
            id=str(row.get('ARBID', '')),
            code=str(row.get('workplace_code', '')),
            name='', 
            capacity_per_day=capacity_hours * utilization,
            start_time=start,
            end_time=end,
            break_time=pause,
            utilization=utilization
        )
        workplaces.append(wp)

    operations = []
    for _, row in processing_df.iterrows():
        op = Operation(
            tech_card=str(row.get('tech_card', '')),
            counter=str(row.get('counter', '')),  
            operation_id=str(row.get('operation', '')),
            description='', 
            workplace_id=str(row.get('ARBID', '')),
            work_type=str(row.get('work_type_code', '')),
            norm_time=0.0,
            norm_unit='',
            quantity=float(row.get('order_qty', 0.0)), 
            confirmed_quantity=0.0,
            planned_labor=float(row.get('planned_labor', 0)),
            actual_labor=float(row.get('actual_labor', 0)),
            order_id=str(row.get('order_id', '')) 
        )
        operations.append(op)

    return MESOptimizer(orders, workplaces, operations,
                        planning_horizon=planning_horizon,
                        emergency_stops=emergency_stops,
                        order_prices=order_prices)