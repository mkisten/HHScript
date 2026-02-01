import sys
import os
from pathlib import Path
import json
import webbrowser
import threading
import logging
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import json as jsonlib

import requests
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDialog, QAbstractItemView, QCheckBox, QSpinBox,
    QFrame, QGroupBox, QSystemTrayIcon, QMenu, QTabWidget, QComboBox, QFormLayout,
    QDateEdit
)
from PySide6.QtCore import Qt, Signal, QObject, QThread, QTimer, QDate
from PySide6.QtGui import QDesktopServices, QColor, QPalette, QFont, QIcon, QPixmap, QAction, QPainter
from PySide6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QValueAxis, QBarCategoryAxis, QCategoryAxis
# Сразу после всех импортов добавьте:
print("=" * 50)
print("СТАРТ ПРОГРАММЫ")
print("=" * 50)

def resource_path(relative_path):
    """Возвращает абсолютный путь до ресурса, работает и в exe, и в dev-режиме"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)

print("resource_path определен")


def get_data_dir():

    app_name = "HH_Vacancy"
    data_dir = Path(os.getenv('APPDATA')) / app_name
    data_dir.mkdir(exist_ok=True)  # Создаём папку, если нет
    return data_dir

data_dir = get_data_dir()
LOG_FILE = data_dir / "app.log"  # Для лога
TOKEN_FILE = data_dir / "auth.json"

AUTH_BASE_URL = os.getenv("AUTH_SERVICE_URL", "https://api.subscriptionhhapp.ru").rstrip("/")
VACANCY_BASE_URL = os.getenv("VACANCY_SERVICE_URL", "https://vacancy.subscriptionhhapp.ru").rstrip("/")
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "hhsubscription_bot")

# Настройка логирования
try:
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(str(LOG_FILE), encoding='utf-8'),  # Изменено: путь к LOG_FILE
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("ЛОГИРОВАНИЕ ИНИЦИАЛИЗИРОВАНО")
    logger.info("=" * 50)
    print("Логирование настроено успешно")
except Exception as e:
    print(f"ОШИБКА при настройке логирования: {e}")
    import traceback
    traceback.print_exc()
    # Добавьте: logger не используется здесь, так что OK


class ApiClient:
    def __init__(self, auth_base_url, vacancy_base_url):
        self.auth_base_url = auth_base_url.rstrip("/")
        self.vacancy_base_url = vacancy_base_url.rstrip("/")
        self.session = requests.Session()
        self.token = None

    def set_token(self, token):
        self.token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def clear_token(self):
        self.token = None
        if "Authorization" in self.session.headers:
            self.session.headers.pop("Authorization")

    def _auth_headers(self):
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def create_auth_session(self, device_id):
        resp = requests.post(
            f"{self.auth_base_url}/api/telegram-auth/create-session",
            json={"deviceId": device_id},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def check_auth_status(self, session_id, device_id):
        params = {"deviceId": device_id} if device_id else {}
        resp = requests.get(
            f"{self.auth_base_url}/api/telegram-auth/status/{session_id}",
            params=params,
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_subscription_status(self):
        resp = self.session.get(
            f"{self.auth_base_url}/api/subscription/status",
            headers=self._auth_headers(),
            timeout=10
        )
        if resp.status_code == 401:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_settings(self):
        resp = self.session.get(
            f"{self.vacancy_base_url}/api/settings",
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def update_settings(self, payload):
        resp = self.session.put(
            f"{self.vacancy_base_url}/api/settings",
            json=payload,
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def search_vacancies(self, payload):
        resp = self.session.post(
            f"{self.vacancy_base_url}/api/vacancies/search",
            json=payload,
            headers=self._auth_headers(),
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def get_vacancies(self, status=None):
        params = {"status": status} if status else {}
        resp = self.session.get(
            f"{self.vacancy_base_url}/api/vacancies",
            params=params,
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def mark_multiple_viewed(self, vacancy_ids):
        resp = self.session.post(
            f"{self.vacancy_base_url}/api/vacancies/mark-multiple-viewed",
            json=vacancy_ids,
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()

    def delete_vacancy(self, vacancy_id):
        resp = self.session.delete(
            f"{self.vacancy_base_url}/api/vacancies/{vacancy_id}",
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()

    def get_current_user(self):
        resp = self.session.get(
            f"{self.auth_base_url}/api/auth/me",
            headers=self._auth_headers(),
            timeout=10
        )
        if resp.status_code == 401:
            return None
        resp.raise_for_status()
        return resp.json()

    def update_profile(self, payload):
        resp = self.session.put(
            f"{self.auth_base_url}/api/auth/profile",
            json=payload,
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_user_payments(self):
        resp = self.session.get(
            f"{self.auth_base_url}/api/payments/my-payments",
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def create_payment(self, payload):
        resp = self.session.post(
            f"{self.auth_base_url}/api/payments/create",
            json=payload,
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def check_payment_status(self, payment_id):
        resp = self.session.get(
            f"{self.auth_base_url}/api/payments/{payment_id}/status",
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def cancel_payment(self, payment_id):
        resp = self.session.post(
            f"{self.auth_base_url}/api/payments/{payment_id}/cancel",
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_admin_users(self):
        resp = self.session.get(
            f"{self.auth_base_url}/api/admin/all-users",
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def update_admin_user(self, telegram_id, payload):
        resp = self.session.put(
            f"{self.auth_base_url}/api/admin/users/{telegram_id}",
            json=payload,
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def extend_subscription(self, payload):
        resp = self.session.post(
            f"{self.auth_base_url}/api/admin/extend-subscription",
            json=payload,
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def set_user_role(self, telegram_id, role):
        resp = self.session.post(
            f"{self.auth_base_url}/api/admin/users/{telegram_id}/role",
            params={"role": role},
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def delete_user(self, telegram_id):
        resp = self.session.delete(
            f"{self.auth_base_url}/api/admin/users/{telegram_id}",
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_admin_stats(self):
        resp = self.session.get(
            f"{self.auth_base_url}/api/admin/stats",
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_admin_payment_stats(self):
        resp = self.session.get(
            f"{self.auth_base_url}/api/admin/payments/stats",
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_admin_payments(self, status=None, page=0, size=20):
        params = {"status": status, "page": page, "size": size}
        resp = self.session.get(
            f"{self.auth_base_url}/api/admin/payments/all",
            params=params,
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def verify_admin_payment(self, payment_id, notes=None):
        resp = self.session.post(
            f"{self.auth_base_url}/api/admin/payments/{payment_id}/verify",
            params={"notes": notes or ""},
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def reject_admin_payment(self, payment_id, reason):
        resp = self.session.post(
            f"{self.auth_base_url}/api/admin/payments/{payment_id}/reject",
            params={"reason": reason},
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_bot_stats(self):
        resp = self.session.get(
            f"{self.auth_base_url}/api/admin/bot/stats",
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def bot_control(self, action):
        resp = self.session.post(
            f"{self.auth_base_url}/api/admin/bot/control",
            json={"action": action},
            headers=self._auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def bot_broadcast(self, message):
        resp = self.session.post(
            f"{self.auth_base_url}/api/admin/bot/broadcast",
            json={"message": message},
            headers=self._auth_headers(),
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()


class TelegramAuthDialog(QDialog):
    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.token = None
        self.session_id = None
        self.device_id = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_status)

        self.setWindowTitle("Авторизация через Telegram")
        self.setModal(True)
        self.resize(420, 260)

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Создаем сессию авторизации...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.link_label = QLabel("")
        self.link_label.setWordWrap(True)
        layout.addWidget(self.link_label)

        self.open_btn = QPushButton("Открыть Telegram")
        self.open_btn.clicked.connect(self.open_telegram)
        self.open_btn.setEnabled(False)
        layout.addWidget(self.open_btn)

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.reject)
        layout.addWidget(self.cancel_btn)

        self.start_auth()

    def start_auth(self):
        try:
            self.device_id = f"desktop-{uuid.uuid4().hex[:8]}"
            session = self.api_client.create_auth_session(self.device_id)
            self.session_id = session.get("sessionId")

            safe_device = self.device_id.replace("_", "-")
            deep_link = f"https://t.me/hhsubscription_bot?start=auth_{self.session_id}_{safe_device}"
            self.link_label.setText(f"Ссылка для входа:\n{deep_link}")
            self.open_btn.setEnabled(True)
            self.status_label.setText("Ожидаем подтверждение в Telegram...")

            self.timer.start(2000)
        except Exception as e:
            self.status_label.setText(f"Ошибка авторизации: {e}")

    def open_telegram(self):
        if self.link_label.text():
            link = self.link_label.text().split("\n")[-1].strip()
            webbrowser.open(link)

    def poll_status(self):
        try:
            status = self.api_client.check_auth_status(self.session_id, self.device_id)
            status_value = status.get("status")
            token = status.get("token") or status.get("jwtToken")

            if status_value == "COMPLETED" and token:
                self.token = token
                self.timer.stop()
                self.accept()
            elif status_value in ("EXPIRED", "NOT_FOUND", "INVALID_DEVICE", "ERROR"):
                self.timer.stop()
                self.status_label.setText(status.get("message") or "Сессия истекла")
        except Exception as e:
            logger.warning(f"Ошибка проверки статуса: {e}")


class SubscriptionPayDialog(QDialog):
    def __init__(self, bot_username, parent=None):
        super().__init__(parent)
        self.bot_username = bot_username
        self.setWindowTitle("Продление подписки")
        self.setModal(True)
        self.resize(420, 260)

        layout = QVBoxLayout(self)
        title = QLabel("Подписка не активна")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        info = QLabel(
            "Для продолжения работы оформите подписку в Telegram-боте.\n"
            "Выберите тариф ниже:"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QHBoxLayout()
        btn_month = QPushButton("Месяц")
        btn_year = QPushButton("Год")
        btn_life = QPushButton("Навсегда")

        btn_month.clicked.connect(lambda: self.open_plan("monthly"))
        btn_year.clicked.connect(lambda: self.open_plan("yearly"))
        btn_life.clicked.connect(lambda: self.open_plan("lifetime"))

        buttons.addWidget(btn_month)
        buttons.addWidget(btn_year)
        buttons.addWidget(btn_life)
        layout.addLayout(buttons)

        open_bot_btn = QPushButton("Открыть бота")
        open_bot_btn.clicked.connect(self.open_bot)
        layout.addWidget(open_bot_btn)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def open_plan(self, plan):
        link = f"https://t.me/{self.bot_username}?start=sub_{plan}"
        webbrowser.open(link)

    def open_bot(self):
        webbrowser.open(f"https://t.me/{self.bot_username}")


class PaymentCreateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Создать платеж")
        self.setModal(True)
        self.resize(380, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.plan_combo = QComboBox()
        self.plan_combo.addItems(["MONTHLY", "YEARLY", "LIFETIME"])
        form.addRow("Тариф:", self.plan_combo)

        self.months_spin = QSpinBox()
        self.months_spin.setRange(1, 12)
        self.months_spin.setValue(1)
        form.addRow("Месяцев:", self.months_spin)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.create_btn = QPushButton("Создать")
        self.cancel_btn = QPushButton("Отмена")
        self.create_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.create_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

    def get_payload(self):
        return {
            "plan": self.plan_combo.currentText(),
            "months": self.months_spin.value()
        }


class SubscriptionExtendDialog(QDialog):
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Продлить подписку")
        self.setModal(True)
        self.resize(420, 260)
        self.user = user

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.plan_combo = QComboBox()
        self.plan_combo.addItems(["MONTHLY", "YEARLY", "LIFETIME", "TRIAL"])
        current_plan = (user.get("subscriptionPlan") or "MONTHLY").upper()
        index = self.plan_combo.findText(current_plan)
        if index >= 0:
            self.plan_combo.setCurrentIndex(index)
        form.addRow("Тариф:", self.plan_combo)

        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 36500)
        self.days_spin.setValue(30)
        form.addRow("Дней:", self.days_spin)

        self.use_date_checkbox = QCheckBox("Использовать дату")
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate().addDays(30))
        self.end_date_edit.setEnabled(False)
        self.use_date_checkbox.toggled.connect(self.end_date_edit.setEnabled)
        form.addRow(self.use_date_checkbox, self.end_date_edit)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Продлить")
        self.cancel_btn = QPushButton("Отмена")
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

    def get_payload(self):
        days = self.days_spin.value()
        if self.use_date_checkbox.isChecked():
            target = self.end_date_edit.date()
            delta = QDate.currentDate().daysTo(target)
            days = max(0, delta)
        return {
            "telegramId": self.user.get("telegramId"),
            "days": days,
            "plan": self.plan_combo.currentText()
        }


class SubscriptionPlanDialog(QDialog):
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Применить тариф")
        self.setModal(True)
        self.resize(360, 200)
        self.user = user

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.plan_combo = QComboBox()
        self.plan_combo.addItems(["MONTHLY", "YEARLY", "LIFETIME", "TRIAL"])
        form.addRow("Тариф:", self.plan_combo)

        self.days_label = QLabel("30")
        form.addRow("Дней будет:", self.days_label)
        self.plan_combo.currentTextChanged.connect(self.update_days_label)
        self.update_days_label(self.plan_combo.currentText())

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.apply_btn = QPushButton("Применить")
        self.cancel_btn = QPushButton("Отмена")
        self.apply_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

    def update_days_label(self, plan):
        days = 30
        if plan == "YEARLY":
            days = 365
        elif plan == "LIFETIME":
            days = 36500
        elif plan == "TRIAL":
            days = 7
        self.days_label.setText(str(days))

    def get_payload(self):
        plan = self.plan_combo.currentText()
        days = int(self.days_label.text())
        return {
            "subscriptionPlan": plan,
            "subscriptionDays": days
        }


class AdminUserEditDialog(QDialog):
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование пользователя")
        self.setModal(True)
        self.resize(460, 320)
        self.user = user

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.first_name = QLineEdit(user.get("firstName") or "")
        self.last_name = QLineEdit(user.get("lastName") or "")
        self.username = QLineEdit(user.get("username") or "")
        self.email = QLineEdit(user.get("email") or "")
        self.phone = QLineEdit(user.get("phone") or "")

        self.subscription_days = QSpinBox()
        self.subscription_days.setRange(0, 36500)
        self.subscription_days.setValue(int(user.get("daysRemaining") or 0))

        self.subscription_plan = QComboBox()
        self.subscription_plan.addItems(["MONTHLY", "YEARLY", "LIFETIME", "TRIAL"])
        current_plan = (user.get("subscriptionPlan") or "MONTHLY").upper()
        index = self.subscription_plan.findText(current_plan)
        if index >= 0:
            self.subscription_plan.setCurrentIndex(index)

        self.role_combo = QComboBox()
        self.role_combo.addItems(["USER", "ADMIN", "MODERATOR"])
        current_role = (user.get("role") or "USER").upper()
        role_index = self.role_combo.findText(current_role)
        if role_index >= 0:
            self.role_combo.setCurrentIndex(role_index)

        form.addRow("Имя:", self.first_name)
        form.addRow("Фамилия:", self.last_name)
        form.addRow("Username:", self.username)
        form.addRow("Email:", self.email)
        form.addRow("Телефон:", self.phone)
        form.addRow("Дней подписки:", self.subscription_days)
        form.addRow("Тариф:", self.subscription_plan)
        form.addRow("Роль:", self.role_combo)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Сохранить")
        self.cancel_btn = QPushButton("Отмена")
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

    def get_payload(self):
        return {
            "firstName": self.first_name.text().strip() or None,
            "lastName": self.last_name.text().strip() or None,
            "username": self.username.text().strip() or None,
            "email": self.email.text().strip() or None,
            "phone": self.phone.text().strip() or None,
            "subscriptionDays": self.subscription_days.value(),
            "subscriptionPlan": self.subscription_plan.currentText()
        }

    def get_role(self):
        return self.role_combo.currentText()


DEFAULT_SETTINGS = {
    "query": "Java разработчик",
    "exclude": "Android, QA, Тестировщик, Аналитик, C#, архитектор, PHP, Fullstack, 1С, Python, Frontend-разработчик",
    "days": 1,
    "theme": "light",
    "work_types": {
        "remote": True,
        "hybrid": False,
        "office": False
    },
    "countries": {
        "russia": True,
        "belarus": True
    },
    "auto_update": {
        "enabled": False,
        "interval_minutes": 30
    },
    "telegram_notify": False,
    "stats_mode": "Вакансии по часам (за день)",
    "stats_date": None
}

# Worker для фонового обновления
class UpdateWorker(QThread):
    finished = Signal(list, int)
    error = Signal(str)

    def __init__(self, auth_token, search_payload, existing_ids, do_search=True):
        super().__init__()
        self.auth_token = auth_token
        self.search_payload = search_payload
        self.existing_ids = existing_ids
        self.do_search = do_search

    def run(self):
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            if self.do_search:
                search_resp = requests.post(
                    f"{VACANCY_BASE_URL}/api/vacancies/search",
                    json=self.search_payload,
                    headers=headers,
                    timeout=30
                )
                search_resp.raise_for_status()

            list_resp = requests.get(
                f"{VACANCY_BASE_URL}/api/vacancies",
                headers=headers,
                timeout=15
            )
            list_resp.raise_for_status()

            vacancies = list_resp.json()
            new_count = sum(1 for v in vacancies if v.get("id") not in self.existing_ids)
            self.finished.emit(vacancies, new_count)
        except Exception as e:
            logger.exception("Ошибка в фоновом потоке")
            self.error.emit(str(e))


class VacancyStreamWorker(QThread):
    new_vacancies = Signal(list)
    error = Signal(str)

    def __init__(self, auth_token, base_url):
        super().__init__()
        self.auth_token = auth_token
        self.base_url = base_url.rstrip("/")
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            with requests.get(
                f"{self.base_url}/api/vacancies/stream",
                headers=headers,
                stream=True,
                timeout=(10, None)
            ) as resp:
                resp.raise_for_status()
                buffer = ""
                for line in resp.iter_lines(decode_unicode=True):
                    if self._stop:
                        break
                    if line is None:
                        continue
                    if line == "":
                        if buffer:
                            try:
                                payload = jsonlib.loads(buffer)
                                if isinstance(payload, list):
                                    self.new_vacancies.emit(payload)
                            except Exception as e:
                                logger.warning(f"Ошибка парсинга SSE: {e}")
                            buffer = ""
                        continue
                    if line.startswith("data:"):
                        buffer += line[5:].strip()
        except Exception as e:
            self.error.emit(str(e))


class SupportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Поддержать разработчика")
        self.setModal(True)
        self.resize(400, 500)

        layout = QVBoxLayout(self)

        # Заголовок
        title_label = QLabel("<b>Спасибо, что пользуетесь 'Удобные Вакансии'!</b>")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Описание
        desc_label = QLabel("Если приложение оказалось полезным, вы можете поддержать разработчика:")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # QLabel для QR-кода
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)

        # Получаем путь к QR-коду
        qr_path = resource_path("qr-code.png")
        logger.info(f"Попытка загрузить QR-код из: {qr_path}")
        logger.info(f"Файл существует: {os.path.exists(qr_path)}")

        qr_pixmap = QPixmap(qr_path)
        if not qr_pixmap.isNull():
            scaled_pixmap = qr_pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.qr_label.setPixmap(scaled_pixmap)
            logger.info("QR-код успешно загружен")
        else:
            error_msg = f"QR-код не найден\nПуть: {qr_path}\nСуществует: {os.path.exists(qr_path)}"
            self.qr_label.setText(error_msg)
            self.qr_label.setStyleSheet("color: red; font-size: 10px;")
            logger.error(f"Не удалось загрузить QR-код из {qr_path}")
        layout.addWidget(self.qr_label)

        # Текст с пояснением и ссылками
        text_label = QLabel("""
        <br>
        Отсканируйте QR-код:<br><br>
        Любая сумма приветствуется!<br><br>
        """)
        text_label.setTextFormat(Qt.RichText)
        text_label.setOpenExternalLinks(True) # Позволяет открывать ссылки
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        # Кнопка Закрыть
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept) # Закрывает диалог
        layout.addWidget(close_button)

    # Опционально: переопределить closeEvent, если нужно что-то сделать при закрытии

class VacancyApp(QMainWindow):

    def parse_loaded_date(self, date_str):
        """Парсит строку даты загрузки в datetime, с fallback на min для сортировки."""
        if not date_str:
            return datetime.min
        try:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning(f"Неверный формат loaded_at: {date_str}")
            return datetime.min

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Удобные Вакансии — HH.ru")
        icon_path = resource_path("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            logger.info(f"Иконка приложения загружена: {icon_path}")
        else:
            logger.warning(f"Иконка приложения {icon_path} не найдена")
        self.resize(1500, 900)
        self.vacancies = []
        self.worker = None
        self.auto_update_timer = QTimer(self)
        self.auto_update_timer.timeout.connect(self.auto_update_check)
        self.stream_retry_timer = QTimer(self)
        self.stream_retry_timer.setSingleShot(True)
        self.stream_retry_timer.timeout.connect(self.start_stream)
        logger.info("Запуск приложения")
        # print(f"DEBUG: DATA_FILE = {DATA_FILE}")
        self.api = ApiClient(AUTH_BASE_URL, VACANCY_BASE_URL)
        self.token = None
        self.current_user = None
        self.is_admin = False
        self.user_payments = []
        self.admin_users = []
        self.filtered_admin_users = []
        self.admin_payments = []
        self.stream_worker = None
        self.offline_mode = False
        self.last_auth_error = None
        self.subscription_active = False
        self.subscription_status = None
        self.user_telegram_id = None
        self.pay_dialog_shown = False
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.timeout.connect(self.try_reconnect)
        if not self.authenticate(allow_dialog=False):
            if self.last_auth_error == "invalid_token":
                if not self.authenticate(allow_dialog=True):
                    self.offline_mode = True
                    self.reconnect_timer.start(10000)
                    self.settings = DEFAULT_SETTINGS.copy()
            else:
                self.offline_mode = True
                self.reconnect_timer.start(10000)
                self.settings = DEFAULT_SETTINGS.copy()
        if not self.offline_mode:
            self.load_settings()
        self.init_ui()  # Сначала создаём UI
        self.apply_theme()
        if not self.offline_mode:
            self.refresh_account_profile()
            self.refresh_account_subscription()
            self.load_user_payments()
            if self.is_admin:
                self.load_admin_users()
                self.load_admin_payments()
                self.load_admin_stats()
                self.load_bot_stats()
        self.load_vacancies_from_file()
        self.populate_stats_dates()  # Теперь stats_date_combo уже существует
        self.on_stats_mode_changed(self.stats_mode_combo.currentText())
        self.update_table()
        self.update_stats_chart()
        if not self.offline_mode:
            self.setup_auto_update()
        self.apply_subscription_state()
        self.update_connection_state()
        if not self.offline_mode:
            self.start_stream()

        self.update_vacancies()

        self.tray_icon = None
        self.setup_system_tray()

    def setup_system_tray(self):
        """Настройка системного трея"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("Системный трей не поддерживается на этой платформе")
            QMessageBox.warning(self, "Предупреждение",
                                "Системный трей не поддерживается. Приложение будет закрываться при нажатии на крестик.")
            return

        self.tray_icon = QSystemTrayIcon(self)
        tray_icon_path = resource_path("icon.png")
        if os.path.exists(tray_icon_path):
            self.tray_icon.setIcon(QIcon(tray_icon_path))
            logger.info(f"Иконка трея загружена: {tray_icon_path}")
        else:
            logger.warning(f"Иконка трея {tray_icon_path} не найдена, используется стандартная иконка")
            self.tray_icon.setIcon(self.windowIcon() or QIcon())

        self.tray_icon.setToolTip("Удобные Вакансии")

        tray_menu = QMenu()

        show_action = QAction("Показать", self)
        show_action.triggered.connect(self.show_and_restore)
        tray_menu.addAction(show_action)

        update_action = QAction("Обновить вакансии", self)
        update_action.triggered.connect(self.update_vacancies)
        tray_menu.addAction(update_action)

        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close_application)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)

        self.tray_icon.show()
        if self.tray_icon.isVisible():
            logger.info("Иконка системного трея успешно отображается")
        else:
            logger.error("Иконка системного трея не отображается, проверьте настройки Windows 11")

    def start_stream(self):
        if self.stream_worker and self.stream_worker.isRunning():
            return
        if not self.token:
            return
        self.stream_worker = VacancyStreamWorker(self.token, VACANCY_BASE_URL)
        self.stream_worker.new_vacancies.connect(self.on_stream_vacancies)
        self.stream_worker.error.connect(self.on_stream_error)
        self.stream_worker.finished.connect(self.schedule_stream_reconnect)
        self.stream_worker.start()

    def stop_stream(self):
        if self.stream_worker:
            self.stream_worker.stop()
            self.stream_worker.wait(1000)
            self.stream_worker = None

    def schedule_stream_reconnect(self):
        if self.stream_retry_timer.isActive():
            return
        self.stream_retry_timer.start(5000)

    def on_stream_vacancies(self, vacancies):
        try:
            normalized = [self.normalize_vacancy(v) for v in vacancies]
            existing_ids = {v.get("id") for v in self.vacancies}
            new_items = [v for v in normalized if v.get("id") not in existing_ids]
            if not new_items:
                return
            self.vacancies.extend(new_items)
            self.populate_stats_dates()
            self.update_table()
            self.update_stats_chart()
        except Exception as e:
            logger.warning(f"Ошибка обновления из SSE: {e}")

    def on_stream_error(self, message):
        logger.warning(f"SSE поток завершился: {message}")
        self.schedule_stream_reconnect()

    def load_token(self):
        if not TOKEN_FILE.exists():
            return None
        try:
            data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            return data.get("token")
        except Exception as e:
            logger.warning(f"Не удалось прочитать токен: {e}")
            return None

    def save_token(self, token):
        TOKEN_FILE.write_text(json.dumps({"token": token}), encoding="utf-8")

    def authenticate(self, allow_dialog=True):
        self.last_auth_error = None
        token = self.load_token()
        if token:
            self.api.set_token(token)
            try:
                status = self.api.get_subscription_status()
                if status:
                    self.token = token
                    self.subscription_status = status
                    self.subscription_active = bool(status.get("active"))
                    self.user_telegram_id = status.get("telegramId")
                    self.load_current_user()
                    return True
                self.last_auth_error = "invalid_token"
                self.api.clear_token()
                self.token = None
            except requests.exceptions.RequestException as e:
                logger.warning(f"Сервер недоступен: {e}")
                self.last_auth_error = "network"
                return False

        if not allow_dialog:
            return False

        dialog = TelegramAuthDialog(self.api, self)
        if dialog.exec() != QDialog.Accepted or not dialog.token:
            return False

        self.token = dialog.token
        self.api.set_token(self.token)
        self.save_token(self.token)

        try:
            status = self.api.get_subscription_status()
            if status:
                self.subscription_status = status
                self.subscription_active = bool(status.get("active"))
                self.user_telegram_id = status.get("telegramId")
                self.load_current_user()
            else:
                self.subscription_active = False
                self.last_auth_error = "invalid_token"
                self.api.clear_token()
                self.token = None
                return False
        except requests.exceptions.RequestException as e:
            logger.warning(f"Сервер недоступен: {e}")
            self.last_auth_error = "network"
            return False
        return True

    def load_current_user(self):
        try:
            user = self.api.get_current_user()
            self.current_user = user
            role = (user or {}).get("role") or ""
            self.is_admin = role.upper() == "ADMIN"
        except Exception as e:
            logger.warning(f"Не удалось загрузить профиль: {e}")
            self.current_user = None
            self.is_admin = False

    def ensure_authenticated(self):
        if self.offline_mode:
            return False
        if not self.token:
            if not self.authenticate():
                return False

        status = self.api.get_subscription_status()
        if not status:
            if not self.authenticate():
                return False
            status = self.api.get_subscription_status()
            if not status:
                return False

        self.subscription_status = status
        self.subscription_active = bool(status.get("active"))
        self.user_telegram_id = status.get("telegramId")
        self.load_current_user()
        if hasattr(self, "profile_first_name"):
            self.refresh_account_profile()
        self.apply_subscription_state()
        return True

    def try_reconnect(self):
        if not self.offline_mode:
            return
        if self.authenticate(allow_dialog=False):
            self.offline_mode = False
            self.reconnect_timer.stop()
            self.load_settings()
            self.refresh_account_profile()
            self.refresh_account_subscription()
            self.load_user_payments()
            if self.is_admin:
                self.load_admin_users()
                self.load_admin_payments()
                self.load_admin_stats()
                self.load_bot_stats()
            self.load_vacancies_from_file()
            self.populate_stats_dates()
            self.update_table()
            self.update_stats_chart()
            self.setup_auto_update()
            self.apply_subscription_state()
            self.update_connection_state()
            self.start_stream()

    def update_connection_state(self):
        if self.offline_mode:
            self.sub_status_label.setText("Нет соединения с сервером")
            self.sub_plan_label.setText("Проверьте подключение")
            controls = [
                self.update_btn,
                self.search_btn,
                self.save_settings_btn,
                self.query_input,
                self.days_input,
                self.remote_checkbox,
                self.hybrid_checkbox,
                self.office_checkbox,
                self.russia_checkbox,
                self.belarus_checkbox,
                self.auto_update_checkbox,
                self.auto_update_interval,
                self.telegram_notify_checkbox,
                self.exclude_input
            ]
            for control in controls:
                control.setEnabled(False)
        else:
            self.apply_subscription_state()

    def apply_subscription_state(self):
        enabled = self.subscription_active
        base_controls = [
            self.query_input,
            self.days_input,
            self.remote_checkbox,
            self.hybrid_checkbox,
            self.office_checkbox,
            self.russia_checkbox,
            self.belarus_checkbox,
            self.save_settings_btn,
            self.exclude_input,
            self.update_btn
        ]

        for control in base_controls:
            control.setEnabled(True)

        auto_controls = [
            self.auto_update_checkbox,
            self.auto_update_interval,
            self.telegram_notify_checkbox
        ]
        for control in auto_controls:
            control.setEnabled(enabled)

        self.pay_btn.setEnabled(True)

        if not enabled and not self.pay_dialog_shown:
            self.pay_dialog_shown = True
            QMessageBox.information(
                self,
                "Подписка не активна",
                "Подписка не активна. Автообновление и рассылка в Telegram отключены."
            )

        self.update_subscription_status_ui()

    def update_subscription_status_ui(self):
        if not self.subscription_status:
            self.sub_status_label.setText("Подписка: неизвестно")
            self.sub_plan_label.setText("")
            return

        active = bool(self.subscription_status.get("active"))
        days = self.subscription_status.get("daysRemaining")
        plan = self.subscription_status.get("subscriptionPlan") or "—"

        if active:
            self.sub_status_label.setText(f"Подписка активна (осталось {days} дн.)")
        else:
            self.sub_status_label.setText("Подписка не активна")

        self.sub_plan_label.setText(f"Тариф: {plan}")
        self.refresh_account_subscription()

    def open_payment_dialog(self):
        dialog = SubscriptionPayDialog(BOT_USERNAME, self)
        dialog.exec()

    def refresh_account_subscription(self):
        if not hasattr(self, "account_status_label"):
            return
        status = self.subscription_status or {}
        active = bool(status.get("active"))
        days = status.get("daysRemaining")
        plan = status.get("subscriptionPlan") or "—"
        end_date = status.get("subscriptionEndDate") or "—"
        self.account_status_label.setText("Статус: Активна" if active else "Статус: Неактивна")
        self.account_plan_label.setText(f"Тариф: {plan}")
        self.account_days_label.setText(f"Осталось дней: {days if days is not None else '—'}")
        self.account_end_label.setText(f"Дата окончания: {end_date}")

    def refresh_account_profile(self):
        if not self.current_user:
            return
        self.profile_first_name.setText(self.current_user.get("firstName") or "")
        self.profile_last_name.setText(self.current_user.get("lastName") or "")
        self.profile_username.setText(self.current_user.get("username") or "")
        self.profile_email.setText(self.current_user.get("email") or "")
        self.profile_phone.setText(self.current_user.get("phone") or "")

    def save_profile(self):
        if not self.ensure_authenticated():
            return
        payload = {
            "firstName": self.profile_first_name.text().strip(),
            "lastName": self.profile_last_name.text().strip(),
            "username": self.profile_username.text().strip(),
            "email": self.profile_email.text().strip(),
            "phone": self.profile_phone.text().strip()
        }
        try:
            self.current_user = self.api.update_profile(payload)
            self.refresh_account_profile()
            QMessageBox.information(self, "Профиль", "Профиль обновлен")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось обновить профиль: {e}")

    def load_user_payments(self):
        if not self.ensure_authenticated():
            return
        try:
            self.user_payments = self.api.get_user_payments()
            self.populate_user_payments()
        except Exception as e:
            QMessageBox.warning(self, "Платежи", f"Не удалось загрузить платежи: {e}")

    def populate_user_payments(self):
        payments = self.user_payments or []
        self.payments_table.setRowCount(len(payments))
        for row, payment in enumerate(payments):
            self.payments_table.setItem(row, 0, QTableWidgetItem(str(payment.get("id"))))
            self.payments_table.setItem(row, 1, QTableWidgetItem(str(payment.get("plan") or "")))
            self.payments_table.setItem(row, 2, QTableWidgetItem(str(payment.get("months") or "")))
            self.payments_table.setItem(row, 3, QTableWidgetItem(str(payment.get("amount") or "")))
            self.payments_table.setItem(row, 4, QTableWidgetItem(str(payment.get("status") or "")))
            self.payments_table.setItem(row, 5, QTableWidgetItem(str(payment.get("createdAt") or "")))
            self.payments_table.setItem(row, 6, QTableWidgetItem(str(payment.get("verifiedAt") or "")))
            self.payments_table.setItem(row, 7, QTableWidgetItem(str(payment.get("adminNotes") or "")))

    def create_payment(self):
        if not self.ensure_authenticated():
            return
        dialog = PaymentCreateDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            payload = dialog.get_payload()
            self.api.create_payment(payload)
            self.load_user_payments()
            QMessageBox.information(self, "Платеж", "Платеж создан")
        except Exception as e:
            QMessageBox.warning(self, "Платеж", f"Не удалось создать платеж: {e}")

    def _selected_payment_id(self):
        row = self.payments_table.currentRow()
        if row < 0:
            return None
        item = self.payments_table.item(row, 0)
        return int(item.text()) if item and item.text().isdigit() else None

    def check_selected_payment(self):
        payment_id = self._selected_payment_id()
        if not payment_id:
            QMessageBox.information(self, "Платежи", "Выберите платеж")
            return
        try:
            self.api.check_payment_status(payment_id)
            self.load_user_payments()
        except Exception as e:
            QMessageBox.warning(self, "Платежи", f"Не удалось проверить статус: {e}")

    def cancel_selected_payment(self):
        payment_id = self._selected_payment_id()
        if not payment_id:
            QMessageBox.information(self, "Платежи", "Выберите платеж")
            return
        try:
            self.api.cancel_payment(payment_id)
            self.load_user_payments()
        except Exception as e:
            QMessageBox.warning(self, "Платежи", f"Не удалось отменить платеж: {e}")

    def load_admin_users(self):
        if not self.ensure_authenticated():
            return
        try:
            response = self.api.get_admin_users()
            self.admin_users = response.get("users", []) if isinstance(response, dict) else response
            self.filtered_admin_users = list(self.admin_users)
            self.populate_admin_users()
        except Exception as e:
            QMessageBox.warning(self, "Администратор", f"Не удалось загрузить пользователей: {e}")

    def filter_admin_users(self):
        if not hasattr(self, "admin_users"):
            return
        query = self.admin_user_search.text().strip().lower()
        if not query:
            self.filtered_admin_users = list(self.admin_users)
        else:
            self.filtered_admin_users = [
                u for u in self.admin_users
                if query in str(u.get("firstName", "")).lower()
                or query in str(u.get("lastName", "")).lower()
                or query in str(u.get("username", "")).lower()
                or query in str(u.get("email", "")).lower()
            ]
        self.populate_admin_users()

    def populate_admin_users(self):
        users = getattr(self, "filtered_admin_users", [])
        self.admin_users_table.setRowCount(len(users))
        for row, user in enumerate(users):
            self.admin_users_table.setItem(row, 0, QTableWidgetItem(str(user.get("telegramId"))))
            full_name = f"{user.get('firstName') or ''} {user.get('lastName') or ''}".strip()
            self.admin_users_table.setItem(row, 1, QTableWidgetItem(full_name))
            self.admin_users_table.setItem(row, 2, QTableWidgetItem(str(user.get("username") or "")))
            self.admin_users_table.setItem(row, 3, QTableWidgetItem(str(user.get("email") or "")))
            self.admin_users_table.setItem(row, 4, QTableWidgetItem("Активна" if user.get("isActive") else "Неактивна"))
            self.admin_users_table.setItem(row, 5, QTableWidgetItem(str(user.get("subscriptionPlan") or "")))
            self.admin_users_table.setItem(row, 6, QTableWidgetItem(str(user.get("daysRemaining") or "")))
            self.admin_users_table.setItem(row, 7, QTableWidgetItem(str(user.get("role") or "")))
            self.admin_users_table.setItem(row, 8, QTableWidgetItem(str(user.get("createdAt") or "")))

    def _selected_admin_user(self):
        row = self.admin_users_table.currentRow()
        if row < 0:
            return None
        telegram_id_item = self.admin_users_table.item(row, 0)
        telegram_id = int(telegram_id_item.text()) if telegram_id_item and telegram_id_item.text().isdigit() else None
        for user in getattr(self, "admin_users", []):
            if user.get("telegramId") == telegram_id:
                return user
        return None

    def edit_selected_admin_user(self):
        user = self._selected_admin_user()
        if not user:
            QMessageBox.information(self, "Администратор", "Выберите пользователя")
            return
        dialog = AdminUserEditDialog(user, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            payload = dialog.get_payload()
            self.api.update_admin_user(user.get("telegramId"), payload)
            role = dialog.get_role()
            if role and role != user.get("role"):
                self.api.set_user_role(user.get("telegramId"), role)
            self.load_admin_users()
        except Exception as e:
            QMessageBox.warning(self, "Администратор", f"Не удалось обновить пользователя: {e}")

    def extend_selected_admin_user(self):
        user = self._selected_admin_user()
        if not user:
            QMessageBox.information(self, "Администратор", "Выберите пользователя")
            return
        dialog = SubscriptionExtendDialog(user, self)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.get_payload()
        try:
            self.api.extend_subscription(payload)
            self.load_admin_users()
        except Exception as e:
            QMessageBox.warning(self, "Администратор", f"Не удалось продлить подписку: {e}")

    def apply_plan_selected_admin_user(self):
        user = self._selected_admin_user()
        if not user:
            QMessageBox.information(self, "Администратор", "Выберите пользователя")
            return
        dialog = SubscriptionPlanDialog(user, self)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.get_payload()
        try:
            self.api.update_admin_user(user.get("telegramId"), payload)
            self.load_admin_users()
        except Exception as e:
            QMessageBox.warning(self, "Администратор", f"Не удалось применить тариф: {e}")

    def delete_selected_admin_user(self):
        user = self._selected_admin_user()
        if not user:
            QMessageBox.information(self, "Администратор", "Выберите пользователя")
            return
        confirm = QMessageBox.question(
            self,
            "Удаление пользователя",
            f"Удалить пользователя {user.get('telegramId')}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.api.delete_user(user.get("telegramId"))
            self.load_admin_users()
        except Exception as e:
            QMessageBox.warning(self, "Администратор", f"Не удалось удалить пользователя: {e}")

    def logout(self):
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        self.token = None
        self.api.clear_token()
        self.stop_stream()
        self.subscription_status = None
        self.subscription_active = False
        self.current_user = None
        self.is_admin = False
        self.pay_dialog_shown = False
        self.offline_mode = False
        self.reconnect_timer.stop()
        QMessageBox.information(self, "Выход", "Вы вышли из профиля")
        if not self.authenticate():
            self.offline_mode = True
            self.reconnect_timer.start(10000)
            self.update_connection_state()
            return
        self.load_settings()
        self.refresh_account_profile()
        self.refresh_account_subscription()
        self.load_user_payments()
        if self.is_admin:
            self.load_admin_users()
            self.load_admin_payments()
            self.load_admin_stats()
            self.load_bot_stats()
        self.load_vacancies_from_file()
        self.populate_stats_dates()
        self.update_table()
        self.update_stats_chart()
        self.apply_subscription_state()
        self.start_stream()

    def load_admin_payments(self):
        if not self.ensure_authenticated():
            return
        status = self.admin_payment_status.currentText()
        status_param = None if status == "ALL" else status
        try:
            response = self.api.get_admin_payments(status=status_param)
            payments = response.get("payments", []) if isinstance(response, dict) else response
            self.admin_payments = payments
            self.populate_admin_payments()
        except Exception as e:
            QMessageBox.warning(self, "Администратор", f"Не удалось загрузить платежи: {e}")

    def populate_admin_payments(self):
        payments = getattr(self, "admin_payments", [])
        self.admin_payments_table.setRowCount(len(payments))
        for row, payment in enumerate(payments):
            self.admin_payments_table.setItem(row, 0, QTableWidgetItem(str(payment.get("id"))))
            self.admin_payments_table.setItem(row, 1, QTableWidgetItem(str(payment.get("telegramId") or "")))
            self.admin_payments_table.setItem(row, 2, QTableWidgetItem(str(payment.get("plan") or "")))
            self.admin_payments_table.setItem(row, 3, QTableWidgetItem(str(payment.get("months") or "")))
            self.admin_payments_table.setItem(row, 4, QTableWidgetItem(str(payment.get("amount") or "")))
            self.admin_payments_table.setItem(row, 5, QTableWidgetItem(str(payment.get("status") or "")))
            self.admin_payments_table.setItem(row, 6, QTableWidgetItem(str(payment.get("createdAt") or "")))
            self.admin_payments_table.setItem(row, 7, QTableWidgetItem(str(payment.get("adminNotes") or "")))

    def _selected_admin_payment_id(self):
        row = self.admin_payments_table.currentRow()
        if row < 0:
            return None
        item = self.admin_payments_table.item(row, 0)
        return int(item.text()) if item and item.text().isdigit() else None

    def verify_selected_payment(self):
        payment_id = self._selected_admin_payment_id()
        if not payment_id:
            QMessageBox.information(self, "Платежи", "Выберите платеж")
            return
        try:
            self.api.verify_admin_payment(payment_id, "Платеж подтвержден")
            self.load_admin_payments()
        except Exception as e:
            QMessageBox.warning(self, "Платежи", f"Не удалось подтвердить: {e}")

    def reject_selected_payment(self):
        payment_id = self._selected_admin_payment_id()
        if not payment_id:
            QMessageBox.information(self, "Платежи", "Выберите платеж")
            return
        try:
            self.api.reject_admin_payment(payment_id, "Платеж отклонен")
            self.load_admin_payments()
        except Exception as e:
            QMessageBox.warning(self, "Платежи", f"Не удалось отклонить: {e}")

    def load_admin_stats(self):
        if not self.ensure_authenticated():
            return
        try:
            stats = self.api.get_admin_stats()
            payment_stats = self.api.get_admin_payment_stats()
            details = (
                f"Всего пользователей: {stats.get('totalUsers')}\n"
                f"Активных подписок: {stats.get('activeSubscriptions')}\n"
                f"Истекших подписок: {stats.get('expiredSubscriptions')}\n"
                f"Пробный период использован: {stats.get('trialUsedCount')}\n"
                f"Платежей всего: {payment_stats.get('totalPayments')}\n"
                f"Ожидают: {payment_stats.get('pendingPayments')}\n"
                f"Подтверждены: {payment_stats.get('verifiedPayments')}\n"
                f"Отклонены: {payment_stats.get('rejectedPayments')}"
            )
            self.admin_stats_details.setText(details)
        except Exception as e:
            QMessageBox.warning(self, "Администратор", f"Не удалось загрузить статистику: {e}")

    def load_bot_stats(self):
        if not self.ensure_authenticated():
            return
        try:
            stats = self.api.get_bot_stats()
            details = (
                f"Всего пользователей: {stats.get('totalUsers')}\n"
                f"Активных сегодня: {stats.get('activeToday')}\n"
                f"Сообщений всего: {stats.get('totalMessages')}\n"
                f"Сообщений сегодня: {stats.get('messagesToday')}\n"
                f"Статус: {stats.get('botStatus')}\n"
                f"Обновлено: {stats.get('lastUpdate')}"
            )
            self.bot_stats_details.setText(details)
        except Exception as e:
            QMessageBox.warning(self, "Бот", f"Не удалось загрузить статистику: {e}")

    def control_bot(self, action):
        if not self.ensure_authenticated():
            return
        try:
            self.api.bot_control(action)
            self.load_bot_stats()
        except Exception as e:
            QMessageBox.warning(self, "Бот", f"Не удалось выполнить действие: {e}")

    def send_broadcast(self):
        message = self.broadcast_input.text().strip()
        if not message:
            QMessageBox.information(self, "Бот", "Введите текст рассылки")
            return
        try:
            self.api.bot_broadcast(message)
            QMessageBox.information(self, "Бот", "Рассылка отправлена")
        except Exception as e:
            QMessageBox.warning(self, "Бот", f"Не удалось отправить рассылку: {e}")

    def show_and_restore(self):
        """Показать и восстановить окно"""
        self.show()
        self.setWindowState(Qt.WindowNoState)
        self.raise_()
        self.activateWindow()
        logger.info("Окно приложения восстановлено из трея")

    def tray_icon_activated(self, reason):
        """Обработка событий иконки трея"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_and_restore()
            logger.info("Окно приложения открыто по двойному клику на иконке трея")

    def closeEvent(self, event):
        """Переопределение события закрытия окна"""
        logger.info("closeEvent вызвано")
        if self.tray_icon:
            logger.info(f"isVisible в closeEvent: {self.tray_icon.isVisible()}")
            self.hide()
            event.ignore()
            self.tray_icon.showMessage(
                "Удобные Вакансии",
                "Приложение свернуто в системный трей. Используйте контекстное меню для выхода.",
                QSystemTrayIcon.Information,
                3000
            )
            logger.info("Окно свернуто в системный трей")
        else:
            logger.info("Системный трей недоступен или не инициализирован, приложение будет закрыто")
            event.accept()

    def close_application(self):
        """Полное завершение приложения"""
        logger.info("Завершение приложения")
        self.auto_update_timer.stop()
        self.stop_stream()
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        if self.tray_icon:
            self.tray_icon.hide()
            logger.info("Иконка трея скрыта")
        self.close()
        QApplication.quit()

    def update_stats_chart(self):
        """Обновление графика статистики в зависимости от выбранного режима"""
        # Проверяем, что все необходимые элементы UI созданы
        if not hasattr(self, 'stats_mode_combo') or not hasattr(self, 'stats_date_combo'):
            logger.warning("Комбобоксы статистики ещё не созданы, пропускаем обновление графика")
            return

        # Проверяем наличие вакансий
        if not self.vacancies:
            logger.info("Нет вакансий для отображения на графике")
            if hasattr(self, 'chart_view') and self.chart_view:
                # Очищаем график если он уже существует
                empty_chart = QChart()
                empty_chart.setTitle("Нет данных для отображения")
                empty_chart.setTheme(
                    QChart.ChartThemeDark if self.settings.get("theme") == "dark" else QChart.ChartThemeLight)
                self.chart_view.setChart(empty_chart)
            return

        # Получаем текущий режим и выбранную дату
        mode = self.stats_mode_combo.currentText()
        selected_date = self.stats_date_combo.currentData()

        # Создаем новый график
        chart = QChart()
        chart.setAnimationOptions(QChart.SeriesAnimations)

        # Выбираем тип графика в зависимости от режима
        try:
            if mode == "Вакансии по часам (за день)":
                self._update_hourly_chart(chart, selected_date)
            elif mode == "Вакансии по дням (месяц)":
                self._update_daily_chart(chart, 30)
            elif mode == "Вакансии по дням (6 месяцев)":
                self._update_daily_chart(chart, 180)
            else:
                logger.warning(f"Неизвестный режим статистики: {mode}")
                return
        except Exception as e:
            logger.error(f"Ошибка при создании графика: {e}")
            return

        # Применяем тему
        chart.setTheme(QChart.ChartThemeDark if self.settings.get("theme") == "dark" else QChart.ChartThemeLight)

        # Создаем или обновляем виджет графика
        if not hasattr(self, 'chart_view') or self.chart_view is None:
            self.chart_view = QChartView(chart)
            self.chart_view.setRenderHint(QPainter.Antialiasing)
            if hasattr(self, 'stats_chart_layout'):
                self.stats_chart_layout.addWidget(self.chart_view)
            else:
                logger.error("stats_chart_layout не найден")
        else:
            self.chart_view.setChart(chart)

        logger.info(f"График статистики обновлен в режиме: {mode}")

    def _update_hourly_chart(self, chart, selected_date):
        """Обновление графика по часам для конкретного дня"""
        hourly_counts = defaultdict(int)

        for v in self.vacancies:
            loaded_at_str = v.get('loaded_at', '')
            if loaded_at_str:
                try:
                    loaded_dt = datetime.strptime(loaded_at_str, "%Y-%m-%d %H:%M:%S")
                    if selected_date and loaded_dt.date() == selected_date:
                        hour = loaded_dt.hour
                        hourly_counts[hour] += 1
                    elif not selected_date:
                        hour = loaded_dt.hour
                        hourly_counts[hour] += 1
                except ValueError:
                    logger.warning(f"Неверный формат loaded_at: {loaded_at_str}")

        date_str = selected_date.strftime("%d.%m.%Y") if selected_date else "все дни"
        chart.setTitle(f"Вакансии по часам ({date_str})")

        bar_set = QBarSet("Количество вакансий")

        # Добавляем значения и включаем отображение меток
        for hour in range(24):
            count = hourly_counts[hour]
            bar_set.append(count)

        # Включаем отображение значений на столбцах
        bar_set.setLabelColor(QColor("#E1E1E1") if self.settings.get("theme") == "dark" else QColor("#212121"))

        series = QBarSeries()
        series.append(bar_set)

        # Включаем отображение меток со значениями
        series.setLabelsVisible(True)
        series.setLabelsPosition(QBarSeries.LabelsOutsideEnd)
        series.setLabelsFormat("@value")

        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        categories = [f"{h}ч" for h in range(24)]
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_value = max(hourly_counts.values()) if hourly_counts else 1
        axis_y = QValueAxis()
        # Увеличиваем диапазон, чтобы метки не обрезались
        axis_y.setRange(0, max_value + max(2, int(max_value * 0.15)))
        axis_y.setTitleText("Количество")
        axis_y.setLabelFormat("%d")
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

    def _update_daily_chart(self, chart, days_count):
        """Обновление графика по дням за указанный период"""
        daily_counts = defaultdict(int)

        for v in self.vacancies:
            loaded_at_str = v.get('loaded_at', '')
            if loaded_at_str:
                try:
                    loaded_dt = datetime.strptime(loaded_at_str, "%Y-%m-%d %H:%M:%S")
                    date_key = loaded_dt.date()
                    daily_counts[date_key] += 1
                except ValueError:
                    logger.warning(f"Неверный формат loaded_at: {loaded_at_str}")

        if not daily_counts:
            chart.setTitle(f"Вакансии по дням (последние {days_count} дней) - нет данных")
            return

        end_date = max(daily_counts.keys())
        start_date = end_date - timedelta(days=days_count - 1)

        chart.setTitle(f"Вакансии по дням (последние {days_count} дней)")

        bar_set = QBarSet("Количество вакансий")
        categories = []

        current_date = start_date
        while current_date <= end_date:
            count = daily_counts.get(current_date, 0)
            bar_set.append(count)
            categories.append(current_date.strftime("%d.%m"))
            current_date += timedelta(days=1)

        # Включаем отображение значений на столбцах
        bar_set.setLabelColor(QColor("#E1E1E1") if self.settings.get("theme") == "dark" else QColor("#212121"))

        series = QBarSeries()
        series.append(bar_set)

        # Включаем отображение меток со значениями
        series.setLabelsVisible(True)
        series.setLabelsPosition(QBarSeries.LabelsOutsideEnd)
        series.setLabelsFormat("@value")

        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_value = max(bar_set.at(i) for i in range(bar_set.count())) if bar_set.count() > 0 else 1
        axis_y = QValueAxis()
        # Увеличиваем диапазон, чтобы метки не обрезались
        axis_y.setRange(0, max_value + max(2, int(max_value * 0.15)))
        axis_y.setTitleText("Количество")
        axis_y.setLabelFormat("%d")
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

    def setup_auto_update(self):
        """Настройка автообновления"""
        if not self.subscription_active:
            self.auto_update_timer.stop()
            return
        auto_update_settings = self.settings.get('auto_update', {})
        enabled = auto_update_settings.get('enabled', False)
        interval = auto_update_settings.get('interval_minutes', 30)

        self.auto_update_timer.stop()

        if enabled:
            interval_ms = interval * 60 * 1000
            self.auto_update_timer.start(interval_ms)
            logger.info(f"Автообновление включено: каждые {interval} минут")
        else:
            logger.info("Автообновление выключено")

    def auto_update_check(self):
        logger.info("Запуск автообновления")
        if self.worker and self.worker.isRunning():
            logger.info("Обновление уже выполняется, пропускаем")
            return
        if not self.ensure_authenticated():
            return
        if not self.subscription_active:
            return
        old_ids = {v['id'] for v in self.vacancies if v.get("id")}
        self.worker = UpdateWorker(self.token, None, old_ids, do_search=False)
        self.worker.finished.connect(self.on_auto_update_finished_with_server)
        self.worker.error.connect(self.on_update_error)
        self.worker.start()

    def on_auto_update_finished_with_server(self, server_vacancies, new_count):
        """Обработка результатов автообновления"""
        logger.info(f"Автообновление завершено: {new_count} новых вакансий")

        self.vacancies = [self.normalize_vacancy(v) for v in server_vacancies]
        self.populate_stats_dates()
        self.update_table()
        self.update_stats_chart()

        if new_count:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Новые вакансии!")
            msg.setText(f"Найдено {new_count} новых вакансий!")
            msg.setInformativeText("Проверьте таблицу для просмотра деталей.")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
            msg.show()
            msg.raise_()
            msg.activateWindow()
            logger.info("Показано уведомление о новых вакансиях")

    def load_settings(self):
        if self.offline_mode:
            self.settings = DEFAULT_SETTINGS.copy()
            return
        try:
            server_settings = self.api.get_settings()
            self.user_telegram_id = server_settings.get("telegramId")

            work_types = set(server_settings.get("workTypes") or [])
            countries = set(server_settings.get("countries") or [])

            self.settings = {
                "query": server_settings.get("searchQuery") or DEFAULT_SETTINGS["query"],
                "exclude": server_settings.get("excludeKeywords") or "",
                "days": server_settings.get("days") or 1,
                "work_types": {
                    "remote": "remote" in work_types,
                    "hybrid": "hybrid" in work_types,
                    "office": "office" in work_types,
                },
                "countries": {
                    "russia": "russia" in countries,
                    "belarus": "belarus" in countries,
                },
                "auto_update": {
                    "enabled": bool(server_settings.get("autoUpdateEnabled")),
                    "interval_minutes": server_settings.get("autoUpdateInterval") or 30
                },
                "telegram_notify": bool(server_settings.get("telegramNotify")),
                "theme": server_settings.get("theme") or "light",
                "stats_mode": self.settings.get("stats_mode", DEFAULT_SETTINGS["stats_mode"]) if hasattr(self, "settings") else DEFAULT_SETTINGS["stats_mode"],
                "stats_date": self.settings.get("stats_date") if hasattr(self, "settings") else None
            }
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек с сервера: {e}")
            self.settings = DEFAULT_SETTINGS.copy()

    def save_settings(self):
        if not self.ensure_authenticated():
            return

        work_types = []
        if self.settings.get("work_types", {}).get("remote"):
            work_types.append("remote")
        if self.settings.get("work_types", {}).get("hybrid"):
            work_types.append("hybrid")
        if self.settings.get("work_types", {}).get("office"):
            work_types.append("office")

        countries = []
        if self.settings.get("countries", {}).get("russia"):
            countries.append("russia")
        if self.settings.get("countries", {}).get("belarus"):
            countries.append("belarus")

        payload = {
            "telegramId": self.user_telegram_id,
            "searchQuery": self.settings.get("query"),
            "days": self.settings.get("days"),
            "excludeKeywords": self.settings.get("exclude"),
            "workTypes": work_types,
            "countries": countries,
            "telegramNotify": self.settings.get("telegram_notify", False) if self.subscription_active else False,
            "autoUpdateEnabled": self.settings.get("auto_update", {}).get("enabled", False) if self.subscription_active else False,
            "autoUpdateInterval": self.settings.get("auto_update", {}).get("interval_minutes", 30),
            "theme": self.settings.get("theme", "light")
        }

        self.api.update_settings(payload)

    def apply_theme(self):
        app = QApplication.instance()
        app.setStyle("Fusion")

        if self.settings.get("theme") == "dark":
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

            self.setStyleSheet("""
                QMainWindow {
                    background-color: #121212;
                }
                QPushButton {
                    background-color: #BB86FC;
                    color: #000000;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 20px;
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
                    font-size: 13px;
                }
                QLineEdit, QSpinBox {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    border: 2px solid #3D3D3D;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QLineEdit:focus, QSpinBox:focus {
                    border: 2px solid #BB86FC;
                }
                QComboBox {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    border: 2px solid #3D3D3D;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QComboBox:focus {
                    border: 2px solid #BB86FC;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    selection-background-color: #BB86FC;
                    selection-color: #000000;
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
                    padding: 12px 8px;
                    border: none;
                    font-weight: bold;
                    font-size: 13px;
                }
                QCheckBox {
                    color: #E1E1E1;
                    spacing: 8px;
                    padding: 4px;
                    font-size: 13px;
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
                }
                QFrame#statsChartFrame {
                    background-color: #1E1E1E;
                    border-radius: 12px;
                    border: 2px solid #2D2D2D;
                }
                QGroupBox {
                    color: #E1E1E1;
                    border: 2px solid #3D3D3D;
                    border-radius: 8px;
                    margin-top: 12px;
                    padding-top: 12px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 5px;
                }
                QTabWidget::pane {
                    border: 1px solid #3D3D3D;
                    background-color: #1E1E1E;
                }
                QTabBar::tab {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    padding: 8px 16px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #BB86FC;
                    color: #000000;
                }
                QChartView {
                    background-color: #1E1E1E;
                    border: none;
                }
            """)
        else:
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

            self.setStyleSheet("""
                QMainWindow {
                    background-color: #F5F5F5;
                }
                QPushButton {
                    background-color: #6200EE;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 20px;
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
                    font-size: 13px;
                }
                QLineEdit, QSpinBox {
                    background-color: #FFFFFF;
                    color: #212121;
                    border: 2px solid #E0E0E0;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QLineEdit:focus, QSpinBox:focus {
                    border: 2px solid #6200EE;
                }
                QComboBox {
                    background-color: #FFFFFF;
                    color: #212121;
                    border: 2px solid #E0E0E0;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QComboBox:focus {
                    border: 2px solid #6200EE;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    background-color: #FFFFFF;
                    color: #212121;
                    selection-background-color: #6200EE;
                    selection-color: #FFFFFF;
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
                    padding: 12px 8px;
                    border: none;
                    border-bottom: 2px solid #E0E0E0;
                    font-weight: bold;
                    font-size: 13px;
                }
                QCheckBox {
                    color: #212121;
                    spacing: 8px;
                    padding: 4px;
                    font-size: 13px;
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
                }
                QFrame#statsChartFrame {
                    background-color: #FFFFFF;
                    border-radius: 12px;
                    border: none;
                }
                QGroupBox {
                    color: #212121;
                    border: 2px solid #E0E0E0;
                    border-radius: 8px;
                    margin-top: 12px;
                    padding-top: 12px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 5px;
                }
                QTabWidget::pane {
                    border: 1px solid #E0E0E0;
                    background-color: #FFFFFF;
                }
                QTabBar::tab {
                    background-color: #FAFAFA;
                    color: #212121;
                    padding: 8px 16px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #6200EE;
                    color: #FFFFFF;
                }
                QChartView {
                    background-color: #FFFFFF;
                    border: none;
                }
            """)

    def toggle_theme(self):
        current = self.settings.get("theme", "light")
        self.settings["theme"] = "dark" if current == "light" else "light"
        self.save_settings()
        self.theme_btn.setText("Темная" if self.settings["theme"] == "light" else "Светлая")
        self.apply_theme()
        self.update_table()
        self.update_stats_chart()

    def init_ui(self):
        logger.info("Инициализация UI")
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        menubar = self.menuBar()
        help_menu = menubar.addMenu("Справка")
        help_menu.addAction("О программе", self.show_about_dialog)

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(80)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 15, 20, 15)

        title_layout = QVBoxLayout()
        title = QLabel("Удобные Вакансии")
        title.setStyleSheet("color: white; font-size: 22px; font-weight: bold;")
        subtitle = QLabel("Удаленная работа • Россия и Беларусь")
        subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.8); font-size: 12px;")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        status_layout = QVBoxLayout()
        self.sub_status_label = QLabel("Подписка: неизвестно")
        self.sub_status_label.setStyleSheet("color: white; font-size: 12px;")
        self.sub_plan_label = QLabel("")
        self.sub_plan_label.setStyleSheet("color: rgba(255, 255, 255, 0.8); font-size: 11px;")
        status_layout.addWidget(self.sub_status_label)
        status_layout.addWidget(self.sub_plan_label)
        header_layout.addLayout(status_layout)

        buttons_layout = QHBoxLayout()
        self.update_btn = QPushButton("Обновить")
        self.search_btn = QPushButton("Запустить поиск")
        self.pay_btn = QPushButton("Продлить")
        self.theme_btn = QPushButton("Темная" if self.settings.get("theme") == "light" else "Светлая")
        self.about_btn = QPushButton("О программе")
        self.exit_btn = QPushButton("Выход")

        self.support_btn = QPushButton("Поддержать")
        self.support_btn.setFixedHeight(40)
        self.support_btn.clicked.connect(self.show_support_dialog)

        self.update_btn.setFixedHeight(40)
        self.search_btn.setFixedHeight(40)
        self.pay_btn.setFixedHeight(40)
        self.theme_btn.setFixedSize(110, 40)
        self.about_btn.setMinimumWidth(140)
        self.about_btn.setFixedHeight(40)
        self.exit_btn.setFixedSize(110, 40)

        self.update_btn.clicked.connect(self.update_vacancies)
        self.search_btn.clicked.connect(self.run_search)
        self.pay_btn.clicked.connect(self.open_payment_dialog)
        self.exit_btn.clicked.connect(self.close_application)
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.about_btn.clicked.connect(self.show_about_dialog)

        buttons_layout.addWidget(self.update_btn)
        buttons_layout.addWidget(self.search_btn)
        buttons_layout.addWidget(self.pay_btn)
        buttons_layout.addWidget(self.theme_btn)
        buttons_layout.addWidget(self.support_btn)
        buttons_layout.addWidget(self.about_btn)
        buttons_layout.addWidget(self.exit_btn)
        header_layout.addLayout(buttons_layout)

        main_layout.addWidget(header)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 12, 15, 12)
        content_layout.setSpacing(12)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)

        # Вкладка "Вакансии"
        vacancies_tab = QWidget()
        vacancies_layout = QVBoxLayout(vacancies_tab)
        vacancies_layout.setContentsMargins(0, 0, 0, 0)
        vacancies_layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        stats_card = QFrame()
        stats_card.setObjectName("statsCard")
        stats_card.setFixedHeight(85)
        stats_layout = QHBoxLayout(stats_card)
        stats_layout.setContentsMargins(20, 12, 20, 12)

        total_layout = QVBoxLayout()
        total_layout.setSpacing(3)
        self.total_label = QLabel("0")
        self.total_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #6200EE;" if self.settings.get(
            "theme") == "light" else "font-size: 28px; font-weight: bold; color: #BB86FC;")
        total_text = QLabel("Всего")
        total_text.setStyleSheet("font-size: 11px; opacity: 0.7;")
        total_layout.addWidget(self.total_label)
        total_layout.addWidget(total_text)

        new_layout = QVBoxLayout()
        new_layout.setSpacing(3)
        self.new_label = QLabel("0")
        self.new_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #00C853;")
        new_text = QLabel("Новых")
        new_text.setStyleSheet("font-size: 11px; opacity: 0.7;")
        new_layout.addWidget(self.new_label)
        new_layout.addWidget(new_text)

        stats_layout.addLayout(total_layout)
        stats_layout.addSpacing(30)
        stats_layout.addLayout(new_layout)
        stats_layout.addStretch()

        top_row.addWidget(stats_card, 1)

        settings_card = QFrame()
        settings_card.setObjectName("settingsCard")
        settings_card.setFixedHeight(85)
        settings_layout = QHBoxLayout(settings_card)
        settings_layout.setContentsMargins(15, 12, 15, 12)
        settings_layout.setSpacing(10)

        settings_layout.addWidget(QLabel("Слово:"))
        self.query_input = QLineEdit()
        self.query_input.setText(self.settings.get("query", ""))
        self.query_input.setFixedWidth(200)
        self.query_input.setMinimumHeight(36)
        settings_layout.addWidget(self.query_input)

        settings_layout.addWidget(QLabel("Период:"))
        self.days_input = QSpinBox()
        self.days_input.setRange(1, 30)
        self.days_input.setValue(self.settings.get("days", 1))
        self.days_input.setFixedWidth(70)
        self.days_input.setMinimumHeight(32)
        settings_layout.addWidget(self.days_input)

        separator1 = QFrame()
        separator1.setFrameShape(QFrame.VLine)
        separator1.setFrameShadow(QFrame.Sunken)
        settings_layout.addWidget(separator1)

        self.remote_checkbox = QCheckBox("Удаленка")
        self.remote_checkbox.setChecked(self.settings.get('work_types', {}).get('remote', True))
        self.remote_checkbox.setMinimumHeight(25)

        self.hybrid_checkbox = QCheckBox("Гибрид")
        self.hybrid_checkbox.setChecked(self.settings.get('work_types', {}).get('hybrid', False))
        self.hybrid_checkbox.setMinimumHeight(25)

        self.office_checkbox = QCheckBox("Офис")
        self.office_checkbox.setChecked(self.settings.get('work_types', {}).get('office', False))
        self.office_checkbox.setMinimumHeight(25)

        settings_layout.addWidget(self.remote_checkbox)
        settings_layout.addWidget(self.hybrid_checkbox)
        settings_layout.addWidget(self.office_checkbox)

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setFrameShadow(QFrame.Sunken)
        settings_layout.addWidget(separator2)

        self.russia_checkbox = QCheckBox("RU")
        self.russia_checkbox.setChecked(self.settings.get('countries', {}).get('russia', True))
        self.russia_checkbox.setMinimumHeight(25)

        self.belarus_checkbox = QCheckBox("BY")
        self.belarus_checkbox.setChecked(self.settings.get('countries', {}).get('belarus', True))
        self.belarus_checkbox.setMinimumHeight(25)

        settings_layout.addWidget(self.russia_checkbox)
        settings_layout.addWidget(self.belarus_checkbox)

        separator3 = QFrame()
        separator3.setFrameShape(QFrame.VLine)
        separator3.setFrameShadow(QFrame.Sunken)
        settings_layout.addWidget(separator3)

        self.auto_update_checkbox = QCheckBox("Автообновление")
        self.auto_update_checkbox.setChecked(
            self.settings.get('auto_update', {}).get('enabled', False)
        )
        self.auto_update_checkbox.setMinimumHeight(25)
        settings_layout.addWidget(self.auto_update_checkbox)

        self.telegram_notify_checkbox = QCheckBox("Рассылка в Telegram")
        self.telegram_notify_checkbox.setChecked(self.settings.get('telegram_notify', False))
        self.telegram_notify_checkbox.setMinimumHeight(25)
        settings_layout.addWidget(self.telegram_notify_checkbox)

        self.auto_update_interval = QSpinBox()
        self.auto_update_interval.setRange(1, 1440)
        self.auto_update_interval.setValue(
            self.settings.get('auto_update', {}).get('interval_minutes', 30)
        )
        self.auto_update_interval.setSuffix(" мин")
        self.auto_update_interval.setFixedWidth(90)
        self.auto_update_interval.setMinimumHeight(32)
        settings_layout.addWidget(self.auto_update_interval)

        settings_layout.addStretch()

        self.save_settings_btn = QPushButton("Сохранить")
        self.save_settings_btn.setFixedSize(110, 38)
        self.save_settings_btn.clicked.connect(self.save_app_settings)
        settings_layout.addWidget(self.save_settings_btn)

        top_row.addWidget(settings_card, 2)
        vacancies_layout.addLayout(top_row)

        exclude_row = QHBoxLayout()
        exclude_label = QLabel("Исключить:")
        exclude_label.setFixedWidth(70)
        exclude_row.addWidget(exclude_label)

        self.exclude_input = QLineEdit()
        self.exclude_input.setText(self.settings.get("exclude", ""))
        self.exclude_input.setPlaceholderText("Через запятую: Android, QA, Тестировщик...")
        self.exclude_input.setMinimumHeight(35)
        exclude_row.addWidget(self.exclude_input)
        vacancies_layout.addLayout(exclude_row)

        self.action_widget = QWidget()
        self.action_widget.setFixedHeight(45)
        action_layout = QHBoxLayout(self.action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)

        self.select_all_btn = QPushButton("Выбрать все")
        self.mark_btn = QPushButton("Пометить просмотренными")
        self.delete_btn = QPushButton("Удалить")
        self.select_all_btn.setFixedHeight(36)
        self.mark_btn.setFixedHeight(36)
        self.delete_btn.setFixedHeight(36)
        self.select_all_btn.clicked.connect(self.select_all_new)
        self.mark_btn.clicked.connect(self.mark_selected_as_old)
        self.delete_btn.clicked.connect(self.delete_selected_vacancies)

        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItem("Все", None)
        self.status_filter_combo.addItem("Новые", "NEW")
        self.status_filter_combo.addItem("Просмотренные", "OLD")
        self.status_filter_combo.currentIndexChanged.connect(self.update_table)

        action_layout.addWidget(self.select_all_btn)
        action_layout.addWidget(self.mark_btn)
        action_layout.addWidget(self.delete_btn)
        action_layout.addStretch()
        action_layout.addWidget(QLabel("Фильтр:"))
        action_layout.addWidget(self.status_filter_combo)
        action_layout.addStretch()
        self.action_widget.hide()
        vacancies_layout.addWidget(self.action_widget)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels(
            ["", "Статус", "Название", "Компания", "Город", "Тип работы", "Зарплата", "Дата", "Дата загрузки",
             "Действие"])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 45)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, 120)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 350)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.resizeSection(5, 110)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        header.resizeSection(7, 90)
        header.setSectionResizeMode(8, QHeaderView.Fixed)
        header.resizeSection(8, 150)
        header.setSectionResizeMode(9, QHeaderView.Fixed)
        header.resizeSection(9, 160)

        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.verticalHeader().setVisible(False)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellClicked.connect(self.on_cell_click)
        self.table.setShowGrid(False)

        vacancies_layout.addWidget(self.table)
        self.tab_widget.addTab(vacancies_tab, "Вакансии")

        # Вкладка "Статистика"
        stats_tab = QWidget()
        stats_tab_layout = QVBoxLayout(stats_tab)
        stats_tab_layout.setContentsMargins(15, 12, 15, 12)
        stats_tab_layout.setSpacing(12)

        stats_control_frame = QFrame()
        stats_control_frame.setObjectName("settingsCard")
        stats_control_frame.setFixedHeight(70)
        stats_control_layout = QHBoxLayout(stats_control_frame)
        stats_control_layout.setContentsMargins(15, 10, 15, 10)
        stats_control_layout.setSpacing(15)

        stats_control_layout.addWidget(QLabel("Режим:"))
        self.stats_mode_combo = QComboBox()
        self.stats_mode_combo.addItems([
            "Вакансии по часам (за день)",
            "Вакансии по дням (месяц)",
            "Вакансии по дням (6 месяцев)"
        ])
        self.stats_mode_combo.setMinimumWidth(220)
        self.stats_mode_combo.currentTextChanged.connect(self.on_stats_mode_changed)
        stats_control_layout.addWidget(self.stats_mode_combo)

        stats_control_layout.addWidget(QLabel("Дата:"))
        self.stats_date_combo = QComboBox()
        self.stats_date_combo.setMinimumWidth(130)
        self.stats_date_combo.currentIndexChanged.connect(self.update_stats_chart)
        stats_control_layout.addWidget(self.stats_date_combo)

        self.prev_btn = QPushButton("←")
        self.prev_btn.setFixedWidth(80)
        self.prev_btn.clicked.connect(self.go_older_date)
        self.prev_btn.setVisible(False)
        stats_control_layout.addWidget(self.prev_btn)

        self.today_btn = QPushButton("Сегодня")
        self.today_btn.setFixedWidth(120)
        self.today_btn.clicked.connect(self.today_date)
        self.today_btn.setVisible(False)
        stats_control_layout.addWidget(self.today_btn)

        self.next_btn = QPushButton("→")
        self.next_btn.setFixedWidth(80)
        self.next_btn.clicked.connect(self.go_newer_date)
        self.next_btn.setVisible(False)
        stats_control_layout.addWidget(self.next_btn)

        stats_control_layout.addStretch()
        stats_tab_layout.addWidget(stats_control_frame)

        self.stats_chart_frame = QFrame()
        self.stats_chart_frame.setObjectName("statsChartFrame")
        self.stats_chart_layout = QVBoxLayout(self.stats_chart_frame)
        self.stats_chart_layout.setContentsMargins(20, 12, 20, 12)
        self.chart_view = None
        stats_tab_layout.addWidget(self.stats_chart_frame)
        self.tab_widget.addTab(stats_tab, "Статистика")

        account_tab = self.build_account_tab()
        self.tab_widget.addTab(account_tab, "Личный кабинет")

        if self.is_admin:
            admin_tab = self.build_admin_tab()
            self.tab_widget.addTab(admin_tab, "Администрирование")

        content_layout.addWidget(self.tab_widget)

        main_layout.addWidget(content_widget)

        # Локальные настройки статистики без сохранения на сервер
        def save_mode(text):
            self.settings['stats_mode'] = text
        self.stats_mode_combo.currentTextChanged.connect(save_mode)

        def save_date():
            current_data = self.stats_date_combo.currentData()
            self.settings['stats_date'] = current_data.isoformat() if current_data else None
            self.update_date_buttons()
        self.stats_date_combo.currentIndexChanged.connect(save_date)

        # Восстановление выбранного режима
        self.stats_mode_combo.setCurrentText(self.settings.get('stats_mode', "Вакансии по часам (за день)"))

    def build_account_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)

        profile_group = QGroupBox("Профиль")
        profile_layout = QFormLayout(profile_group)

        self.profile_first_name = QLineEdit()
        self.profile_last_name = QLineEdit()
        self.profile_username = QLineEdit()
        self.profile_email = QLineEdit()
        self.profile_phone = QLineEdit()

        profile_layout.addRow("Имя:", self.profile_first_name)
        profile_layout.addRow("Фамилия:", self.profile_last_name)
        profile_layout.addRow("Username:", self.profile_username)
        profile_layout.addRow("Email:", self.profile_email)
        profile_layout.addRow("Телефон:", self.profile_phone)

        self.profile_save_btn = QPushButton("Сохранить профиль")
        self.profile_save_btn.clicked.connect(self.save_profile)
        profile_actions = QHBoxLayout()
        self.profile_logout_btn = QPushButton("Выйти из профиля")
        self.profile_logout_btn.clicked.connect(self.logout)
        profile_actions.addWidget(self.profile_save_btn)
        profile_actions.addWidget(self.profile_logout_btn)
        profile_actions.addStretch()
        profile_layout.addRow(profile_actions)

        subscription_group = QGroupBox("Подписка и платежи")
        sub_layout = QVBoxLayout(subscription_group)

        sub_info = QHBoxLayout()
        self.account_status_label = QLabel("Статус: —")
        self.account_plan_label = QLabel("Тариф: —")
        self.account_days_label = QLabel("Осталось дней: —")
        self.account_end_label = QLabel("Дата окончания: —")
        sub_info.addWidget(self.account_status_label)
        sub_info.addSpacing(20)
        sub_info.addWidget(self.account_plan_label)
        sub_info.addSpacing(20)
        sub_info.addWidget(self.account_days_label)
        sub_info.addSpacing(20)
        sub_info.addWidget(self.account_end_label)
        sub_layout.addLayout(sub_info)

        payments_actions = QHBoxLayout()
        self.payment_create_btn = QPushButton("Создать платеж")
        self.payment_refresh_btn = QPushButton("Обновить платежи")
        self.payment_check_btn = QPushButton("Проверить статус")
        self.payment_cancel_btn = QPushButton("Отменить платеж")
        self.payment_create_btn.clicked.connect(self.create_payment)
        self.payment_refresh_btn.clicked.connect(self.load_user_payments)
        self.payment_check_btn.clicked.connect(self.check_selected_payment)
        self.payment_cancel_btn.clicked.connect(self.cancel_selected_payment)
        payments_actions.addWidget(self.payment_create_btn)
        payments_actions.addWidget(self.payment_refresh_btn)
        payments_actions.addWidget(self.payment_check_btn)
        payments_actions.addWidget(self.payment_cancel_btn)
        payments_actions.addStretch()
        sub_layout.addLayout(payments_actions)

        self.payments_table = QTableWidget()
        self.payments_table.setColumnCount(8)
        self.payments_table.setHorizontalHeaderLabels(
            ["ID", "Тариф", "Месяцев", "Сумма", "Статус", "Создан", "Подтвержден", "Примечание"]
        )
        self.payments_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.payments_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.payments_table.setEditTriggers(QTableWidget.NoEditTriggers)
        sub_layout.addWidget(self.payments_table)

        layout.addWidget(profile_group)
        layout.addWidget(subscription_group)
        layout.addStretch()
        return tab

    def build_admin_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)

        self.admin_tabs = QTabWidget()
        self.admin_tabs.addTab(self.build_admin_users_tab(), "Пользователи")
        self.admin_tabs.addTab(self.build_admin_payments_tab(), "Платежи")
        self.admin_tabs.addTab(self.build_admin_stats_tab(), "Статистика")
        self.admin_tabs.addTab(self.build_admin_bot_tab(), "Бот")
        layout.addWidget(self.admin_tabs)
        return tab

    def build_admin_users_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        top = QHBoxLayout()
        self.admin_user_search = QLineEdit()
        self.admin_user_search.setPlaceholderText("Поиск по имени, username или email")
        self.admin_user_search.textChanged.connect(self.filter_admin_users)
        self.admin_user_refresh_btn = QPushButton("Обновить")
        self.admin_user_refresh_btn.clicked.connect(self.load_admin_users)
        self.admin_user_edit_btn = QPushButton("Редактировать")
        self.admin_user_edit_btn.clicked.connect(self.edit_selected_admin_user)
        self.admin_user_extend_btn = QPushButton("Продлить")
        self.admin_user_extend_btn.clicked.connect(self.extend_selected_admin_user)
        self.admin_user_plan_btn = QPushButton("Тариф")
        self.admin_user_plan_btn.clicked.connect(self.apply_plan_selected_admin_user)
        self.admin_user_delete_btn = QPushButton("Удалить")
        self.admin_user_delete_btn.clicked.connect(self.delete_selected_admin_user)
        top.addWidget(self.admin_user_search)
        top.addWidget(self.admin_user_refresh_btn)
        top.addWidget(self.admin_user_edit_btn)
        top.addWidget(self.admin_user_extend_btn)
        top.addWidget(self.admin_user_plan_btn)
        top.addWidget(self.admin_user_delete_btn)
        layout.addLayout(top)

        self.admin_users_table = QTableWidget()
        self.admin_users_table.setColumnCount(9)
        self.admin_users_table.setHorizontalHeaderLabels(
            ["Telegram ID", "Имя", "Username", "Email", "Статус", "Тариф", "Дней", "Роль", "Создан"]
        )
        self.admin_users_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.admin_users_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.admin_users_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.admin_users_table)
        return tab

    def build_admin_payments_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        top = QHBoxLayout()
        self.admin_payment_status = QComboBox()
        self.admin_payment_status.addItems(["ALL", "PENDING", "VERIFIED", "REJECTED", "EXPIRED"])
        self.admin_payment_status.currentIndexChanged.connect(self.load_admin_payments)
        self.admin_payment_refresh_btn = QPushButton("Обновить")
        self.admin_payment_refresh_btn.clicked.connect(self.load_admin_payments)
        self.admin_payment_verify_btn = QPushButton("Подтвердить")
        self.admin_payment_verify_btn.clicked.connect(self.verify_selected_payment)
        self.admin_payment_reject_btn = QPushButton("Отклонить")
        self.admin_payment_reject_btn.clicked.connect(self.reject_selected_payment)
        top.addWidget(QLabel("Статус:"))
        top.addWidget(self.admin_payment_status)
        top.addWidget(self.admin_payment_refresh_btn)
        top.addWidget(self.admin_payment_verify_btn)
        top.addWidget(self.admin_payment_reject_btn)
        top.addStretch()
        layout.addLayout(top)

        self.admin_payments_table = QTableWidget()
        self.admin_payments_table.setColumnCount(8)
        self.admin_payments_table.setHorizontalHeaderLabels(
            ["ID", "Telegram ID", "Тариф", "Месяцев", "Сумма", "Статус", "Создан", "Примечание"]
        )
        self.admin_payments_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.admin_payments_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.admin_payments_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.admin_payments_table)
        return tab

    def build_admin_stats_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        self.admin_stats_label = QLabel("Статистика администратора")
        self.admin_stats_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.admin_stats_label)

        self.admin_stats_details = QLabel("")
        self.admin_stats_details.setWordWrap(True)
        layout.addWidget(self.admin_stats_details)

        self.admin_stats_refresh_btn = QPushButton("Обновить")
        self.admin_stats_refresh_btn.clicked.connect(self.load_admin_stats)
        layout.addWidget(self.admin_stats_refresh_btn)
        layout.addStretch()
        return tab

    def build_admin_bot_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        self.bot_stats_label = QLabel("Статистика бота")
        self.bot_stats_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.bot_stats_details = QLabel("")
        self.bot_stats_details.setWordWrap(True)

        layout.addWidget(self.bot_stats_label)
        layout.addWidget(self.bot_stats_details)

        controls = QHBoxLayout()
        self.bot_start_btn = QPushButton("Старт")
        self.bot_restart_btn = QPushButton("Рестарт")
        self.bot_start_btn.clicked.connect(lambda: self.control_bot("start"))
        self.bot_restart_btn.clicked.connect(lambda: self.control_bot("restart"))
        controls.addWidget(self.bot_start_btn)
        controls.addWidget(self.bot_restart_btn)
        controls.addStretch()
        layout.addLayout(controls)

        broadcast_group = QGroupBox("Рассылка")
        b_layout = QVBoxLayout(broadcast_group)
        self.broadcast_input = QLineEdit()
        self.broadcast_input.setPlaceholderText("Текст рассылки")
        self.broadcast_send_btn = QPushButton("Отправить")
        self.broadcast_send_btn.clicked.connect(self.send_broadcast)
        b_layout.addWidget(self.broadcast_input)
        b_layout.addWidget(self.broadcast_send_btn)
        layout.addWidget(broadcast_group)
        layout.addStretch()
        return tab

    def go_older_date(self):
        """Переход к более старой дате (увеличение индекса)"""
        current_index = self.stats_date_combo.currentIndex()
        if current_index < self.stats_date_combo.count() - 1:
            self.stats_date_combo.setCurrentIndex(current_index + 1)

    def go_newer_date(self):
        """Переход к более новой дате (уменьшение индекса)"""
        current_index = self.stats_date_combo.currentIndex()
        if current_index > 0:
            self.stats_date_combo.setCurrentIndex(current_index - 1)

    # def prev_date(self):
    #     current_index = self.stats_date_combo.currentIndex()
    #     if current_index > 0:
    #         self.stats_date_combo.setCurrentIndex(current_index - 1)
    #
    # def next_date(self):
    #     current_index = self.stats_date_combo.currentIndex()
    #     if current_index < self.stats_date_combo.count() - 1:
    #         self.stats_date_combo.setCurrentIndex(current_index + 1)

    def today_date(self):
        today = datetime.now().date()
        for i in range(self.stats_date_combo.count()):
            if self.stats_date_combo.itemData(i) == today:
                self.stats_date_combo.setCurrentIndex(i)
                break

    def update_date_buttons(self):
        current_index = self.stats_date_combo.currentIndex()
        self.prev_btn.setEnabled(current_index < self.stats_date_combo.count() - 1)  # ← для старой: если не последняя
        self.next_btn.setEnabled(current_index > 0)  # → для новой: если не первая

    def save_app_settings(self):
        query = self.query_input.text().strip()
        exclude = self.exclude_input.text().strip()
        days = self.days_input.value()

        if not query:
            QMessageBox.warning(self, "Ошибка", "Укажите ключевое слово")
            return

        work_types = {
            'remote': self.remote_checkbox.isChecked(),
            'hybrid': self.hybrid_checkbox.isChecked(),
            'office': self.office_checkbox.isChecked()
        }

        countries = {
            'russia': self.russia_checkbox.isChecked(),
            'belarus': self.belarus_checkbox.isChecked()
        }

        auto_update = {
            'enabled': self.auto_update_checkbox.isChecked(),
            'interval_minutes': self.auto_update_interval.value()
        }

        self.settings.update({
            "query": query,
            "exclude": exclude,
            "days": days,
            "work_types": work_types,
            "countries": countries,
            "auto_update": auto_update,
            "telegram_notify": self.telegram_notify_checkbox.isChecked()
        })

        self.save_settings()
        self.setup_auto_update()
        QMessageBox.information(self, "Успех", "Настройки сохранены!")

    def update_table(self):
        logger.info("Обновление таблицы")
        new_count = sum(1 for v in self.vacancies if v.get('status') == 'NEW')
        self.total_label.setText(str(len(self.vacancies)))
        self.new_label.setText(str(new_count))

        sorted_vacancies = sorted(self.vacancies, key=lambda x: self.parse_loaded_date(x.get('loaded_at', '')),
                                  reverse=True)
        sorted_vacancies.sort(key=lambda x: 0 if x.get('status') == 'NEW' else 1)

        status_filter = None
        if hasattr(self, "status_filter_combo") and self.status_filter_combo:
            status_filter = self.status_filter_combo.currentData()
        if status_filter:
            filtered_vacancies = [v for v in sorted_vacancies if v.get("status") == status_filter]
        else:
            filtered_vacancies = list(sorted_vacancies)

        if filtered_vacancies:
            self.action_widget.show()
        else:
            self.action_widget.hide()

        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                self.table.removeCellWidget(row, 0)
                widget.deleteLater()

        self.table.setRowCount(len(filtered_vacancies))

        is_dark = self.settings.get("theme") == "dark"

        for row, v in enumerate(filtered_vacancies):
            checkbox = QCheckBox()
            checkbox.setProperty("vacancy_id", v.get("id"))
            self.table.setCellWidget(row, 0, checkbox)

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

            title_item = QTableWidgetItem(v.get('title', '-'))
            title_item.setData(Qt.UserRole, v.get("id"))
            self.table.setItem(row, 2, title_item)
            self.table.setItem(row, 3, QTableWidgetItem(v.get('company', '-')))
            self.table.setItem(row, 4, QTableWidgetItem(v.get('city', '-')))

            schedule = v.get('schedule', '-')
            schedule_item = QTableWidgetItem(schedule)
            self.table.setItem(row, 5, schedule_item)

            self.table.setItem(row, 6, QTableWidgetItem(v.get('salary', '-')))
            self.table.setItem(row, 7, QTableWidgetItem(v.get('date', '-')))
            self.table.setItem(row, 8, QTableWidgetItem(v.get('loaded_at', '-')))

            open_item = QTableWidgetItem("🔗 Открыть")
            open_item.setData(Qt.UserRole, v.get('link', ''))
            open_item.setTextAlignment(Qt.AlignCenter)
            open_item.setForeground(QColor("#BB86FC" if is_dark else "#6200EE"))
            font = open_item.font()
            font.setBold(True)
            open_item.setFont(font)
            self.table.setItem(row, 9, open_item)

        logger.info("Таблица обновлена")

    def on_cell_click(self, row, column):
        if column == 9:
            item = self.table.item(row, column)
            if item:
                link = item.data(Qt.UserRole)
                if link and link != "#":
                    logger.info(f"Открытие ссылки: {link}")
                    QDesktopServices.openUrl(link)

    def format_datetime(self, value):
        if not value:
            return ""
        try:
            cleaned = value.replace("Z", "").replace("+00:00", "")
            dt = datetime.fromisoformat(cleaned)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return value

    def normalize_vacancy(self, vacancy):
        status = vacancy.get("status")
        status_value = "NEW" if status == "NEW" else "OLD"
        published_at = vacancy.get("publishedAt")
        loaded_at = vacancy.get("loadedAt")

        return {
            "id": vacancy.get("id"),
            "title": vacancy.get("title") or "-",
            "company": vacancy.get("employer") or "-",
            "city": vacancy.get("city") or "-",
            "salary": vacancy.get("salary") or "не указана",
            "date": self.format_datetime(published_at)[:10] if published_at else "",
            "link": vacancy.get("url") or "#",
            "schedule": vacancy.get("schedule") or "-",
            "status": status_value,
            "loaded_at": self.format_datetime(loaded_at)
        }

    def build_search_payload(self):
        work_types = [k for k, v in self.settings.get("work_types", {}).items() if v]
        countries = [k for k, v in self.settings.get("countries", {}).items() if v]

        return {
            "query": self.settings.get("query"),
            "days": self.settings.get("days"),
            "workTypes": work_types,
            "countries": countries,
            "excludeKeywords": self.settings.get("exclude"),
            "telegramNotify": self.settings.get("telegram_notify", False) if self.subscription_active else False
        }

    def load_vacancies_from_file(self):
        if self.offline_mode:
            self.vacancies = []
            return
        try:
            server_vacancies = self.api.get_vacancies()
            self.vacancies = [self.normalize_vacancy(v) for v in server_vacancies]
            logger.info(f"Загружено {len(self.vacancies)} вакансий с сервера")
        except Exception as e:
            logger.error(f"Ошибка загрузки вакансий: {e}")
            self.vacancies = []

    def save_vacancies_to_file(self):
        return

    def update_vacancies(self):
        logger.info("Нажата кнопка 'Обновить'")
        if self.offline_mode:
            QMessageBox.warning(self, "Нет соединения", "Сервер недоступен. Повторите позже.")
            return
        if not self.ensure_authenticated():
            return
        self.update_btn.setEnabled(False)
        self.update_btn.setText("⏳ Обновление...")
        old_ids = {v['id'] for v in self.vacancies if v.get("id")}
        search_payload = self.build_search_payload()
        self.worker = UpdateWorker(self.token, search_payload, old_ids, do_search=False)
        self.worker.finished.connect(self.on_update_finished_with_server)
        self.worker.error.connect(self.on_update_error)
        self.worker.start()

    def run_search(self):
        logger.info("Запуск поиска на сервере")
        if self.offline_mode:
            QMessageBox.warning(self, "Нет соединения", "Сервер недоступен. Повторите позже.")
            return
        if self.worker and self.worker.isRunning():
            logger.info("Обновление уже выполняется, пропускаем")
            return
        if not self.ensure_authenticated():
            return
        self.search_btn.setEnabled(False)
        self.search_btn.setText("⏳ Поиск...")
        old_ids = {v['id'] for v in self.vacancies if v.get("id")}
        search_payload = self.build_search_payload()
        self.worker = UpdateWorker(self.token, search_payload, old_ids, do_search=True)
        self.worker.finished.connect(self.on_update_finished_with_server)
        self.worker.error.connect(self.on_update_error)
        self.worker.start()

    def on_update_finished_with_server(self, server_vacancies, new_count):
        logger.info(f"Обновление завершено: {new_count} новых вакансий")

        self.vacancies = [self.normalize_vacancy(v) for v in server_vacancies]
        self.populate_stats_dates()
        self.update_table()
        self.update_stats_chart()

        self.update_btn.setEnabled(True)
        self.update_btn.setText("🔄 Обновить")
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Запустить поиск")

        if new_count:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Успех")
            msg.setText(f"✅ Найдено {new_count} новых вакансий!")
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
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Запустить поиск")

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
        ids_to_mark = []
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                vacancy_id = checkbox.property("vacancy_id")
                for v in self.vacancies:
                    if v.get("id") == vacancy_id and v.get("status") == "NEW":
                        v["status"] = "OLD"
                        if vacancy_id:
                            ids_to_mark.append(vacancy_id)
                        updated += 1
                        break

        if updated > 0:
            if ids_to_mark:
                try:
                    self.api.mark_multiple_viewed(ids_to_mark)
                except Exception as e:
                    logger.error(f"Ошибка отметки вакансий: {e}")
            self.update_table()
            self.update_stats_chart()
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

    def delete_selected_vacancies(self):
        logger.info("Удаление выбранных вакансий")
        ids_to_delete = []
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                vacancy_id = checkbox.property("vacancy_id")
                if vacancy_id:
                    ids_to_delete.append(vacancy_id)

        if not ids_to_delete:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Внимание")
            msg.setText("⚠️ Не выбрано ни одной вакансии")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
            return

        confirm = QMessageBox.question(
            self,
            "Удаление",
            f"Удалить выбранные вакансии ({len(ids_to_delete)})?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        failed = 0
        for vacancy_id in ids_to_delete:
            try:
                self.api.delete_vacancy(vacancy_id)
            except Exception as e:
                failed += 1
                logger.error(f"Ошибка удаления вакансии {vacancy_id}: {e}")

        self.vacancies = [v for v in self.vacancies if v.get("id") not in ids_to_delete]
        self.update_table()
        self.update_stats_chart()

        if failed:
            QMessageBox.warning(self, "Удаление", f"Не удалось удалить: {failed}")

    def show_about_dialog(self):
        """Показывает информацию о приложении и разработчике"""
        text = (
            "<b>Удобные Вакансии — HH.ru</b><br><br>"
            "Разработчик: Максим К.<br>"
            "Email: <a href='mailto:maximkisten@gmail.com'>maximkisten@gmail.com</a><br>"
            "Telegram: <a href='https://t.me/maximkisten'>@maximkisten</a><br><br>"
            "Все мысли и пожелания готов принимать по указанным контактам."
        )

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("О программе")
        msg.setTextFormat(Qt.RichText)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def show_support_dialog(self):
        """Открывает диалог с QR-кодом и просьбой о поддержке."""
        dialog = SupportDialog(self)
        dialog.exec()

    def populate_stats_dates(self):
        """Заполнение комбобокса с датами для статистики"""
        if not hasattr(self, 'stats_date_combo'):
            logger.warning("stats_date_combo ещё не создан, пропускаем populate_stats_dates")
            return

        dates = set()
        for v in self.vacancies:
            loaded_at_str = v.get('loaded_at', '')
            if loaded_at_str:
                try:
                    loaded_dt = datetime.strptime(loaded_at_str, "%Y-%m-%d %H:%M:%S")
                    dates.add(loaded_dt.date())
                except ValueError:
                    pass

        self.stats_date_combo.clear()

        if not dates:
            self.stats_date_combo.addItem("Нет данных")
            return

        for date in sorted(dates, reverse=True):
            self.stats_date_combo.addItem(date.strftime("%d.%m.%Y"), date)

        # Восстановить выбранную дату
        saved_date_str = self.settings.get('stats_date')
        if saved_date_str:
            try:
                saved_date = datetime.fromisoformat(saved_date_str).date()
                index = self.stats_date_combo.findData(saved_date)
                if index >= 0:
                    self.stats_date_combo.setCurrentIndex(index)
                else:
                    # Установить на последнюю (самую новую)
                    self.stats_date_combo.setCurrentIndex(0)
            except ValueError:
                # Неверный формат сохраненной даты
                self.stats_date_combo.setCurrentIndex(0)
        else:
            # Установить на последнюю (самую новую)
            self.stats_date_combo.setCurrentIndex(0)

        self.update_date_buttons()
        logger.info(f"Загружено {len(dates)} уникальных дат для статистики")

    def on_stats_mode_changed(self, mode):
        """Обработка изменения режима статистики"""
        is_hourly = mode == "Вакансии по часам (за день)"
        self.stats_date_combo.setVisible(is_hourly)
        self.prev_btn.setVisible(is_hourly)
        self.today_btn.setVisible(is_hourly)
        self.next_btn.setVisible(is_hourly)
        if is_hourly:
            self.update_date_buttons()

        for i in range(self.stats_date_combo.parentWidget().layout().count()):
            item = self.stats_date_combo.parentWidget().layout().itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QLabel) and item.widget().text() == "Дата:":
                item.widget().setVisible(is_hourly)
                break

        self.update_stats_chart()


if __name__ == "__main__":
    print("=" * 50)
    print("Вход в main блок")
    print("=" * 50)
    try:
        logger.info("Запуск основного цикла приложения")
        print("Создание QApplication")
        app = QApplication(sys.argv)
        print("QApplication создан")

        app.setStyle("Fusion")
        print("Стиль установлен")

        print("Создание окна VacancyApp")
        window = VacancyApp()
        print("Окно создано")

        print("Показ окна")
        window.show()
        print("Окно показано")

        print("Запуск event loop")
        sys.exit(app.exec())
    except Exception as e:
        print(f"=" * 50)
        print(f"КРИТИЧЕСКАЯ ОШИБКА: {e}")
        print(f"=" * 50)
        import traceback

        traceback.print_exc()
        input("Нажмите Enter для выхода...")
