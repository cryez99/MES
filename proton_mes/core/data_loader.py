import pandas as pd
import os
from typing import Dict, Optional, Tuple, List
import logging
from core.models import ProductionPlan, Assignment
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MissingFilesError(Exception):
    def __init__(self, missing_files, missing_details=None):
        self.missing_files = missing_files  
        self.missing_details = missing_details 
        super().__init__(f"Отсутствуют файлы: {', '.join(missing_files)}")


class DataLoader:

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.dfs: Dict[str, pd.DataFrame] = {}

    FILE_SPECS = {
        'orders': {
            'filename': 'заказы дебл.XLSX',
            'required_columns': ['Заказ AUFNR', 'Код изделия', 'Количество заказа (GMEIN)',
                                 'СрокНачала/Базис', 'БазисСрокКонца', 'ПользовСтатус'],
            'required': True
        },
        'order_tech': {
            'filename': 'AFKO_рр заказы номера техкарт.XLSX',
            'required_columns': ['Заказ AUFNR', '№ техкарты/операции  AUFPL'],
            'required': True
        },
        'operations': {
            'filename': 'AFVC_данные к операции_айди рабочего места, вид ра.XLSX',
            'required_columns': ['№ техкарты/операции AUFPL', 'Счетчик APLZL', 'Операция VORNR',
                                 'Краткий текст к операции LTXA1', 'Управляющий ключ STEUS',
                                 'Ид. Объекта ARBID', 'Вид работ LAR01'],
            'required': False
        },
        'norms': {
            'filename': 'AFVV_данные от техкарт по структуре операции Колич.XLSX',
            'required_columns': ['№ техкарты/операции AUFPL', 'Счетчик APLZL',
                                 'Заданное значение VGW01', 'ЕдинИзмеренЗаданЗнач VGE03',
                                 'Заданное значение VGW04', 'Заданное значение VGW05',
                                 'Количество операции MGVRG', 'ПодтверждВыхПрод GMNGA'],
            'required': False
        },
        'workplaces': {
            'filename': 'CRHD_V1_рабочее место номер и название краткое.XLSX',
            'required_columns': ['Ид. объекта', 'Рабочее место ARBPL', 'Краткое название KTEXT'],
            'required': False
        },
        'work_types': {
            'filename': 'CSLT_виды работ_текст.XLSX',
            'required_columns': ['Вид работ LSTAR', 'Название KTEXT'],
            'required': False
        },
        'capacities': {
            'filename': 'KAKO_мощность.XLSX',
            'required_columns': ['Ид. мощности', 'Время начала BEGZT', 'Время конца ENDZT',
                                 'Перерыв/сек. PAUSE', 'Число ОтдМощностей AZNOR', 'СтепИспользования NGRAD'],
            'required': False
        }
    }

    def load_all(self) -> Dict[str, pd.DataFrame]:
        missing_files = []
        missing_details = []
        for key, spec in self.FILE_SPECS.items():
            filename = spec['filename']
            path = os.path.join(self.data_dir, filename)
            if not os.path.exists(path):
                logger.warning(f"Файл не найден {path}")
                missing_files.append(filename)
                missing_details.append({
                    'filename': filename,
                    'required': spec['required'],
                    'required_columns': spec['required_columns']
                })
                continue
            try:
                df = pd.read_excel(path, sheet_name=0, dtype=str)
                self.dfs[key] = df
                logger.info(f"Загружен файл {filename} с {df.shape}")
            except Exception as e:
                logger.error(f"Ошибка загрузки: {filename}: {e}")
                raise
        missing_required = [spec['filename'] for key, spec in self.FILE_SPECS.items()
                            if spec['required'] and spec['filename'] in missing_files]
        if missing_required:
            raise MissingFilesError(missing_required, missing_details)
        return self.dfs

    def join_data(self) -> pd.DataFrame:
        if not self.dfs:
            self.load_all()

        orders = self.dfs.get('orders')
        order_tech = self.dfs.get('order_tech')
        if orders is None or order_tech is None:
            raise ValueError("Нет заказов или того, что с ними связано")

        orders_cols = ['Заказ AUFNR', 'Код изделия', 'Количество заказа (GMEIN)',
                       'СрокНачала/Базис', 'БазисСрокКонца', 'ПользовСтатус']
        orders = orders[orders_cols].copy()
        orders.rename(columns={'Заказ AUFNR': 'order_id'}, inplace=True)

        order_tech_cols = ['Заказ AUFNR', '№ техкарты/операции  AUFPL']
        order_tech = order_tech[order_tech_cols].copy()
        order_tech.rename(columns={'Заказ AUFNR': 'order_id',
                                   '№ техкарты/операции  AUFPL': 'tech_card'}, inplace=True)
        merged = pd.merge(orders, order_tech, on='order_id', how='left')

        ops = self.dfs.get('operations')
        if ops is not None:
            ops_cols = ['№ техкарты/операции AUFPL', 'Счетчик APLZL', 'Операция VORNR',
                        'Краткий текст к операции LTXA1', 'Управляющий ключ STEUS',
                        'Ид. Объекта ARBID', 'Вид работ LAR01']
            ops = ops[ops_cols].copy()
            ops.rename(columns={'№ техкарты/операции AUFPL': 'tech_card'}, inplace=True)
            merged = pd.merge(merged, ops, on='tech_card', how='left')

        norms = self.dfs.get('norms')
        if norms is not None:
            norms_cols = ['№ техкарты/операции AUFPL', 'Счетчик APLZL',
                          'Заданное значение VGW01', 'ЕдинИзмеренЗаданЗнач VGE03',
                          'Заданное значение VGW04', 'Заданное значение VGW05',
                          'Количество операции MGVRG', 'ПодтверждВыхПрод GMNGA']
            norms = norms[norms_cols].copy()
            norms.rename(columns={'№ техкарты/операции AUFPL': 'tech_card'}, inplace=True)
            merged = pd.merge(merged, norms, on=['tech_card', 'Счетчик APLZL'], how='left')

        workplaces = self.dfs.get('workplaces')
        if workplaces is not None:
            wp_cols = ['Ид. объекта', 'Рабочее место ARBPL', 'Краткое название KTEXT']
            workplaces = workplaces[wp_cols].copy()
            workplaces.rename(columns={'Ид. объекта': 'ARBID'}, inplace=True)
            merged = pd.merge(merged, workplaces, left_on='Ид. Объекта ARBID', right_on='ARBID', how='left')

        work_types = self.dfs.get('work_types')
        if work_types is not None:
            wt_cols = ['Вид работ LSTAR', 'Название KTEXT']
            work_types = work_types[wt_cols].copy()
            work_types.rename(columns={'Вид работ LSTAR': 'LAR01'}, inplace=True)
            merged = pd.merge(merged, work_types, left_on='Вид работ LAR01', right_on='LAR01', how='left')

        capacities = self.dfs.get('capacities')
        if capacities is not None:
            cap_cols = ['Ид. мощности', 'Время начала BEGZT', 'Время конца ENDZT',
                        'Перерыв/сек. PAUSE', 'Число ОтдМощностей AZNOR', 'СтепИспользования NGRAD']
            capacities = capacities[cap_cols].copy()
            capacities.rename(columns={'Ид. мощности': 'ARBID'}, inplace=True)
            merged = pd.merge(merged, capacities, left_on='Ид. Объекта ARBID', right_on='ARBID', how='left')

        merged = self._calculate_labor_intensity(merged)

        rename_map = {
            'Операция VORNR': 'operation',
            'Ид. Объекта ARBID': 'ARBID',
            'Рабочее место ARBPL': 'workplace_code',
            'Вид работ LAR01': 'work_type_code',
            'Краткий текст к операции LTXA1': 'operation_desc',
            'Управляющий ключ STEUS': 'control_key',
            'Код изделия': 'product_code',
            'Количество заказа (GMEIN)': 'order_qty',
            'СрокНачала/Базис': 'start_date',
            'БазисСрокКонца': 'end_date',
            'ПользовСтатус': 'status',
            'Краткое название KTEXT': 'workplace_name',
            'Название KTEXT': 'work_type_name',
            'Число ОтдМощностей AZNOR': 'AZNOR',
            'СтепИспользования NGRAD': 'NGRAD',
            'Время начала BEGZT': 'BEGZT',
            'Время конца ENDZT': 'ENDZT',
            'Перерыв/сек. PAUSE': 'PAUSE',
            'Заданное значение VGW01': 'VGW01',
            'ЕдинИзмеренЗаданЗнач VGE03': 'VGE03',
            'Заданное значение VGW04': 'VGW04',
            'Заданное значение VGW05': 'VGW05',
            'Количество операции MGVRG': 'MGVRG',
            'ПодтверждВыхПрод GMNGA': 'GMNGA',
        }
        for old, new in rename_map.items():
            if old in merged.columns:
                merged.rename(columns={old: new}, inplace=True)

        logger.info(f"Объединенные данные, размер: {merged.shape}")
        def clean_numeric(val):
            if pd.isna(val):
                return val
            if isinstance(val, str):
                cleaned = val.replace(',', '.').strip()
                import re
                cleaned = re.sub(r'[^\d\.\-]', '', cleaned)
                if cleaned == '' or cleaned == '.':
                    return None
                try:
                    return float(cleaned)
                except ValueError:
                    return None
            return val

        if 'order_qty' in merged.columns:
            merged['order_qty'] = merged['order_qty'].apply(clean_numeric)
            merged['order_qty'] = pd.to_numeric(merged['order_qty'], errors='coerce')
        for col in ['MGVRG', 'GMNGA', 'VGW01', 'VGW04', 'VGW05']:
            if col in merged.columns:
                col_data = merged[col]
                if isinstance(col_data, pd.DataFrame):
                    col_data = col_data.iloc[:, 0]
                merged[col] = pd.to_numeric(col_data, errors='coerce')

        return merged

    def _calculate_labor_intensity(self, df: pd.DataFrame) -> pd.DataFrame:
        def clean_numeric(val):
            if pd.isna(val):
                return val
            if isinstance(val, str):
                cleaned = val.replace(',', '.').strip()
                import re
                cleaned = re.sub(r'[^\d\.\-]', '', cleaned)
                if cleaned == '' or cleaned == '.':
                    return None
                try:
                    return float(cleaned)
                except ValueError:
                    return None
            return val

        col_map = {
            'VGW01': 'Заданное значение VGW01',
            'VGW04': 'Заданное значение VGW04',
            'VGW05': 'Заданное значение VGW05',
            'MGVRG': 'Количество операции MGVRG',
            'GMNGA': 'ПодтверждВыхПрод GMNGA'
        }
        existing = {}
        for short, long in col_map.items():
            if long in df.columns:
                existing[short] = long
            elif short in df.columns:
                existing[short] = short
            else:
                existing[short] = None

        for short, col_name in existing.items():
            if col_name is not None:
                df[col_name] = df[col_name].apply(clean_numeric)
                df[col_name] = pd.to_numeric(df[col_name], errors='coerce')
                df[short] = df[col_name]

        if all(existing[col] is not None for col in ['VGW01', 'VGW04', 'VGW05', 'MGVRG']):
            vgw05 = df['VGW05'].replace(0, 1)
            df['planned_labor'] = df['VGW01'] * (df['VGW04'] / vgw05) * df['MGVRG']
            if existing['GMNGA'] is not None:
                df['actual_labor'] = df['VGW01'] * (df['VGW04'] / vgw05) * df['GMNGA']
            else:
                df['actual_labor'] = 0.0
        else:
            df['planned_labor'] = 0.0
            df['actual_labor'] = 0.0
            logger.warning("Отсутствуют столбцы для расчета трудоемкости, устанавливаем в ноль.")

        return df

    def get_optimization_data(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        merged = self.join_data()

        orders_df = merged[['order_id', 'product_code', 'order_qty',
                            'start_date', 'end_date']].copy()
        orders_df.drop_duplicates(inplace=True)

        workplaces_df = self.dfs.get('workplaces')
        if workplaces_df is None:
            resources_df = merged[['ARBID', 'workplace_code', 'workplace_name', 'AZNOR', 'NGRAD',
                                   'BEGZT', 'ENDZT', 'PAUSE']].copy()
            resources_df.drop_duplicates(inplace=True)
        else:
            wp_cols = ['Ид. объекта', 'Рабочее место ARBPL', 'Краткое название KTEXT']
            available_cols = [c for c in wp_cols if c in workplaces_df.columns]
            if not available_cols:
                raise ValueError("CRHD file missing required columns")
            workplaces = workplaces_df[available_cols].copy()
            rename_map = {
                'Ид. объекта': 'ARBID',
                'Рабочее место ARBPL': 'workplace_code',
                'Краткое название KTEXT': 'workplace_name'
            }
            workplaces.rename(columns=rename_map, inplace=True)
            if 'ARBID' not in workplaces.columns:
                workplaces['ARBID'] = workplaces.iloc[:, 0] 
            capacities_df = self.dfs.get('capacities')
            if capacities_df is not None:
                cap_cols = ['Ид. мощности', 'Время начала BEGZT', 'Время конца ENDZT',
                            'Перерыв/сек. PAUSE', 'Число ОтдМощностей AZNOR', 'СтепИспользования NGRAD']
                cap_available = [c for c in cap_cols if c in capacities_df.columns]
                if cap_available:
                    capacities = capacities_df[cap_available].copy()
                    capacities.rename(columns={'Ид. мощности': 'ARBID'}, inplace=True)
                    workplaces = pd.merge(workplaces, capacities, on='ARBID', how='left')
                    cap_rename = {
                        'Время начала BEGZT': 'BEGZT',
                        'Время конца ENDZT': 'ENDZT',
                        'Перерыв/сек. PAUSE': 'PAUSE',
                        'Число ОтдМощностей AZNOR': 'AZNOR',
                        'СтепИспользования NGRAD': 'NGRAD'
                    }
                    for old, new in cap_rename.items():
                        if old in workplaces.columns:
                            workplaces.rename(columns={old: new}, inplace=True)
                else:
                    pass
            default_values = {
                'BEGZT': 28800,   
                'ENDZT': 61200,   
                'PAUSE': 3600,    
                'AZNOR': 1,
                'NGRAD': 100     
            }
            for col, default in default_values.items():
                if col not in workplaces.columns:
                    workplaces[col] = default
                else:
                    workplaces[col] = pd.to_numeric(workplaces[col], errors='coerce').fillna(default)
            if 'workplace_code' not in workplaces.columns:
                workplaces['workplace_code'] = workplaces['ARBID']
            if 'workplace_name' not in workplaces.columns:
                workplaces['workplace_name'] = ''
            resources_df = workplaces[['ARBID', 'workplace_code', 'workplace_name',
                                       'AZNOR', 'NGRAD', 'BEGZT', 'ENDZT', 'PAUSE']].copy()
            resources_df.drop_duplicates(inplace=True)

        processing_times_df = merged[['order_id', 'tech_card', 'operation', 'ARBID',
                                      'planned_labor', 'actual_labor', 'order_qty', 'Счетчик APLZL',
                                      'work_type_code']].copy()
        processing_times_df.rename(columns={'Счетчик APLZL': 'counter'}, inplace=True)

        return orders_df, resources_df, processing_times_df

    def build_initial_plan(self) -> ProductionPlan:
        merged = self.join_data()
        if 'start_date' in merged.columns:
            merged['start_date'] = pd.to_datetime(merged['start_date'], errors='coerce')
        if 'end_date' in merged.columns:
            merged['end_date'] = pd.to_datetime(merged['end_date'], errors='coerce')

        assignments = []
        for order_id, group in merged.groupby('order_id'):
            order_start = group['start_date'].min()
            order_end = group['end_date'].max()
            if pd.isna(order_start) or pd.isna(order_end):
                order_start = datetime.now()
                order_end = order_start + timedelta(days=1)

            total_labor = group['planned_labor'].sum()
            if total_labor == 0:
                total_labor = 1

            if 'Счетчик APLZL' in group.columns:
                group = group.sort_values('Счетчик APLZL')
            else:
                group = group.sort_values('operation')

            current_time = order_start
            for idx, row in group.iterrows():
                labor = row['planned_labor']
                if labor == 0:
                    labor = 1  
                duration_seconds = (labor / total_labor) * (order_end - order_start).total_seconds()
                duration_seconds = max(duration_seconds, 60)  
                end_time = current_time + timedelta(seconds=duration_seconds)
                if end_time > order_end:
                    end_time = order_end
                planned_labor = row.get('planned_labor', 0.0)
                labor_hours = planned_labor / 60.0
                quantity_val = row.get('order_qty', 0.0)
                if hasattr(quantity_val, '__len__') and not isinstance(quantity_val, (str, bytes)):
                    if len(quantity_val) > 0:
                        quantity = float(quantity_val.iloc[0]) if hasattr(quantity_val, 'iloc') else float(quantity_val[0])
                    else:
                        quantity = 0.0
                else:
                    quantity = float(quantity_val) if not pd.isna(quantity_val) else 0.0
                assignment = Assignment(
                    order_id=str(row['order_id']),
                    operation_id=str(row.get('operation', '')),
                    workplace_id=str(row.get('ARBID', '')),
                    period=0,  
                    start_time=current_time,
                    end_time=end_time,
                    quantity_produced=quantity,
                    labor_hours=labor_hours,
                    setup_cost=0.0
                )
                assignments.append(assignment)
                current_time = end_time

        plan = ProductionPlan(
            assignments=assignments,
            total_profit=0.0,
            total_setup_cost=0.0
        )
        logger.info(f"Построен первоначальный план с {len(assignments)} назначениями")
        return plan

    def build_improved_initial_plan(self) -> ProductionPlan:
        merged = self.join_data()
        if 'start_date' in merged.columns:
            merged['start_date'] = pd.to_datetime(merged['start_date'], errors='coerce')
        if 'end_date' in merged.columns:
            merged['end_date'] = pd.to_datetime(merged['end_date'], errors='coerce')
        if 'planned_labor' in merged.columns:
            merged['planned_labor'] = pd.to_numeric(merged['planned_labor'], errors='coerce').fillna(60)
        else:
            merged['planned_labor'] = 60 
        workplace_schedule = {}
        for _, row in merged[['ARBID', 'BEGZT', 'ENDZT', 'PAUSE']].drop_duplicates().iterrows():
            wp = str(row['ARBID'])
            if pd.isna(row['BEGZT']) or pd.isna(row['ENDZT']):
                start_sec = 8 * 3600 
                end_sec = 17 * 3600   
                pause = 0
            else:
                start_sec = int(float(row['BEGZT']))
                end_sec = int(float(row['ENDZT']))
                pause = int(float(row['PAUSE'])) if not pd.isna(row['PAUSE']) else 0
            workplace_schedule[wp] = (start_sec, end_sec, pause)

        busy_intervals = {wp: [] for wp in workplace_schedule.keys()}

        def find_free_slot(wp_id, earliest_start, duration, schedule, busy):
            start_sec, end_sec, pause = schedule.get(wp_id, (8*3600, 17*3600, 0))
            work_day_length = end_sec - start_sec - pause
            if work_day_length <= 0:
                work_day_length = 8 * 3600

            current_date = earliest_start.replace(hour=0, minute=0, second=0, microsecond=0)
            max_days = 30
            for day_offset in range(max_days):
                day = current_date + timedelta(days=day_offset)
                day_start = day + timedelta(seconds=start_sec)
                day_end = day + timedelta(seconds=end_sec)
                if pause > 0:
                    pause_start = day_end - timedelta(seconds=pause)
                    periods = [(day_start, pause_start),
                               (pause_start + timedelta(seconds=pause), day_end)]
                else:
                    periods = [(day_start, day_end)]

                for period_start, period_end in periods:
                    candidate = max(period_start, earliest_start)
                    if candidate >= period_end:
                        continue
                    sorted_busy = sorted(busy, key=lambda x: x[0])
                    for busy_start, busy_end in sorted_busy:
                        if busy_end <= candidate:
                            continue
                        if busy_start >= candidate + duration:
                            break
                        candidate = max(candidate, busy_end)
                    if candidate + duration <= period_end:
                        return candidate, candidate + duration
            return None

        assignments = []
        order_last_end = {}
        order_groups = merged.groupby('order_id')
        order_start_dates = {}
        for order_id, group in order_groups:
            start = group['start_date'].min()
            if pd.isna(start):
                start = datetime.now().replace(hour=0, minute=0, second=0)
            else:
                start = start.replace(hour=0, minute=0, second=0)
            order_start_dates[order_id] = start

        sorted_order_ids = sorted(order_start_dates.keys(), key=lambda oid: order_start_dates[oid])
        for order_id in sorted_order_ids:
            group = order_groups.get_group(order_id)
            if 'Счетчик APLZL' in group.columns:
                group = group.sort_values('Счетчик APLZL')
            else:
                group = group.sort_values('operation')
            for idx, row in group.iterrows():
                operation_id = str(row.get('operation', ''))
                workplace_id = str(row.get('ARBID', ''))
                if not workplace_id or workplace_id == 'nan':
                    continue
                duration_minutes = max(float(row['planned_labor']), 1.0)
                duration = timedelta(minutes=duration_minutes)

                order_start = order_start_dates[order_id]
                earliest_start = max(order_start, order_last_end.get(order_id, order_start))
                if order_id == 'ORD004':
                    logger.debug(f"Операция {operation_id} на рабочем месте {workplace_id}, earliest_start={earliest_start}, order_last_end={order_last_end.get(order_id)}")

                slot = find_free_slot(workplace_id, earliest_start, duration,
                                      workplace_schedule, busy_intervals[workplace_id])
                if slot is None:
                    busy = busy_intervals[workplace_id]
                    if busy:
                        last_end = max(end for _, end in busy)
                        start_time = max(last_end, earliest_start)
                    else:
                        start_sec, _, _ = workplace_schedule.get(workplace_id, (8*3600, 17*3600, 0))
                        start_time = max(earliest_start + timedelta(seconds=start_sec), earliest_start)
                    end_time = start_time + duration
                    logger.warning(f"Не найден слот для операции {operation_id} на рабочем месте {workplace_id}, размещена после последней занятости в {start_time}")
                else:
                    start_time, end_time = slot

                planned_labor = row.get('planned_labor', 0.0)
                labor_hours = planned_labor / 60.0
                quantity_val = row.get('order_qty', 0.0)
                if hasattr(quantity_val, '__len__') and not isinstance(quantity_val, (str, bytes)):
                    if len(quantity_val) > 0:
                        quantity = float(quantity_val.iloc[0]) if hasattr(quantity_val, 'iloc') else float(quantity_val[0])
                    else:
                        quantity = 0.0
                else:
                    quantity = float(quantity_val) if not pd.isna(quantity_val) else 0.0
                assignment = Assignment(
                    order_id=order_id,
                    operation_id=operation_id,
                    workplace_id=workplace_id,
                    period=0,
                    start_time=start_time,
                    end_time=end_time,
                    quantity_produced=quantity,
                    labor_hours=labor_hours,
                    setup_cost=0.0
                )
                assignments.append(assignment)
                busy_intervals[workplace_id].append((start_time, end_time))
                busy_intervals[workplace_id].sort(key=lambda x: x[0])
                order_last_end[order_id] = end_time

        plan = ProductionPlan(
            assignments=assignments,
            total_profit=0.0,
            total_setup_cost=0.0
        )
        logger.info(f"Построен улучшенный первоначальный план с {len(assignments)} назначениями")
        return plan


if __name__ == '__main__':
    loader = DataLoader('../Attachments_Kleschevnikov-A-M@protonpm.ru_2026-03-12_17-03-21')
    loader.load_all()
    merged = loader.join_data()
    print(merged.head())