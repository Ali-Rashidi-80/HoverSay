import sys
import threading
import time
import os
import tempfile
import logging
import csv
from datetime import datetime
import pyautogui
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from googletrans import Translator
from langdetect import detect
from gtts import gTTS
import pygame
import uuid
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QSlider, QSpinBox, QPushButton, QTextEdit, QScrollArea,
    QMenuBar, QAction, QFileDialog, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from pynput import mouse
import re
import unicodedata
import shutil
import keyboard
import pyperclip
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

# تنظیم مسیر Tesseract
def get_tesseract_path():
    if shutil.which("tesseract"):
        return shutil.which("tesseract")
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    possible_path = os.path.join(base_path, "Tesseract-OCR", "tesseract.exe")
    if os.path.exists(possible_path):
        return possible_path
    else:
        return r'C:\Program Files\Tesseract-OCR\tesseract.exe'

pytesseract.pytesseract.tesseract_cmd = get_tesseract_path()

# تنظیم لاگ
logging.basicConfig(
    filename="translator_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

# پرچم مدیریت پخش صوت
is_playing = False
stop_playing = False

# توابع پخش صوت
def generate_and_play_audio(text, lang):
    global is_playing, stop_playing
    if is_playing:
        logging.info("پخش صوت در حال اجرا است، پخش جدید نادیده گرفته شد.")
        return
    is_playing = True
    stop_playing = False
    try:
        temp_audio_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.mp3")
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(temp_audio_path)
        logging.info(f"فایل صوتی تولید شد: {temp_audio_path}")
        wait_for_file_write_complete(temp_audio_path)
        play_audio(temp_audio_path)
    except Exception as e:
        logging.error(f"خطا در تولید/پخش صوت: {e}")
        QMessageBox.critical(None, "خطا", "پخش صوت با خطا مواجه شد.")
    finally:
        is_playing = False

def wait_for_file_write_complete(file_path, timeout=5):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with open(file_path, "rb"):
                return
        except PermissionError:
            time.sleep(0.1)
    raise RuntimeError("فایل صوتی تا زمان مقرر قابل دسترسی نشد.")

def play_audio(audio_file):
    global stop_playing
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy() and not stop_playing:
            time.sleep(0.1)
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        time.sleep(0.3)
        if os.path.exists(audio_file):
            os.remove(audio_file)
            logging.info("فایل صوتی موقت حذف شد.")
    except Exception as e:
        logging.error(f"خطا در پخش یا حذف صوت: {e}")

def stop_audio():
    global stop_playing
    stop_playing = True
    pygame.mixer.music.stop()

# پاکسازی متن
def clean_text(text):
    try:
        text = unicodedata.normalize('NFKC', text)
        text = ''.join(ch for ch in text if ch.isprintable())
        text = text.replace('|', 'I').replace('1', 'l').replace('0', 'O')
        text = re.sub(r'[\u200c\u200b-\u200f\u202a-\u202e]', '', text)
        text = re.sub(r'[^ء-يa-zA-Z0-9\s\.,!?؛،]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'([!?.,؛،])\1+', r'\1', text)
        if len(text) < 2:
            return ""
        return text
    except Exception as e:
        logging.error(f"خطا در پاکسازی متن: {e}")
        return ""

# کلاس اصلی برنامه
class TranslatorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("سیستم ترجمه و تلفظ هوشمند")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("background-color: #f0f0f0;")
        self.transTranslator = Translator()
        self.last_text = ""
        self.auto_capture = True
        self.region_width = 200
        self.region_height = 200
        self.capture_interval = 2000
        self.history = []
        self.mask_window = None
        self.mouse_listener = None
        self.ocr_mode = True
        self.clipboard_mode = False
        self.last_clipboard_text = ""
        self.request_queue = Queue(maxsize=1)
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.initUI()
        self.start_mouse_listener()
        self.start_keyboard_listener()
        self.timer = QTimer()
        self.timer.timeout.connect(self.process_region)
        self.timer.start(1000)
        self.clipboard_timer = QTimer()
        self.clipboard_timer.timeout.connect(self.check_clipboard)
        self.clipboard_timer.start(1000)

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # منو
        menubar = self.menuBar()
        mode_menu = menubar.addMenu("حالت‌ها")
        ocr_action = QAction("حالت OCR", self, checkable=True, checked=True)
        ocr_action.triggered.connect(lambda: self.toggle_modes(True, False))
        mode_menu.addAction(ocr_action)
        clipboard_action = QAction("حالت کلیپ‌بورد", self, checkable=True)
        clipboard_action.triggered.connect(lambda: self.toggle_modes(False, True))
        mode_menu.addAction(clipboard_action)

        # تنظیمات
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        main_layout.addWidget(settings_widget)

        width_label = QLabel("عرض ناحیه ضبط (px):")
        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setMinimum(100)
        self.width_slider.setMaximum(500)
        self.width_slider.setValue(200)
        self.width_slider.valueChanged.connect(lambda: setattr(self, 'region_width', self.width_slider.value()))

        height_label = QLabel("ارتفاع ناحیه ضبط (px):")
        self.height_slider = QSlider(Qt.Horizontal)
        self.height_slider.setMinimum(100)
        self.height_slider.setMaximum(500)
        self.height_slider.setValue(200)
        self.height_slider.valueChanged.connect(lambda: setattr(self, 'region_height', self.height_slider.value()))

        interval_label = QLabel("فاصله زمانی ضبط (ms):")
        self.interval_spin = QSpinBox()
        self.interval_spin.setMinimum(500)
        self.interval_spin.setMaximum(10000)
        self.interval_spin.setValue(2000)
        self.interval_spin.valueChanged.connect(lambda: setattr(self, 'capture_interval', self.interval_spin.value()))

        self.auto_capture_check = QCheckBox("ضبط خودکار")
        self.auto_capture_check.setChecked(True)
        self.auto_capture_check.stateChanged.connect(lambda: setattr(self, 'auto_capture', self.auto_capture_check.isChecked()))

        manual_capture_button = QPushButton("ضبط دستی")
        manual_capture_button.clicked.connect(self.manual_capture)

        settings_layout.addWidget(width_label)
        settings_layout.addWidget(self.width_slider)
        settings_layout.addWidget(height_label)
        settings_layout.addWidget(self.height_slider)
        settings_layout.addWidget(interval_label)
        settings_layout.addWidget(self.interval_spin)
        settings_layout.addWidget(self.auto_capture_check)
        settings_layout.addWidget(manual_capture_button)

        # نتایج
        result_widget = QWidget()
        result_layout = QVBoxLayout(result_widget)
        main_layout.addWidget(result_widget)

        original_label = QLabel("متن استخراج‌شده:")
        self.original_text = QTextEdit()
        self.original_text.setReadOnly(True)
        self.original_text.setText("در انتظار استخراج متن...")

        language_label = QLabel("زبان تشخیص داده شده:")
        self.language_text = QLabel("نامشخص")

        translation_label = QLabel("ترجمه:")
        self.translation_text = QTextEdit()
        self.translation_text.setReadOnly(True)
        self.translation_text.setText("در انتظار ترجمه...")

        self.play_button = QPushButton("پخش تلفظ")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.on_play)

        self.stop_button = QPushButton("توقف تلفظ")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(stop_audio)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        result_layout.addWidget(original_label)
        result_layout.addWidget(self.original_text)
        result_layout.addWidget(language_label)
        result_layout.addWidget(self.language_text)
        result_layout.addWidget(translation_label)
        result_layout.addWidget(self.translation_text)
        result_layout.addWidget(self.play_button)
        result_layout.addWidget(self.stop_button)
        result_layout.addWidget(self.progress)

        # تاریخچه
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        main_layout.addWidget(history_widget)

        self.history_list = QTextEdit()
        self.history_list.setReadOnly(True)

        export_button = QPushButton("خروجی CSV")
        export_button.clicked.connect(self.export_history)

        history_layout.addWidget(self.history_list)
        history_layout.addWidget(export_button)

        # اسکرول
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(central_widget)
        self.setCentralWidget(scroll_area)

    def toggle_modes(self, ocr, clipboard):
        self.ocr_mode = ocr
        self.clipboard_mode = clipboard

    def start_mouse_listener(self):
        self.mouse_listener = mouse.Listener(on_move=self.on_mouse_move)
        self.mouse_listener.start()

    def on_mouse_move(self, x, y):
        if self.mask_window:
            self.mask_window.close()
            self.mask_window = None

    def show_mask(self, left, top, width, height):
        if self.mask_window:
            self.mask_window.close()
        self.mask_window = QWidget()
        self.mask_window.setGeometry(left, top, width, height)
        self.mask_window.setWindowOpacity(0.3)
        self.mask_window.setStyleSheet("background-color: yellow;")
        self.mask_window.show()
        QTimer.singleShot(1000, self.fade_mask)

    def fade_mask(self):
        if self.mask_window:
            self.mask_window.setWindowOpacity(self.mask_window.windowOpacity() - 0.1)
            if self.mask_window.windowOpacity() > 0:
                QTimer.singleShot(100, self.fade_mask)
            else:
                self.mask_window.close()
                self.mask_window = None

    def start_keyboard_listener(self):
        keyboard.add_hotkey('f2', self.manual_capture)

    def manual_capture(self):
        if self.ocr_mode:
            self.executor.submit(self._process_region)

    def capture_region(self):
        try:
            width = self.region_width
            height = self.region_height
            x, y = pyautogui.position()
            left = max(x - width // 2, 0)
            top = max(y - height // 2, 0)
            image = pyautogui.screenshot(region=(left, top, width, height))
            logging.info("ناحیه ضبط گرفته شد.")
            self.show_mask(left, top, width, height)
            return image
        except Exception as e:
            logging.error(f"خطا در گرفتن اسکرین‌شات: {e}")
            return None

    def preprocess_image(self, image):
        try:
            image = image.convert('L')
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2)
            image = image.filter(ImageFilter.MedianFilter())
            threshold = 140
            image = image.point(lambda p: 255 if p > threshold else 0)
            logging.info("پیش‌پردازش تصویر انجام شد.")
            return image
        except Exception as e:
            logging.error(f"خطا در پیش‌پردازش تصویر: {e}")
            return image

    def extract_text_from_image(self, image):
        try:
            text = pytesseract.image_to_string(image, lang='eng+fas')
            logging.info(f"متن استخراج شد: {text.strip()}")
            return text.strip()
        except Exception as e:
            logging.error(f"خطا در استخراج متن: {e}")
            return ""

    def translate_text(self, text):
        try:
            detected_lang = detect(text)
        except Exception as e:
            logging.error(f"خطا در تشخیص زبان: {e}")
            detected_lang = 'en'
        dest_lang = 'en' if detected_lang == 'fa' else 'fa'
        try:
            translated = self.translator.translate(text, dest=dest_lang)
            translation_text = translated.text
            logging.info(f"ترجمه انجام شد: {translation_text}")
        except Exception as e:
            logging.error(f"خطا در ترجمه: {e}")
            translation_text = "ترجمه امکان‌پذیر نیست."
        return detected_lang, translation_text

    def auto_play_audio(self, detected_lang, text, translation_text):
        def play():
            if detected_lang == 'fa':
                audio_text = translation_text
                tts_lang = 'en'
            else:
                audio_text = text
                tts_lang = 'en'
            if audio_text and audio_text != "ترجمه امکان‌پذیر نیست.":
                generate_and_play_audio(audio_text, tts_lang)
        threading.Thread(target=play, daemon=True).start()

    def on_play(self):
        try:
            detected_lang = detect(self.original_text.toPlainText())
        except Exception:
            detected_lang = 'en'
        if detected_lang == 'fa':
            audio_text = self.translation_text.toPlainText()
            tts_lang = 'en'
        else:
            audio_text = self.original_text.toPlainText()
            tts_lang = 'en'
        if audio_text and audio_text != "ترجمه امکان‌پذیر نیست.":
            generate_and_play_audio(audio_text, tts_lang)

    def add_to_history(self, text, detected_lang, translation_text):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "timestamp": timestamp,
            "text": text,
            "language": "فارسی" if detected_lang == 'fa' else "انگلیسی",
            "translation": translation_text
        }
        self.history.append(record)
        history_entry = f"{timestamp} | {record['language']} | {text[:30]}... -> {translation_text[:30]}..."
        self.history_list.append(history_entry)

    def export_history(self):
        if not self.history:
            QMessageBox.information(self, "خروجی تاریخچه", "هیچ رکوردی موجود نیست.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "ذخیره تاریخچه", "", "CSV Files (*.csv)")
        if file_path:
            try:
                with open(file_path, mode='w', newline='', encoding="utf-8") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=["timestamp", "text", "language", "translation"])
                    writer.writeheader()
                    for record in self.history:
                        writer.writerow(record)
                QMessageBox.information(self, "خروجی تاریخچه", "تاریخچه ذخیره شد.")
            except Exception as e:
                logging.error(f"خطا در ذخیره تاریخچه: {e}")
                QMessageBox.critical(self, "خطا", "ذخیره تاریخچه با خطا مواجه شد.")

    def process_region(self):
        if self.auto_capture and self.ocr_mode:
            if not self.request_queue.full():
                self.request_queue.put(self._process_region)
                self.executor.submit(self._process_request)

    def _process_request(self):
        try:
            request = self.request_queue.get()
            self.progress.setVisible(True)
            request()
        finally:
            self.progress.setVisible(False)
            self.request_queue.task_done()

    def _process_region(self):
        try:
            image = self.capture_region()
            if image:
                processed_image = self.preprocess_image(image)
                text = self.extract_text_from_image(processed_image)
                text = clean_text(text)
                if text and text != self.last_text:
                    self.last_text = text
                    self.original_text.setText(text)
                    detected_lang, translation_text = self.translate_text(text)
                    self.language_text.setText("فارسی" if detected_lang == 'fa' else "انگلیسی")
                    self.translation_text.setText(translation_text)
                    self.play_button.setEnabled(True)
                    self.stop_button.setEnabled(True)
                    self.add_to_history(text, detected_lang, translation_text)
                    self.auto_play_audio(detected_lang, text, translation_text)
        except Exception as e:
            logging.error(f"خطا در پردازش ناحیه: {e}")

    def check_clipboard(self):
        if self.clipboard_mode:
            try:
                clipboard_text = pyperclip.paste()
                if clipboard_text and clipboard_text != self.last_clipboard_text:
                    self.last_clipboard_text = clipboard_text
                    text = clean_text(clipboard_text)
                    if text:
                        self.original_text.setText(text)
                        detected_lang, translation_text = self.translate_text(text)
                        self.language_text.setText("فارسی" if detected_lang == 'fa' else "انگلیسی")
                        self.translation_text.setText(translation_text)
                        self.play_button.setEnabled(True)
                        self.stop_button.setEnabled(True)
                        self.add_to_history(text, detected_lang, translation_text)
                        self.auto_play_audio(detected_lang, text, translation_text)
            except Exception as e:
                logging.error(f"خطا در بررسی کلیپ‌بورد: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TranslatorApp()
    window.show()
    sys.exit(app.exec_())