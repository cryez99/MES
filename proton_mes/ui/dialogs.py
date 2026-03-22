from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QDateTimeEdit, QComboBox, QPushButton,
                             QFileDialog, QMessageBox, QFormLayout, QTextEdit)
from PyQt5.QtCore import QDateTime, Qt
from core.models import EmergencyStop
import pandas as pd


class EmergencyStopDialog(QDialog):
    def __init__(self, resources_df, parent=None):
        super().__init__(parent)
        self.resources_df = resources_df
        self.stop = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Добавить аварийную остановку")
        self.setModal(True)
        layout = QFormLayout()

        self.combo_workplace = QComboBox()
        if self.resources_df is not None:
            workplaces = self.resources_df['ARBID'].dropna().unique()
            for wp in workplaces:
                self.combo_workplace.addItem(str(wp))
        layout.addRow("Рабочее место (ID):", self.combo_workplace)

        self.edit_start = QDateTimeEdit()
        self.edit_start.setDateTime(QDateTime.currentDateTime())
        self.edit_start.setCalendarPopup(True)
        layout.addRow("Время начала:", self.edit_start)

        self.edit_end = QDateTimeEdit()
        self.edit_end.setDateTime(QDateTime.currentDateTime().addDays(1))
        self.edit_end.setCalendarPopup(True)
        layout.addRow("Время окончания:", self.edit_end)

        self.edit_reason = QTextEdit()
        self.edit_reason.setMaximumHeight(80)
        layout.addRow("Причина:", self.edit_reason)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Добавить")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addRow(btn_layout)

        self.setLayout(layout)

    def accept(self):
        wp = self.combo_workplace.currentText()
        start = self.edit_start.dateTime().toPyDateTime()
        end = self.edit_end.dateTime().toPyDateTime()
        reason = self.edit_reason.toPlainText()
        if start >= end:
            QMessageBox.warning(self, "Ошибка", "Время начала должно быть раньше времени окончания.")
            return
        if not wp:
            QMessageBox.warning(self, "Ошибка", "Выберите рабочее место.")
            return
        self.stop = EmergencyStop(
            workplace_id=wp,
            start_time=start,
            end_time=end,
            reason=reason
        )
        super().accept()

    def get_stop(self):
        return self.stop


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filename = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Экспорт плана")
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Выберите файл для сохранения:"))

        self.edit_path = QLineEdit()
        self.edit_path.setReadOnly(True)
        btn_browse = QPushButton("Обзор...")
        btn_browse.clicked.connect(self.browse)

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.edit_path)
        path_layout.addWidget(btn_browse)
        layout.addLayout(path_layout)

        self.combo_format = QComboBox()
        self.combo_format.addItems(["Excel (*.xlsx)", "CSV (*.csv)"])
        layout.addWidget(QLabel("Формат:"))
        layout.addWidget(self.combo_format)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Экспорт")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def browse(self):
        fmt = self.combo_format.currentText()
        filters = fmt
        filename, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", "", filters)
        if filename:
            self.edit_path.setText(filename)

    def accept(self):
        self.filename = self.edit_path.text()
        if not self.filename:
            QMessageBox.warning(self, "Ошибка", "Укажите путь к файлу.")
            return
        super().accept()

    def get_filename(self):
        return self.filename


class ChangeoverCostDialog(QDialog):
    def __init__(self, resources_df, parent=None):
        super().__init__(parent)
        self.resources_df = resources_df
        self.costs = {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Стоимость перенакладки по рабочим местам")
        self.setModal(True)
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Укажите стоимость перенакладки (руб.) для каждого рабочего места:"))
        layout.addWidget(QLabel("Стоимость применяется при переключении между разными заказами на одном рабочем месте."))

        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Рабочее место (ID)", "Стоимость перенакладки"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        if self.resources_df is not None:
            workplaces = self.resources_df['ARBID'].dropna().unique()
            self.table.setRowCount(len(workplaces))
            for i, wp in enumerate(workplaces):
                self.table.setItem(i, 0, QTableWidgetItem(str(wp)))
                cost_item = QTableWidgetItem("0.0")
                self.table.setItem(i, 1, cost_item)

        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Сохранить")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def accept(self):
        self.costs = {}
        for i in range(self.table.rowCount()):
            wp_item = self.table.item(i, 0)
            cost_item = self.table.item(i, 1)
            if wp_item and cost_item:
                wp = wp_item.text()
                try:
                    cost = float(cost_item.text())
                except ValueError:
                    cost = 0.0
                self.costs[wp] = cost
        super().accept()

    def get_costs(self):
        return self.costs


class OrderPriceDialog(QDialog):
    def __init__(self, orders_df, parent=None):
        super().__init__(parent)
        self.orders_df = orders_df
        self.prices = {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Цены на заказы")
        self.setModal(True)
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("Укажите цену (руб.) для каждого заказа:"))
        layout.addWidget(QLabel("Если цена не указана, будет использована расчётная выручка (количество × 1000)."))

        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Заказ (ID)", "Количество", "Цена (руб.)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        if self.orders_df is not None:
            orders = self.orders_df[['order_id', 'order_qty']].drop_duplicates()
            self.table.setRowCount(len(orders))
            for i, (_, row) in enumerate(orders.iterrows()):
                order_id = str(row['order_id'])
                qty = str(row['order_qty'])
                self.table.setItem(i, 0, QTableWidgetItem(order_id))
                self.table.setItem(i, 1, QTableWidgetItem(qty))
                default_price = float(qty) * 1000 if qty.replace('.', '').isdigit() else 0.0
                price_item = QTableWidgetItem(f"{default_price:.2f}")
                self.table.setItem(i, 2, price_item)

        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Сохранить")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def accept(self):
        self.prices = {}
        for i in range(self.table.rowCount()):
            order_item = self.table.item(i, 0)
            price_item = self.table.item(i, 2)
            if order_item and price_item:
                order_id = order_item.text()
                try:
                    price = float(price_item.text())
                except ValueError:
                    price = 0.0
                self.prices[order_id] = price
        super().accept()

    def get_prices(self):
        return self.prices