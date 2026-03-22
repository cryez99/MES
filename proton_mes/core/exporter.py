
import pandas as pd
from datetime import datetime
from typing import List
from .models import ProductionPlan, Assignment


def export_plan_to_excel(plan: ProductionPlan, filepath: str) -> None:
    assignments_data = []
    for a in plan.assignments:
        duration = (a.end_time - a.start_time).total_seconds() / 3600.0
        labor = a.quantity_produced 
        assignments_data.append({
            'Рабочее место': a.workplace_id,
            'Период': a.period,
            'Заказ': a.order_id,
            'Операция': a.operation_id,
            'Начало': a.start_time,
            'Окончание': a.end_time,
            'Длительность (часы)': round(duration, 2),
            'Количество': a.quantity_produced,
            'Затраты на переналадку': a.setup_cost,
            'Статус': 'планируется',
        })
    df_assign = pd.DataFrame(assignments_data)
    if not df_assign.empty:
        df_assign['Начало'] = pd.to_datetime(df_assign['Начало'])
        df_assign['Окончание'] = pd.to_datetime(df_assign['Окончание'])
        df_assign['Начало'] = df_assign['Начало'].dt.strftime('%Y-%m-%d %H:%M')
        df_assign['Окончание'] = df_assign['Окончание'].dt.strftime('%Y-%m-%d %H:%M')

    summary_data = [
        ['Общая прибыль', plan.total_profit],
        ['Затраты на переналадку', plan.total_setup_cost],
        ['Количество назначений', len(plan.assignments)],
        ['Дата генерации', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
    ]
    df_summary = pd.DataFrame(summary_data, columns=['Параметр', 'Значение'])

    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df_assign.to_excel(writer, sheet_name='Назначения', index=False)
        df_summary.to_excel(writer, sheet_name='Сводка', index=False)

        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

    print(f'План экспортирован в {filepath}')


def export_assignments_to_csv(assignments: List[Assignment], filepath: str) -> None:
    data = []
    for a in assignments:
        duration = (a.end_time - a.start_time).total_seconds() / 3600.0
        data.append({
            'workplace_id': a.workplace_id,
            'period': a.period,
            'order_id': a.order_id,
            'operation_id': a.operation_id,
            'start_time': a.start_time,
            'end_time': a.end_time,
            'duration_hours': round(duration, 2),
            'quantity_produced': a.quantity_produced,
            'setup_cost': a.setup_cost,
            'status': 'planned',
        })
    df = pd.DataFrame(data)
    df.to_csv(filepath, index=False, encoding='utf-8-sig')
    print(f'Назначения экспортированы в {filepath}')