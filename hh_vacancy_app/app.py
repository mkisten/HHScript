import sys
import os
import json
import webbrowser
import threading
import logging
from datetime import datetime, timedelta

import requests
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView, QCheckBox, QSpinBox,
    QFrame
)
from PySide6.QtCore import Qt, Signal, QObject, QThread
from PySide6.QtGui import QDesktopServices, QColor, QPalette, QFont

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

DATA_FILE = "vacancies_data.json"
SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "query": "Java разработчик",
    "exclude": "Android, QA, Тестировщик, Аналитик, C#, архитектор, PHP, Fullstack, 1С, Python, Frontend-разработчик",
    "days": 1,
    "theme": "light"
}


# Worker для фонового обновления
class UpdateWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def run(self):
        try:
            logger.info("Фоновый поток: начало получения вакансий")

            current_vacancies = []
            if os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, 'r', encoding='utf-8') as f:
                        current_vacancies = json.load(f)
                    logger.debug(f"Загружено {len(current_vacancies)} вакансий из файла")
                except Exception as e:
                    logger.error(f"Ошибка загрузки из файла: {e}")

            old_links = {v['link'] for v in current_vacancies}

            new_vacancies = self.get_vacancies_from_api()
            truly_new = [v for v in new_vacancies if v['link'] not in old_links]

            logger.info(f"Найдено {len(truly_new)} новых вакансий")

            if truly_new:
                all_vacancies = current_vacancies + truly_new
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_vacancies, f, ensure_ascii=False, indent=2)
                logger.info("Вакансии сохранены в файл")

            self.finished.emit(truly_new)

        except Exception as e:
            logger.exception("Ошибка в фоновом потоке")
            self.error.emit(str(e))

    def get_vacancies_from_api(self):
        date_from = (datetime.now() - timedelta(days=int(self.settings['days']))).strftime("%Y-%m-%dT%H:%M:%S")

        exclude_list = [w.strip() for w in self.settings['exclude'].split(',') if w.strip()]
        exclude_str = " NOT ".join(exclude_list)
        search_text = f"{self.settings['query']} NOT {exclude_str}" if exclude_str else self.settings['query']

        logger.debug(f"Поисковый запрос: {search_text}")

        params = {
            "text": search_text,
            "area": [113, 16],
            "schedule": "remote",
            "per_page": 50,
            "page": 0,
            "date_from": date_from,
            "professional_role": 96
        }

        vacancies = []
        API_URL = "https://api.hh.ru/vacancies"
        max_pages = 5

        while params["page"] < max_pages:
            try:
                logger.debug(f"Запрос страницы {params['page'] + 1}")
                resp = requests.get(API_URL, params=params, timeout=10)

                if resp.status_code != 200:
                    logger.warning(f"API вернул статус {resp.status_code}")
                    break

                data = resp.json()
                items = data.get("items", [])
                logger.debug(f"Получено {len(items)} вакансий на странице {params['page'] + 1}")

                for item in items:
                    salary_info = item.get("salary")
                    if salary_info:
                        s_from = salary_info.get('from') or ''
                        s_to = salary_info.get('to') or ''
                        curr = salary_info.get('currency') or ''
                        salary_parts = []
                        if s_from: salary_parts.append(str(s_from))
                        if s_to: salary_parts.append(str(s_to))
                        salary = " - ".join(salary_parts)
                        if curr: salary += f" {curr}"
                        if not salary: salary = "не указана"
                    else:
                        salary = "не указана"

                    raw_date = item.get("published_at")
                    date_str = raw_date[:10] if isinstance(raw_date, str) and len(raw_date) >= 10 else ''

                    vacancies.append({
                        "title": item.get("name", "-"),
                        "company": item.get("employer", {}).get("name", "-"),
                        "city": item.get("area", {}).get("name", "-"),
                        "salary": salary,
                        "date": date_str,
                        "link": item.get("alternate_url", "#"),
                        "status": "NEW"
                    })

                if params["page"] >= data.get("pages", 1) - 1:
                    break
                params["page"] += 1

            except Exception as e:
                logger.error(f"Ошибка при получении данных: {e}")
                break

        logger.info(f"Получено {len(vacancies)} вакансий с API")
        return vacancies


class VacancyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Java Backend Вакансии — HH.ru")
        self.resize(1400, 900)
        self.vacancies = []
        self.worker = None
        logger.info("Запуск приложения")
        self.load_settings()
        self.init_ui()
        self.apply_theme()
        self.load_vacancies_from_file()
        self.update_table()

    def load_settings(self):
        logger.info("Загрузка настроек")
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
                logger.info("Настройки загружены из файла")
            except Exception as e:
                logger.error(f"Ошибка загрузки настроек: {e}")
                self.settings = DEFAULT_SETTINGS.copy()
        else:
            self.settings = DEFAULT_SETTINGS.copy()
            logger.info("Используются настройки по умолчанию")

    def save_settings(self):
        logger.info("Сохранение настроек")
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            logger.info("Настройки сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}")

    def apply_theme(self):
        app = QApplication.instance()
        app.setStyle("Fusion")

        if self.settings.get("theme") == "dark":
            # Material Dark Theme
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor("#121212"))
            palette.setColor(QPalette.WindowText, QColor("#E1E1E1"))
            palette.setColor(QPalette.Base, QColor("#1E1E1E"))
            palette.setColor(QPalette.AlternateBase, QColor("#2D2D2D"))
            palette.setColor(QPalette.ToolTipBase, QColor("#2D2D2D"))
            palette.setColor(QPalette.ToolTipText, QColor("#E1E1E1"))
            palette.setColor(QPalette.Text, QColor("#E1E1E1"))
            palette.setColor(QPalette.Button, QColor("#2D2D2D"))
            palette.setColor(QPalette.ButtonText, QColor("#E1E1E1"))
            palette.setColor(QPalette.BrightText, QColor("#FF5252"))
            palette.setColor(QPalette.Link, QColor("#BB86FC"))
            palette.setColor(QPalette.Highlight, QColor("#BB86FC"))
            palette.setColor(QPalette.HighlightedText, QColor("#000000"))
            app.setPalette(palette)

            # Стили для темной темы
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #121212;
                }
                QPushButton {
                    background-color: #BB86FC;
                    color: #000000;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 24px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #D7B5FF;
                }
                QPushButton:pressed {
                    background-color: #9965E0;
                }
                QPushButton:disabled {
                    background-color: #3D3D3D;
                    color: #6D6D6D;
                }
                QLabel {
                    color: #E1E1E1;
                    font-size: 14px;
                }
                QLineEdit, QSpinBox {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    border: 2px solid #3D3D3D;
                    border-radius: 8px;
                    padding: 8px;
                    font-size: 13px;
                }
                QLineEdit:focus, QSpinBox:focus {
                    border: 2px solid #BB86FC;
                }
                QTableWidget {
                    background-color: #1E1E1E;
                    alternate-background-color: #252525;
                    color: #E1E1E1;
                    gridline-color: #3D3D3D;
                    border: none;
                    border-radius: 12px;
                }
                QTableWidget::item {
                    padding: 8px;
                }
                QTableWidget::item:selected {
                    background-color: #BB86FC;
                    color: #000000;
                }
                QHeaderView::section {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    padding: 12px;
                    border: none;
                    font-weight: bold;
                    font-size: 13px;
                }
                QCheckBox {
                    color: #E1E1E1;
                    spacing: 8px;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                    border-radius: 4px;
                    border: 2px solid #BB86FC;
                    background-color: #2D2D2D;
                }
                QCheckBox::indicator:checked {
                    background-color: #BB86FC;
                    border: 2px solid #BB86FC;
                }
                QFrame#header {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                stop:0 #6A1B9A, stop:1 #8E24AA);
                    border-radius: 0px;
                }
                QFrame#statsCard {
                    background-color: #1E1E1E;
                    border-radius: 12px;
                    border: 2px solid #2D2D2D;
                }
                QFrame#settingsCard {
                    background-color: #1E1E1E;
                    border-radius: 12px;
                    border: 2px solid #2D2D2D;
                    padding: 16px;
                }
            """)
        else:
            # Material Light Theme
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor("#F5F5F5"))
            palette.setColor(QPalette.WindowText, QColor("#212121"))
            palette.setColor(QPalette.Base, QColor("#FFFFFF"))
            palette.setColor(QPalette.AlternateBase, QColor("#FAFAFA"))
            palette.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
            palette.setColor(QPalette.ToolTipText, QColor("#212121"))
            palette.setColor(QPalette.Text, QColor("#212121"))
            palette.setColor(QPalette.Button, QColor("#FFFFFF"))
            palette.setColor(QPalette.ButtonText, QColor("#212121"))
            palette.setColor(QPalette.BrightText, QColor("#FF5252"))
            palette.setColor(QPalette.Link, QColor("#6200EE"))
            palette.setColor(QPalette.Highlight, QColor("#6200EE"))
            palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
            app.setPalette(palette)

            # Стили для светлой темы
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #F5F5F5;
                }
                QPushButton {
                    background-color: #6200EE;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 24px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #7C4DFF;
                }
                QPushButton:pressed {
                    background-color: #5600D6;
                }
                QPushButton:disabled {
                    background-color: #E0E0E0;
                    color: #9E9E9E;
                }
                QLabel {
                    color: #212121;
                    font-size: 14px;
                }
                QLineEdit, QSpinBox {
                    background-color: #FFFFFF;
                    color: #212121;
                    border: 2px solid #E0E0E0;
                    border-radius: 8px;
                    padding: 8px;
                    font-size: 13px;
                }
                QLineEdit:focus, QSpinBox:focus {
                    border: 2px solid #6200EE;
                }
                QTableWidget {
                    background-color: #FFFFFF;
                    alternate-background-color: #FAFAFA;
                    color: #212121;
                    gridline-color: #E0E0E0;
                    border: none;
                    border-radius: 12px;
                }
                QTableWidget::item {
                    padding: 8px;
                }
                QTableWidget::item:selected {
                    background-color: #6200EE;
                    color: #FFFFFF;
                }
                QHeaderView::section {
                    background-color: #FAFAFA;
                    color: #212121;
                    padding: 12px;
                    border: none;
                    border-bottom: 2px solid #E0E0E0;
                    font-weight: bold;
                    font-size: 13px;
                }
                QCheckBox {
                    color: #212121;
                    spacing: 8px;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                    border-radius: 4px;
                    border: 2px solid #6200EE;
                    background-color: #FFFFFF;
                }
                QCheckBox::indicator:checked {
                    background-color: #6200EE;
                    border: 2px solid #6200EE;
                }
                QFrame#header {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                stop:0 #6200EE, stop:1 #9D46FF);
                    border-radius: 0px;
                }
                QFrame#statsCard {
                    background-color: #FFFFFF;
                    border-radius: 12px;
                    border: none;
                }
                QFrame#settingsCard {
                    background-color: #FFFFFF;
                    border-radius: 12px;
                    border: none;
                    padding: 16px;
                }
            """)

    def toggle_theme(self):
        current = self.settings.get("theme", "light")
        self.settings["theme"] = "dark" if current == "light" else "light"
        self.save_settings()
        self.theme_btn.setText(f"🌙 Темная" if self.settings["theme"] == "light" else "☀️ Светлая")
        self.apply_theme()
        self.update_table()

    def init_ui(self):
        logger.info("Инициализация UI")
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Шапка с градиентом
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(120)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(30, 20, 30, 20)

        title = QLabel("☕ Java Backend Вакансии")
        title.setStyleSheet("color: white; font-size: 28px; font-weight: bold;")
        subtitle = QLabel("Удаленная работа • Россия и Беларусь")
        subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.8); font-size: 14px;")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        main_layout.addWidget(header)

        # Контент с отступами
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)

        # Статистика (карточка)
        stats_card = QFrame()
        stats_card.setObjectName("statsCard")
        stats_layout = QHBoxLayout(stats_card)
        stats_layout.setContentsMargins(24, 16, 24, 16)

        # Всего вакансий
        total_container = QVBoxLayout()
        self.total_label = QLabel("0")
        self.total_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #6200EE;" if self.settings.get(
            "theme") == "light" else "font-size: 32px; font-weight: bold; color: #BB86FC;")
        total_text = QLabel("Всего вакансий")
        total_text.setStyleSheet("font-size: 12px; opacity: 0.7;")
        total_container.addWidget(self.total_label)
        total_container.addWidget(total_text)

        # Новых
        new_container = QVBoxLayout()
        self.new_label = QLabel("0")
        self.new_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #00C853;")
        new_text = QLabel("Новых")
        new_text.setStyleSheet("font-size: 12px; opacity: 0.7;")
        new_container.addWidget(self.new_label)
        new_container.addWidget(new_text)

        stats_layout.addLayout(total_container)
        stats_layout.addSpacing(40)
        stats_layout.addLayout(new_container)
        stats_layout.addStretch()

        # Кнопки управления
        buttons_layout = QHBoxLayout()
        self.update_btn = QPushButton("🔄 Обновить")
        self.theme_btn = QPushButton(f"🌙 Темная" if self.settings.get("theme") == "light" else "☀️ Светлая")
        self.exit_btn = QPushButton("❌ Выход")

        self.update_btn.setFixedHeight(45)
        self.theme_btn.setFixedHeight(45)
        self.exit_btn.setFixedHeight(45)

        self.update_btn.clicked.connect(self.update_vacancies)
        self.exit_btn.clicked.connect(self.close)
        self.theme_btn.clicked.connect(self.toggle_theme)

        buttons_layout.addWidget(self.update_btn)
        buttons_layout.addWidget(self.theme_btn)
        buttons_layout.addWidget(self.exit_btn)
        stats_layout.addLayout(buttons_layout)

        content_layout.addWidget(stats_card)

        # Настройки поиска (карточка)
        settings_card = QFrame()
        settings_card.setObjectName("settingsCard")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(24, 16, 24, 16)
        settings_layout.setSpacing(12)

        # Заголовок настроек
        settings_title = QLabel("⚙️ Настройки поиска")
        settings_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        settings_layout.addWidget(settings_title)

        # Строка 1
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Ключевое слово:"))
        self.query_input = QLineEdit()
        self.query_input.setText(self.settings.get("query", ""))
        self.query_input.setPlaceholderText("Например: Python разработчик")
        row1.addWidget(self.query_input, 1)
        settings_layout.addLayout(row1)

        # Строка 2
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Исключить:"))
        self.exclude_input = QLineEdit()
        self.exclude_input.setText(self.settings.get("exclude", ""))
        self.exclude_input.setPlaceholderText("Через запятую: Android, QA")
        row2.addWidget(self.exclude_input, 1)

        row2.addWidget(QLabel("Период (дней):"))
        self.days_input = QSpinBox()
        self.days_input.setRange(1, 30)
        self.days_input.setValue(self.settings.get("days", 1))
        self.days_input.setFixedWidth(80)
        row2.addWidget(self.days_input)

        self.save_settings_btn = QPushButton("💾 Сохранить")
        self.save_settings_btn.setFixedHeight(35)
        self.save_settings_btn.clicked.connect(self.save_app_settings)
        row2.addWidget(self.save_settings_btn)
        settings_layout.addLayout(row2)

        content_layout.addWidget(settings_card)

        # Кнопки действий с вакансиями
        self.action_widget = QWidget()
        action_layout = QHBoxLayout(self.action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.select_all_btn = QPushButton("✅ Выбрать все новые")
        self.mark_btn = QPushButton("👁️ Пометить как просмотренные")
        self.select_all_btn.setFixedHeight(40)
        self.mark_btn.setFixedHeight(40)
        self.select_all_btn.clicked.connect(self.select_all_new)
        self.mark_btn.clicked.connect(self.mark_selected_as_old)
        action_layout.addWidget(self.select_all_btn)
        action_layout.addWidget(self.mark_btn)
        action_layout.addStretch()
        self.action_widget.hide()
        content_layout.addWidget(self.action_widget)

        # Таблица
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["", "Статус", "Название", "Компания", "Город", "Зарплата", "Дата", "Действие"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellClicked.connect(self.on_cell_click)
        content_layout.addWidget(self.table)

        main_layout.addWidget(content_widget)

    def save_app_settings(self):
        query = self.query_input.text().strip()
        exclude = self.exclude_input.text().strip()
        days = self.days_input.value()
        if not query:
            QMessageBox.warning(self, "Ошибка", "Укажите ключевое слово")
            return
        self.settings.update({"query": query, "exclude": exclude, "days": days})
        self.save_settings()
        QMessageBox.information(self, "Успех", "✅ Настройки сохранены!")

    def update_table(self):
        logger.info("Обновление таблицы")
        new_count = sum(1 for v in self.vacancies if v.get('status') == 'NEW')
        self.total_label.setText(str(len(self.vacancies)))
        self.new_label.setText(str(new_count))

        if new_count > 0:
            self.action_widget.show()
        else:
            self.action_widget.hide()

        # Сортировка
        sorted_vacancies = sorted(self.vacancies, key=lambda x: x.get('date', '') or '0000-00-00', reverse=True)
        sorted_vacancies.sort(key=lambda x: 0 if x.get('status') == 'NEW' else 1)

        self.table.setRowCount(len(sorted_vacancies))

        is_dark = self.settings.get("theme") == "dark"

        for row, v in enumerate(sorted_vacancies):
            # Чекбокс
            if v.get('status') == 'NEW':
                checkbox = QCheckBox()
                self.table.setCellWidget(row, 0, checkbox)
            else:
                self.table.setItem(row, 0, QTableWidgetItem(""))

            # Статус
            status_text = "🆕 Новая" if v.get('status') == 'NEW' else "👁️ Просмотрена"
            status_item = QTableWidgetItem(status_text)

            if v.get('status') == 'NEW':
                if is_dark:
                    status_item.setBackground(QColor("#1B5E20"))
                    status_item.setForeground(QColor("#69F0AE"))
                else:
                    status_item.setBackground(QColor("#C8E6C9"))
                    status_item.setForeground(QColor("#1B5E20"))
            else:
                if is_dark:
                    status_item.setBackground(QColor("#424242"))
                    status_item.setForeground(QColor("#BDBDBD"))
                else:
                    status_item.setBackground(QColor("#F5F5F5"))
                    status_item.setForeground(QColor("#757575"))

            font = status_item.font()
            font.setBold(True)
            status_item.setFont(font)
            self.table.setItem(row, 1, status_item)

            self.table.setItem(row, 2, QTableWidgetItem(v.get('title', '-')))
            self.table.setItem(row, 3, QTableWidgetItem(v.get('company', '-')))
            self.table.setItem(row, 4, QTableWidgetItem(v.get('city', '-')))
            self.table.setItem(row, 5, QTableWidgetItem(v.get('salary', '-')))
            self.table.setItem(row, 6, QTableWidgetItem(v.get('date', '-')))

            # Кнопка "Открыть"
            open_item = QTableWidgetItem("🔗 Открыть")
            open_item.setData(Qt.UserRole, v.get('link', ''))
            open_item.setTextAlignment(Qt.AlignCenter)
            open_item.setForeground(QColor("#BB86FC" if is_dark else "#6200EE"))
            font = open_item.font()
            font.setBold(True)
            open_item.setFont(font)
            self.table.setItem(row, 7, open_item)

        logger.info("Таблица обновлена")

    def on_cell_click(self, row, column):
        if column == 7:
            item = self.table.item(row, column)
            if item:
                link = item.data(Qt.UserRole)
                if link and link != "#":
                    logger.info(f"Открытие ссылки: {link}")
                    QDesktopServices.openUrl(link)

    def load_vacancies_from_file(self):
        logger.info("Загрузка вакансий из файла")
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.vacancies = json.load(f)
                logger.info(f"Загружено {len(self.vacancies)} вакансий из файла")
            except Exception as e:
                logger.error(f"Ошибка загрузки вакансий: {e}")
                self.vacancies = []
        else:
            self.vacancies = []
            logger.info("Файл данных не найден")

    def save_vacancies_to_file(self):
        logger.info("Сохранение вакансий в файл")
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.vacancies, f, ensure_ascii=False, indent=2)
            logger.info("Вакансии сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения вакансий: {e}")

    def update_vacancies(self):
        logger.info("Нажата кнопка 'Обновить'")
        self.update_btn.setEnabled(False)
        self.update_btn.setText("⏳ Обновление...")

        self.worker = UpdateWorker(self.settings.copy())
        self.worker.finished.connect(self.on_update_finished)
        self.worker.error.connect(self.on_update_error)
        self.worker.start()

    def on_update_finished(self, truly_new):
        logger.info(f"Обновление завершено: {len(truly_new)} новых вакансий")

        self.vacancies.extend(truly_new)
        self.update_table()

        self.update_btn.setEnabled(True)
        self.update_btn.setText("🔄 Обновить")

        if truly_new:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Успех")
            msg.setText(f"✅ Найдено {len(truly_new)} новых вакансий!")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
        else:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Информация")
            msg.setText("ℹ️ Нет новых вакансий")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()

    def on_update_error(self, error_msg):
        logger.error(f"Ошибка обновления: {error_msg}")
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Ошибка")
        msg.setText(f"❌ Ошибка при обновлении:\n{error_msg}")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

        self.update_btn.setEnabled(True)
        self.update_btn.setText("🔄 Обновить")

    def select_all_new(self):
        logger.info("Выбор всех новых вакансий")
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and "Новая" in item.text():
                checkbox = self.table.cellWidget(row, 0)
                if checkbox:
                    checkbox.setChecked(True)

    def mark_selected_as_old(self):
        logger.info("Пометка выбранных как просмотренные")
        updated = 0
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                link_item = self.table.item(row, 7)
                link = link_item.data(Qt.UserRole) if link_item else ""
                if link:
                    for v in self.vacancies:
                        if v.get('link') == link:
                            v['status'] = 'OLD'
                            updated += 1
                            break

        if updated > 0:
            self.save_vacancies_to_file()
            self.update_table()
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Успех")
            msg.setText(f"✅ Помечено {updated} вакансий как просмотренные")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
        else:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Внимание")
            msg.setText("⚠️ Не выбрано ни одной вакансии")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()


if __name__ == "__main__":
    logger.info("Запуск основного цикла приложения")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = VacancyApp()
    window.show()
    sys.exit(app.exec())