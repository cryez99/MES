import sys
import os
import pandas as pd
from PyQt5.QtWidgets import (QMainWindow, QTabWidget, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QFileDialog, QLabel,
                             QTableWidget, QTableWidgetItem, QMessageBox,
                             QGroupBox, QSpinBox, QDoubleSpinBox, QComboBox,
                             QTextEdit, QProgressBar, QApplication)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from core.data_loader import DataLoader, MissingFilesError
from core.optimizer import create_optimizer_from_dataframes, MESOptimizer
from core.calculator import CapacityCalculator
from core.models import EmergencyStop
from .gantt_widget import GanttWidget
from .dialogs import EmergencyStopDialog, ExportDialog, ChangeoverCostDialog, OrderPriceDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data_loader = None
        self.merged_data = None
        self.orders_df = None
        self.resources_df = None
        self.processing_df = None
        self.optimizer = None
        self.plan = None
        self.initial_plan = None  
        self.emergency_stops = [] 
        self.changeover_costs = {}  
        self.order_prices = {}     
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("MES Система оптимизации производственного планирования")
        self.setGeometry(100, 100, 1200, 800)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tab_planning = QWidget()
        self.tab_gantt = QWidget()
        self.tab_stops = QWidget()
        self.tab_reference = QWidget()
        self.tab_initial = QWidget()
        self.tab_help = QWidget()

        self.tabs.addTab(self.tab_planning, "Планирование")
        self.tabs.addTab(self.tab_gantt, "Диаграмма Ганта")
        self.tabs.addTab(self.tab_stops, "Управление остановками")
        self.tabs.addTab(self.tab_reference, "Справочники")
        self.tabs.addTab(self.tab_initial, "Исходные данные")
        self.tabs.addTab(self.tab_help, "Справка")

        self.setup_planning_tab()
        self.setup_gantt_tab()
        self.setup_stops_tab()
        self.setup_reference_tab()
        self.setup_initial_tab()
        self.setup_help_tab()

        self.statusBar().showMessage("Готово")

    def setup_planning_tab(self):
        layout = QVBoxLayout()

        load_group = QGroupBox("Загрузка данных")
        load_layout = QHBoxLayout()
        self.btn_load = QPushButton("Загрузить Excel файлы")
        self.btn_load.clicked.connect(self.load_data)
        self.label_data_status = QLabel("Данные не загружены")
        load_layout.addWidget(self.btn_load)
        load_layout.addWidget(self.label_data_status)
        load_layout.addStretch()
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)

        param_group = QGroupBox("Параметры оптимизации")
        param_layout = QVBoxLayout()
        horizon_layout = QHBoxLayout()
        horizon_layout.addWidget(QLabel("Горизонт планирования (дней):"))
        self.spin_horizon = QSpinBox()
        self.spin_horizon.setRange(1, 365)
        self.spin_horizon.setValue(7)
        horizon_layout.addWidget(self.spin_horizon)
        horizon_layout.addStretch()
        param_layout.addLayout(horizon_layout)


        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Тип оптимизации:"))
        self.combo_optimization_type = QComboBox()
        self.combo_optimization_type.addItem("Максимизация прибыли")
        self.combo_optimization_type.addItem("Минимизация времени")
        type_layout.addWidget(self.combo_optimization_type)
        type_layout.addStretch()
        param_layout.addLayout(type_layout)

        changeover_layout = QHBoxLayout()
        changeover_layout.addWidget(QLabel("Стоимость перенакладки:"))
        self.btn_changeover = QPushButton("Задать для рабочих мест...")
        self.btn_changeover.clicked.connect(self.set_changeover_costs)
        changeover_layout.addWidget(self.btn_changeover)
        changeover_layout.addStretch()
        param_layout.addLayout(changeover_layout)

        order_price_layout = QHBoxLayout()
        order_price_layout.addWidget(QLabel("Цены на заказы:"))
        self.btn_order_prices = QPushButton("Задать цены...")
        self.btn_order_prices.clicked.connect(self.set_order_prices)
        order_price_layout.addWidget(self.btn_order_prices)
        order_price_layout.addStretch()
        param_layout.addLayout(order_price_layout)

        param_group.setLayout(param_layout)
        layout.addWidget(param_group)

        btn_layout = QHBoxLayout()
        self.btn_optimize = QPushButton("Запустить оптимизацию")
        self.btn_optimize.clicked.connect(self.run_optimization)
        self.btn_optimize.setEnabled(False)
        self.btn_export = QPushButton("Экспорт плана в Excel")
        self.btn_export.clicked.connect(self.export_plan)
        self.btn_export.setEnabled(False)
        self.btn_compare = QPushButton("Сравнить планы")
        self.btn_compare.clicked.connect(self.compare_plans)
        self.btn_compare.setEnabled(False)
        btn_layout.addWidget(self.btn_optimize)
        btn_layout.addWidget(self.btn_export)
        btn_layout.addWidget(self.btn_compare)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.table_results = QTableWidget()
        self.table_results.setSortingEnabled(True)
        self.table_results.setColumnCount(6)
        self.table_results.setHorizontalHeaderLabels([
            "Заказ", "Рабочее место", "Период", "Количество", "Начало", "Окончание"
        ])
        layout.addWidget(self.table_results)

        self.tab_planning.setLayout(layout)

    def setup_gantt_tab(self):
        layout = QVBoxLayout()
        self.gantt = GanttWidget()
        layout.addWidget(self.gantt)
        self.tab_gantt.setLayout(layout)

    def setup_stops_tab(self):
        layout = QVBoxLayout()
        self.btn_add_stop = QPushButton("Добавить аварийную остановку")
        self.btn_add_stop.clicked.connect(self.add_emergency_stop)
        layout.addWidget(self.btn_add_stop)

        self.table_stops = QTableWidget()
        self.table_stops.setSortingEnabled(True)
        self.table_stops.setColumnCount(5)
        self.table_stops.setHorizontalHeaderLabels([
            "Рабочее место", "Начало", "Окончание", "Причина", "Действия"
        ])
        layout.addWidget(self.table_stops)

        self.btn_recalculate = QPushButton("Пересчитать план с учетом остановок")
        self.btn_recalculate.clicked.connect(self.recalculate_with_stops)
        layout.addWidget(self.btn_recalculate)

        self.tab_stops.setLayout(layout)

    def setup_reference_tab(self):
        layout = QVBoxLayout()
        self.tab_reference_tabs = QTabWidget()
        self.table_orders = QTableWidget()
        self.table_orders.setSortingEnabled(True)
        self.table_workplaces = QTableWidget()
        self.table_workplaces.setSortingEnabled(True)
        self.table_operations = QTableWidget()
        self.table_operations.setSortingEnabled(True)
        self.table_product_operation = QTableWidget()
        self.table_product_operation.setSortingEnabled(True)
        self.table_workplace_operation = QTableWidget()
        self.table_workplace_operation.setSortingEnabled(True)
        self.tab_reference_tabs.addTab(self.table_orders, "Заказы")
        self.tab_reference_tabs.addTab(self.table_workplaces, "Рабочие места")
        self.tab_reference_tabs.addTab(self.table_operations, "Операции")
        self.tab_reference_tabs.addTab(self.table_product_operation, "Изделие-Операция")
        self.tab_reference_tabs.addTab(self.table_workplace_operation, "Рабочее место-Операция")
        layout.addWidget(self.tab_reference_tabs)
        self.tab_reference.setLayout(layout)

    def setup_initial_tab(self):
        layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        self.label_initial_status = QLabel("Исходный план не построен")
        self.btn_build_initial = QPushButton("Построить исходный план")
        self.btn_build_initial.clicked.connect(self.build_initial_plan)
        self.btn_build_initial.setEnabled(False)
        self.btn_export_initial = QPushButton("Экспорт исходного плана в Excel")
        self.btn_export_initial.clicked.connect(self.export_initial_plan)
        self.btn_export_initial.setEnabled(False)
        self.btn_compare = QPushButton("Сравнить с оптимизированным")
        self.btn_compare.clicked.connect(self.compare_plans)
        self.btn_compare.setEnabled(False)
        top_layout.addWidget(self.label_initial_status)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_build_initial)
        top_layout.addWidget(self.btn_export_initial)
        top_layout.addWidget(self.btn_compare)
        layout.addLayout(top_layout)

        self.table_initial = QTableWidget()
        self.table_initial.setSortingEnabled(True)
        self.table_initial.setColumnCount(7)
        self.table_initial.setHorizontalHeaderLabels([
            "Заказ", "Рабочее место", "Период", "Количество", "Начало", "Окончание", "Трудоемкость (ч)"
        ])
        layout.addWidget(self.table_initial)

        self.gantt_initial = GanttWidget()
        layout.addWidget(self.gantt_initial)

        self.tab_initial.setLayout(layout)

    def setup_help_tab(self):
        layout = QVBoxLayout()
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setHtml(self._get_help_html())
        layout.addWidget(help_text)
        self.tab_help.setLayout(layout)

    def _get_help_html(self):
        return """
        <html>
        <head>
        <style>
        body { font-family: Arial, sans-serif; margin: 10px; }
        h1 { color: #2c3e50; }
        h2 { color: #34495e; margin-top: 20px; }
        ul { margin-left: 20px; }
        li { margin-bottom: 5px; }
        .note { background-color: #f8f9fa; padding: 10px; border-left: 4px solid #3498db; }
        table { border-collapse: collapse; width: 100%; margin: 15px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; font-weight: bold; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .required { color: #c0392b; font-weight: bold; }
        .optional { color: #27ae60; }
        .column-list { font-family: monospace; font-size: 0.9em; }
        </style>
        </head>
        <body>
        <h1>Справка по работе с приложением MES оптимизации</h1>
        <p>Данное приложение предназначено для оптимизации производственного планирования на основе данных SAP ERP.</p>
        
        <h2>Основные шаги работы</h2>
        <ul>
        <li><b>Загрузка данных</b>: На вкладке "Планирование" нажмите "Загрузить Excel файлы". Выберите папку, содержащую необходимые файлы (заказы, техкарты, операции, нормативы, рабочие места, виды работ, мощности). Обязательные файлы: "заказы дебл.XLSX" и "AFKO_рр заказы номера техкарт.XLSX". Если файлы отсутствуют, появится сообщение с указанием недостающих.</li>
        <li><b>Настройка параметров</b>: Установите горизонт планирования (дни), выберите тип оптимизации (максимизация прибыли или минимизация времени), при необходимости задайте стоимости переналадки и цены на заказы.</li>
        <li><b>Запуск оптимизации</b>: Нажмите "Запустить оптимизацию". Результаты появятся в таблице и на вкладке "Диаграмма Ганта".</li>
        <li><b>Управление остановками</b>: На вкладке "Управление остановками" можно добавлять аварийные остановки рабочих мест, после чего пересчитать план.</li>
        <li><b>Просмотр справочников</b>: На вкладке "Справочники" доступны таблицы заказов, рабочих мест, операций и связей.</li>
        <li><b>Исходные данные</b>: На вкладке "Исходные данные" можно построить исходный план (без оптимизации) и сравнить его с оптимизированным.</li>
        <li><b>Экспорт</b>: Результаты можно сохранить в Excel (кнопки "Экспорт плана в Excel" и "Экспорт исходного плана в Excel").</li>
        </ul>
        
        <h2>Требования к данным</h2>
        <p>Приложение ожидает следующие файлы Excel (имена должны точно совпадать, регистр важен):</p>
        <table>
          <thead>
            <tr>
              <th>Файл</th>
              <th>Обязательный</th>
              <th>Назначение</th>
              <th>Обязательные столбцы</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>заказы дебл.XLSX</td>
              <td><span class="required">Да</span></td>
              <td>Заказы с информацией о заказах, сроках, количестве</td>
              <td class="column-list">Заказ AUFNR, Код изделия, Количество заказа (GMEIN), СрокНачала/Базис, БазисСрокКонца, ПользовСтатус</td>
            </tr>
            <tr>
              <td>AFKO_рр заказы номера техкарт.XLSX</td>
              <td><span class="required">Да</span></td>
              <td>Связь заказ-техкарта</td>
              <td class="column-list">Заказ AUFNR, № техкарты/операции  AUFPL</td>
            </tr>
            <tr>
              <td>AFVC_данные к операции_айди рабочего места, вид ра.XLSX</td>
              <td><span class="optional">Нет</span></td>
              <td>Операции с указанием рабочего места и вида работ</td>
              <td class="column-list">№ техкарты/операции AUFPL, Счетчик APLZL, Операция VORNR, Краткий текст к операции LTXA1, Управляющий ключ STEUS, Ид. Объекта ARBID, Вид работ LAR01</td>
            </tr>
            <tr>
              <td>AFVV_данные от техкарт по структуре операции Колич.XLSX</td>
              <td><span class="optional">Нет</span></td>
              <td>Нормативы времени и количества</td>
              <td class="column-list">№ техкарты/операции AUFPL, Счетчик APLZL, Заданное значение VGW01, ЕдинИзмеренЗаданЗнач VGE03, Заданное значение VGW04, Заданное значение VGW05, Количество операции MGVRG, ПодтверждВыхПрод GMNGA</td>
            </tr>
            <tr>
              <td>CRHD_V1_рабочее место номер и название краткое.XLSX</td>
              <td><span class="optional">Нет</span></td>
              <td>Рабочие места с названиями</td>
              <td class="column-list">Ид. объекта, Рабочее место ARBPL, Краткое название KTEXT</td>
            </tr>
            <tr>
              <td>CSLT_виды работ_текст.XLSX</td>
              <td><span class="optional">Нет</span></td>
              <td>Виды работ с описанием</td>
              <td class="column-list">Вид работ LSTAR, Название KTEXT</td>
            </tr>
            <tr>
              <td>KAKO_мощность.XLSX</td>
              <td><span class="optional">Нет</span></td>
              <td>Мощности рабочих мест (рабочее время, перерывы)</td>
              <td class="column-list">Ид. мощности, Время начала BEGZT, Время конца ENDZT, Перерыв/сек. PAUSE, Число ОтдМощностей AZNOR, СтепИспользования NGRAD</td>
            </tr>
          </tbody>
        </table>
        <p>Все файлы должны находиться в одной директории. Приложение автоматически связывает данные по ключам.</p>
        <p>Поддерживаемые форматы: .xlsx, .xls.</p>
        
        <h2>Возможные проблемы и решения</h2>
        <ul>
        <li><b>Не загружаются данные</b>: Проверьте наличие обязательных файлов в выбранной папке. Убедитесь, что файлы не повреждены и имеют правильные названия столбцов.</li>
        <li><b>Оптимизация не запускается</b>: Убедитесь, что данные загружены (статус "Загружено"). Проверьте, что горизонт планирования не слишком мал.</li>
        <li><b>Диаграмма Ганта не отображается</b>: После оптимизации перейдите на вкладку "Диаграмма Ганта". Если план пуст, возможно, нет назначений.</li>
        </ul>
        
        </body>
        </html>
        """
    def build_initial_plan(self):
        if self.data_loader is None:
            QMessageBox.warning(self, "Предупреждение", "Сначала загрузите данные.")
            return
        try:
            self.initial_plan = self.data_loader.build_improved_initial_plan()
            self.display_initial_plan()
            self.gantt_initial.update_gantt(self.initial_plan)
            self.label_initial_status.setText(f"Исходный план построен: {len(self.initial_plan.assignments)} назначений")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка построения исходного плана", str(e))

    def display_initial_plan(self):
        if self.initial_plan is None:
            return
        assignments = self.initial_plan.assignments
        self.table_initial.setRowCount(len(assignments))
        for i, a in enumerate(assignments):
            self.table_initial.setItem(i, 0, QTableWidgetItem(a.order_id))
            self.table_initial.setItem(i, 1, QTableWidgetItem(a.workplace_id))
            self.table_initial.setItem(i, 2, QTableWidgetItem(str(a.period)))
            self.table_initial.setItem(i, 3, QTableWidgetItem(f"{a.quantity_produced:.2f}"))
            self.table_initial.setItem(i, 4, QTableWidgetItem(a.start_time.strftime("%Y-%m-%d %H:%M")))
            self.table_initial.setItem(i, 5, QTableWidgetItem(a.end_time.strftime("%Y-%m-%d %H:%M")))
            self.table_initial.setItem(i, 6, QTableWidgetItem(f"{a.labor_hours:.2f}"))
    def load_data(self):
        data_dir = QFileDialog.getExistingDirectory(self, "Выберите папку с Excel файлами",
                                                    "../Attachments_Kleschevnikov-A-M@protonpm.ru_2026-03-12_17-03-21")
        if not data_dir:
            return
        try:
            self.data_loader = DataLoader(data_dir)
            self.data_loader.load_all()
            self.merged_data = self.data_loader.join_data()
            self.orders_df, self.resources_df, self.processing_df = self.data_loader.get_optimization_data()
            self.resources_df = CapacityCalculator.compute_capacity_df(self.resources_df)
            self.label_data_status.setText(f"Загружено: {len(self.orders_df)} заказов, {len(self.resources_df)} рабочих мест")
            self.btn_optimize.setEnabled(True)
            self.btn_build_initial.setEnabled(True)
            self.update_reference_tables()
            try:
                self.initial_plan = self.data_loader.build_improved_initial_plan()
                self.display_initial_plan()
                self.gantt_initial.update_gantt(self.initial_plan)
                self.label_initial_status.setText(f"Исходный план построен: {len(self.initial_plan.assignments)} назначений")
            except Exception as e:
                self.label_initial_status.setText("Ошибка построения исходного плана")
                print(f"Initial plan build error: {e}")
            QMessageBox.information(self, "Успех", "Данные успешно загружены.")
        except MissingFilesError as e:
            lines = []
            if e.missing_details:
                lines.append("Отсутствуют файлы:")
                for detail in e.missing_details:
                    req = "обязательный" if detail['required'] else "опциональный"
                    lines.append(f"  • {detail['filename']} ({req})")
                    if detail['required_columns']:
                        cols = ", ".join(detail['required_columns'])
                        lines.append(f"    Требуемые столбцы: {cols}")
            else:
                lines.append("Не найдены обязательные файлы:")
                lines.extend(f"  • {f}" for f in e.missing_files)
            lines.append("\nУбедитесь, что в выбранной папке присутствуют все необходимые файлы.")
            QMessageBox.critical(self, "Отсутствуют файлы", "\n".join(lines))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {str(e)}")

    def update_reference_tables(self):
        self.table_orders.setRowCount(len(self.orders_df))
        self.table_orders.setColumnCount(5)
        self.table_orders.setHorizontalHeaderLabels(["ID заказа", "Код изделия", "Количество", "Начало", "Окончание"])
        for table_row, (_, row) in enumerate(self.orders_df.iterrows()):
            self.table_orders.setItem(table_row, 0, QTableWidgetItem(str(row.get('order_id', ''))))
            self.table_orders.setItem(table_row, 1, QTableWidgetItem(str(row.get('product_code', ''))))
            self.table_orders.setItem(table_row, 2, QTableWidgetItem(str(row.get('order_qty', ''))))
            self.table_orders.setItem(table_row, 3, QTableWidgetItem(str(row.get('start_date', ''))))
            self.table_orders.setItem(table_row, 4, QTableWidgetItem(str(row.get('end_date', ''))))

        self.table_workplaces.setRowCount(len(self.resources_df))
        self.table_workplaces.setColumnCount(9)
        self.table_workplaces.setHorizontalHeaderLabels([
            "ID", "Код", "Название", "AZNOR", "BEGZT", "ENDZT", "PAUSE", "NGRAD", "Емкость (ч/день)"
        ])
        for table_row, (_, row) in enumerate(self.resources_df.iterrows()):
            self.table_workplaces.setItem(table_row, 0, QTableWidgetItem(str(row.get('ARBID', ''))))
            self.table_workplaces.setItem(table_row, 1, QTableWidgetItem(str(row.get('workplace_code', ''))))
            self.table_workplaces.setItem(table_row, 2, QTableWidgetItem(str(row.get('workplace_name', ''))))
            self.table_workplaces.setItem(table_row, 3, QTableWidgetItem(str(row.get('AZNOR', ''))))
            self.table_workplaces.setItem(table_row, 4, QTableWidgetItem(str(row.get('BEGZT', ''))))
            self.table_workplaces.setItem(table_row, 5, QTableWidgetItem(str(row.get('ENDZT', ''))))
            self.table_workplaces.setItem(table_row, 6, QTableWidgetItem(str(row.get('PAUSE', ''))))
            self.table_workplaces.setItem(table_row, 7, QTableWidgetItem(str(row.get('NGRAD', ''))))
            self.table_workplaces.setItem(table_row, 8, QTableWidgetItem(str(row.get('daily_capacity_hours', ''))))

        if self.merged_data is not None:
            ops_cols = ['tech_card', 'operation', 'work_type_code', 'VGW01', 'VGE03', 'MGVRG', 'GMNGA', 'planned_labor', 'actual_labor']
            available_cols = [col for col in ops_cols if col in self.merged_data.columns]
            ops_df = self.merged_data[available_cols].drop_duplicates().reset_index(drop=True)
        else:
            ops_df = self.processing_df
        self.table_operations.setRowCount(len(ops_df))
        self.table_operations.setColumnCount(len(available_cols))
        self.table_operations.setHorizontalHeaderLabels([
            "Техкарта", "Операция", "Вид работ", "VGW01", "Ед. изм.", "MGVRG", "GMNGA", "План. трудозатраты", "Факт. трудозатраты"
        ])
        for table_row, (_, row) in enumerate(ops_df.iterrows()):
            for j, col in enumerate(available_cols):
                self.table_operations.setItem(table_row, j, QTableWidgetItem(str(row.get(col, ''))))

        if self.merged_data is not None and 'product_code' in self.merged_data.columns and 'operation' in self.merged_data.columns:
            prod_op_df = self.merged_data[['product_code', 'operation']].drop_duplicates().sort_values(['product_code', 'operation'])
        else:
            prod_op_df = self.merged_data.iloc[0:0][['product_code', 'operation']] if self.merged_data is not None else pd.DataFrame(columns=['product_code', 'operation'])
        self.table_product_operation.setRowCount(len(prod_op_df))
        self.table_product_operation.setColumnCount(2)
        self.table_product_operation.setHorizontalHeaderLabels(["Код изделия", "Операция"])
        for table_row, (_, row) in enumerate(prod_op_df.iterrows()):
            self.table_product_operation.setItem(table_row, 0, QTableWidgetItem(str(row.get('product_code', ''))))
            self.table_product_operation.setItem(table_row, 1, QTableWidgetItem(str(row.get('operation', ''))))

        if self.merged_data is not None and 'ARBID' in self.merged_data.columns and 'operation' in self.merged_data.columns:
            wp_op_df = self.merged_data[['ARBID', 'operation']].drop_duplicates().sort_values(['ARBID', 'operation'])
        else:
            wp_op_df = self.merged_data.iloc[0:0][['ARBID', 'operation']] if self.merged_data is not None else pd.DataFrame(columns=['ARBID', 'operation'])
        self.table_workplace_operation.setRowCount(len(wp_op_df))
        self.table_workplace_operation.setColumnCount(2)
        self.table_workplace_operation.setHorizontalHeaderLabels(["Рабочее место", "Операция"])
        for table_row, (_, row) in enumerate(wp_op_df.iterrows()):
            self.table_workplace_operation.setItem(table_row, 0, QTableWidgetItem(str(row.get('ARBID', ''))))
            self.table_workplace_operation.setItem(table_row, 1, QTableWidgetItem(str(row.get('operation', ''))))


    def display_plan(self):
        if self.plan is None:
            return
        df = self.optimizer.export_to_dataframe(self.plan)
        self.table_results.setRowCount(len(df))
        for i, row in df.iterrows():
            self.table_results.setItem(i, 0, QTableWidgetItem(str(row['order'])))
            self.table_results.setItem(i, 1, QTableWidgetItem(str(row['workplace'])))
            self.table_results.setItem(i, 2, QTableWidgetItem(str(row['period'])))
            self.table_results.setItem(i, 3, QTableWidgetItem(f"{row['quantity']:.2f}"))
            self.table_results.setItem(i, 4, QTableWidgetItem(str(row['start'])))
            self.table_results.setItem(i, 5, QTableWidgetItem(str(row['end'])))

    def export_plan(self):
        if self.plan is None:
            return
        dialog = ExportDialog(self)
        if dialog.exec_():
            filename = dialog.get_filename()
            if filename:
                df = self.optimizer.export_to_dataframe(self.plan)
                df.to_excel(filename, index=False)
                QMessageBox.information(self, "Экспорт", f"План сохранен в {filename}")

    def add_emergency_stop(self):
        dialog = EmergencyStopDialog(self.resources_df, self)
        if dialog.exec_():
            stop = dialog.get_stop()
            self.emergency_stops.append(stop)
            row = self.table_stops.rowCount()
            self.table_stops.insertRow(row)
            self.table_stops.setItem(row, 0, QTableWidgetItem(stop.workplace_id))
            self.table_stops.setItem(row, 1, QTableWidgetItem(stop.start_time.strftime("%Y-%m-%d %H:%M")))
            self.table_stops.setItem(row, 2, QTableWidgetItem(stop.end_time.strftime("%Y-%m-%d %H:%M")))
            self.table_stops.setItem(row, 3, QTableWidgetItem(stop.reason))
            btn_delete = QPushButton("Удалить")
            btn_delete.clicked.connect(lambda: self.delete_stop(row))
            self.table_stops.setCellWidget(row, 4, btn_delete)

    def set_changeover_costs(self):
        if self.resources_df is None:
            QMessageBox.warning(self, "Предупреждение", "Сначала загрузите данные.")
            return
        dialog = ChangeoverCostDialog(self.resources_df, self)
        if dialog.exec_():
            self.changeover_costs = dialog.get_costs()
            QMessageBox.information(self, "Стоимости перенакладки",
                                    f"Установлены стоимости для {len(self.changeover_costs)} рабочих мест.")

    def set_order_prices(self):
        if self.orders_df is None:
            QMessageBox.warning(self, "Предупреждение", "Сначала загрузите данные.")
            return
        dialog = OrderPriceDialog(self.orders_df, self)
        if dialog.exec_():
            self.order_prices = dialog.get_prices()
            QMessageBox.information(self, "Цены на заказы",
                                    f"Установлены цены для {len(self.order_prices)} заказов.")

    def delete_stop(self, row):
        if 0 <= row < len(self.emergency_stops):
            self.emergency_stops.pop(row)
        self.table_stops.removeRow(row)
        for r in range(row, self.table_stops.rowCount()):
            btn = self.table_stops.cellWidget(r, 4)
            if btn:
                try:
                    btn.clicked.disconnect()
                except:
                    pass
                btn.clicked.connect(lambda checked, r=r: self.delete_stop(r))

    def recalculate_with_stops(self):
        if self.orders_df is None or self.resources_df is None or self.processing_df is None:
            QMessageBox.warning(self, "Предупреждение", "Сначала загрузите данные.")
            return
        if not self.emergency_stops:
            QMessageBox.information(self, "Информация", "Нет аварийных остановок. План останется прежним.")
            return

        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        QApplication.processEvents()

        try:
            horizon = self.spin_horizon.value()
            self.optimizer = create_optimizer_from_dataframes(
                self.orders_df, self.resources_df, self.processing_df,
                emergency_stops=self.emergency_stops,
                planning_horizon=horizon,
                order_prices=self.order_prices
            )
            if self.changeover_costs:
                self.optimizer.set_changeover_costs(self.changeover_costs)
            self.plan = self.optimizer.optimize()
            self.display_plan()
            self.gantt.update_gantt(self.plan)
            QMessageBox.information(self, "Пересчет завершен",
                                    f"Новый план с учетом остановок. Прибыль: {self.plan.total_profit:.2f}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка пересчета", str(e))
        finally:
            self.progress.setVisible(False)
    @staticmethod
    def _format_timedelta_ru(td):
        total_seconds = int(td.total_seconds())
        sign = '' if total_seconds >= 0 else '-'
        total_seconds = abs(total_seconds)
        days = total_seconds // (24 * 3600)
        remaining = total_seconds % (24 * 3600)
        hours = remaining // 3600
        remaining %= 3600
        minutes = remaining // 60
        seconds = remaining % 60

        parts = []
        if days > 0:
            if days == 1:
                parts.append(f"{days} день")
            elif 2 <= days <= 4:
                parts.append(f"{days} дня")
            else:
                parts.append(f"{days} дней")
        if hours > 0:
            if hours == 1:
                parts.append(f"{hours} час")
            elif 2 <= hours <= 4:
                parts.append(f"{hours} часа")
            else:
                parts.append(f"{hours} часов")
        if minutes > 0:
            if minutes == 1:
                parts.append(f"{minutes} минута")
            elif 2 <= minutes <= 4:
                parts.append(f"{minutes} минуты")
            else:
                parts.append(f"{minutes} минут")
        if seconds > 0 and not parts:  
            if seconds == 1:
                parts.append(f"{seconds} секунда")
            elif 2 <= seconds <= 4:
                parts.append(f"{seconds} секунды")
            else:
                parts.append(f"{seconds} секунд")

        if not parts:
            return "0 секунд"
        return sign + ' '.join(parts)

    def run_optimization(self):
        if self.orders_df is None or self.resources_df is None or self.processing_df is None:
            QMessageBox.warning(self, "Предупреждение", "Сначала загрузите данные.")
            return
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        QApplication.processEvents()

        try:
            horizon = self.spin_horizon.value()
            self.optimizer = create_optimizer_from_dataframes(
                self.orders_df, self.resources_df, self.processing_df,
                emergency_stops=self.emergency_stops,
                planning_horizon=horizon,
                order_prices=self.order_prices
            )
            if self.changeover_costs:
                self.optimizer.set_changeover_costs(self.changeover_costs)
            opt_type = self.combo_optimization_type.currentText()
            if opt_type == "Максимизация прибыли":
                self.plan = self.optimizer.optimize()
            else:
                self.plan = self.optimizer.optimize_makespan()
            self.display_plan()
            self.gantt.update_gantt(self.plan)
            self.btn_export.setEnabled(True)
            self.btn_compare.setEnabled(True)
            self.btn_export_initial.setEnabled(True)
            if opt_type == "Максимизация прибыли":
                msg = f"Получен план с общей прибылью: {self.plan.total_profit:.2f}"
            else:
                if self.plan.assignments:
                    opt_makespan = max(a.end_time for a in self.plan.assignments)
                else:
                    opt_makespan = None
                if self.initial_plan and self.initial_plan.assignments:
                    init_makespan = max(a.end_time for a in self.initial_plan.assignments)
                    if opt_makespan and init_makespan:
                        diff = init_makespan - opt_makespan
                        if diff.total_seconds() > 0:
                            formatted = self._format_timedelta_ru(diff)
                            msg = f"Время оптимизированного производства сократилось на {formatted} по отношению к исходному варианту."
                        elif diff.total_seconds() < 0:
                            formatted = self._format_timedelta_ru(-diff)  
                            msg = f"Время оптимизированного производства увеличилось на {formatted} по отношению к исходному варианту."
                        else:
                            msg = "Время производства осталось неизменным."
                    else:
                        msg = f"Максимальное время окончания оптимизированного плана: {opt_makespan.strftime('%Y-%m-%d %H:%M') if opt_makespan else 'N/A'}"
                else:
                    msg = f"Максимальное время окончания оптимизированного плана: {opt_makespan.strftime('%Y-%m-%d %H:%M') if opt_makespan else 'N/A'}"
            QMessageBox.information(self, "Оптимизация завершена", msg)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка оптимизации", str(e))
        finally:
            self.progress.setVisible(False)

    def export_initial_plan(self):
        if self.initial_plan is None:
            QMessageBox.warning(self, "Предупреждение", "Исходный план не построен.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Сохранить исходный план", "", "Excel Files (*.xlsx)")
        if not filename:
            return
        try:
            from core.exporter import export_plan_to_excel
            export_plan_to_excel(self.initial_plan, filename)
            QMessageBox.information(self, "Экспорт", f"Исходный план сохранен в {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка экспорта", str(e))

    def compare_plans(self):
        if self.initial_plan is None:
            QMessageBox.warning(self, "Предупреждение", "Исходный план не построен.")
            return
        if self.plan is None:
            QMessageBox.warning(self, "Предупреждение", "Оптимизированный план не построен.")
            return
        initial_count = len(self.initial_plan.assignments)
        optimized_count = len(self.plan.assignments)
        initial_makespan = max((a.end_time for a in self.initial_plan.assignments), default=None)
        optimized_makespan = max((a.end_time for a in self.plan.assignments), default=None)
        initial_total_labor = sum(a.labor_hours for a in self.initial_plan.assignments)
        optimized_total_labor = sum(a.labor_hours for a in self.plan.assignments)

        msg = f"""
        Сравнение планов:
        -------------------------
        Исходный план:
          - Количество назначений: {initial_count}
          - Общая трудоемкость: {initial_total_labor:.2f} ч
          - Максимальное время окончания: {initial_makespan.strftime('%Y-%m-%d %H:%M') if initial_makespan else 'N/A'}
        -------------------------
        Оптимизированный план:
          - Количество назначений: {optimized_count}
          - Общая трудоемкость: {optimized_total_labor:.2f} ч
          - Максимальное время окончания: {optimized_makespan.strftime('%Y-%m-%d %H:%M') if optimized_makespan else 'N/A'}
          - Общая прибыль: {self.plan.total_profit:.2f}
        """
        QMessageBox.information(self, "Сравнение планов", msg)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()