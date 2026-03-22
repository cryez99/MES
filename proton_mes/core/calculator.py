import pandas as pd
import numpy as np
from typing import Dict, List


class LaborCalculator:
    @staticmethod
    def calculate_planned_labor(vgw01: float, vgw04: float, vgw05: float, mgvrg: float) -> float:
        if vgw05 == 0:
            return 0.0
        return vgw01 * (vgw04 / vgw05) * mgvrg

    @staticmethod
    def calculate_actual_labor(vgw01: float, vgw04: float, vgw05: float, gmnga: float) -> float:
        if vgw05 == 0:
            return 0.0
        return vgw01 * (vgw04 / vgw05) * gmnga

    @staticmethod
    def compute_for_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # Ensure numeric
        for col in ['VGW01', 'VGW04', 'VGW05', 'MGVRG', 'GMNGA']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        if all(col in df.columns for col in ['VGW01', 'VGW04', 'VGW05', 'MGVRG']):
            df['planned_labor'] = df.apply(
                lambda row: LaborCalculator.calculate_planned_labor(
                    row['VGW01'], row['VGW04'], row['VGW05'], row['MGVRG']
                ), axis=1
            )
        else:
            df['planned_labor'] = 0.0

        if all(col in df.columns for col in ['VGW01', 'VGW04', 'VGW05', 'GMNGA']):
            df['actual_labor'] = df.apply(
                lambda row: LaborCalculator.calculate_actual_labor(
                    row['VGW01'], row['VGW04'], row['VGW05'], row['GMNGA']
                ), axis=1
            )
        else:
            df['actual_labor'] = 0.0

        return df


class CapacityCalculator:
    @staticmethod
    def daily_capacity_hours(start_sec: int, end_sec: int, break_sec: int,
                             utilization: float, num_resources: int) -> float:
        if end_sec <= start_sec:
            total_sec = 24 * 3600
        else:
            total_sec = end_sec - start_sec
        net_sec = total_sec - break_sec
        if net_sec < 0:
            net_sec = 0
        hours = net_sec / 3600
        return hours * utilization * num_resources

    @staticmethod
    def compute_capacity_df(resources_df: pd.DataFrame) -> pd.DataFrame:
        df = resources_df.copy()
        for col in ['BEGZT', 'ENDZT', 'PAUSE', 'NGRAD', 'AZNOR']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df['daily_capacity_hours'] = df.apply(
            lambda row: CapacityCalculator.daily_capacity_hours(
                row.get('BEGZT', 0),
                row.get('ENDZT', 0),
                row.get('PAUSE', 0),
                row.get('NGRAD', 1.0),
                row.get('AZNOR', 1)
            ), axis=1
        )
        return df