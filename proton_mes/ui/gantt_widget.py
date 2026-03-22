import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.patches import Rectangle
from matplotlib.dates import date2num, DateFormatter
import pandas as pd
from datetime import datetime, timedelta
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import Qt
import numpy as np


class GanttWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure, self.ax = plt.subplots(figsize=(10, 6))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.toolbar)
        self.layout.addWidget(self.canvas)
        self.setLayout(self.layout)
        self.plan = None
        self.assignments = []
        self.original_xlim = None
        self.original_ylim = None
        self.canvas.mpl_connect('scroll_event', self.on_scroll)

    def on_scroll(self, event):
        if event.inaxes != self.ax:
            return
        scale_factor = 1.2
        if event.button == 'up':
            scale_factor = 1.0 / scale_factor
        elif event.button == 'down':
            scale_factor = scale_factor
        else:
            return

        cur_xlim = self.ax.get_xlim()
        cur_ylim = self.ax.get_ylim()

        xdata = event.xdata
        ydata = event.ydata

        if xdata is None or ydata is None:
            xdata = (cur_xlim[0] + cur_xlim[1]) / 2
            ydata = (cur_ylim[0] + cur_ylim[1]) / 2

        new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
        new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

        new_xlim = (xdata - new_width / 2, xdata + new_width / 2)
        new_ylim = (ydata - new_height / 2, ydata + new_height / 2)

        self.ax.set_xlim(new_xlim)
        self.ax.set_ylim(new_ylim)
        self.canvas.draw()

    def update_gantt(self, plan):
        self.plan = plan
        self.assignments = plan.assignments if plan else []
        self._draw()

    def _draw(self):
        self.ax.clear()
        if not self.assignments:
            self.ax.text(0.5, 0.5, 'Нет данных для отображения',
                         horizontalalignment='center',
                         verticalalignment='center',
                         transform=self.ax.transAxes)
            self.canvas.draw()
            return
        
        sorted_assignments = sorted(self.assignments, key=lambda a: a.start_time)
        
        workplaces = sorted(set(a.workplace_id for a in sorted_assignments))
        wp_to_y = {wp: i for i, wp in enumerate(workplaces)}
        colors = plt.cm.tab20(np.linspace(0, 1, len(workplaces)))

        all_starts = [a.start_time for a in sorted_assignments]
        all_ends = [a.end_time for a in sorted_assignments]
        min_time = min(all_starts) if all_starts else datetime.now()
        max_time = max(all_ends) if all_ends else datetime.now() + timedelta(days=1)
        
        TIME_PADDING = 0.0001  
        BAR_HEIGHT = 0.5
        for a in sorted_assignments:
            y = wp_to_y[a.workplace_id]
            start = date2num(a.start_time)
            end = date2num(a.end_time)
            left = start + TIME_PADDING
            right = end - TIME_PADDING
            if right <= left:
                right = left + 0.0001  
            width = right - left
            self.ax.barh(y, width, left=left, height=BAR_HEIGHT,
                         color=colors[y % len(colors)],
                         edgecolor='black')
            label = f"{a.order_id}"
            self.ax.text(left + width / 2, y, label,
                         ha='center', va='center', fontsize=8, color='white')

        self.ax.set_yticks(list(wp_to_y.values()))
        self.ax.set_yticklabels(list(wp_to_y.keys()))
        self.ax.set_xlabel('Время')
        self.ax.set_ylabel('Рабочие места')
        self.ax.set_title('Диаграмма Ганта производственного плана')
        self.ax.xaxis_date()
        self.ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d %H:%M'))
        self.ax.set_xlim(date2num(min_time - timedelta(hours=1)), date2num(max_time + timedelta(hours=1)))
        self.original_xlim = self.ax.get_xlim()
        self.original_ylim = self.ax.get_ylim()
        self.ax.grid(True, axis='x', linestyle='--', alpha=0.5)
        self.figure.autofmt_xdate()
        self.figure.tight_layout()
        self.canvas.draw()

    def export_image(self, filename):
        if self.plan is None:
            return False
        self.figure.savefig(filename, dpi=300)
        return True