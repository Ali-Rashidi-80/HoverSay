import time
import tempfile
import os
from gtts import gTTS
import pygame
import uuid

def generate_and_play_audio(text, lang):
    try:
        temp_audio_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.mp3")
        tts = gTTS(text=text, lang=lang)
        tts.save(temp_audio_path)
        print(f"فایل صوتی تولید شد: {temp_audio_path}")

        wait_for_file_write_complete(temp_audio_path)
        play_audio(temp_audio_path)

    except Exception as e:
        print(f"❌ خطا در تولید/پخش صوت: {e}")

def wait_for_file_write_complete(file_path, timeout=5):
    for _ in range(int(timeout * 10)):
        try:
            with open(file_path, "rb"):
                return
        except PermissionError:
            time.sleep(0.1)
    raise RuntimeError("⏳ فایل صوتی تا زمان مقرر قابل دسترسی نشد.")

def play_audio(audio_file):
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.music.stop()

        # 🧼 اطمینان از اینکه فایل دیگه استفاده نمی‌شه
        try:
            pygame.mixer.music.unload()
        except:
            pass  # برخی نسخه‌ها این تابع رو ندارن

        pygame.mixer.quit()
        time.sleep(0.3)  # 🔑 زمان دادن برای آزادسازی فایل

        # حذف فایل
        if os.path.exists(audio_file):
            os.remove(audio_file)
            print("🗑 فایل صوتی موقت حذف شد.")

    except Exception as e:
        print(f"❌ خطا در پخش یا حذف صوت: {e}")

if __name__ == "__main__":
    sample_text = "This is a test of the text-to-speech system using pygame."
    sample_lang = "en"  # 'fa' برای فارسی، 'en' برای انگلیسی
    generate_and_play_audio(sample_text, sample_lang)