import os
import sys
from tkinter import messagebox

from loguru import logger
from dotenv import load_dotenv

from app_gui import AutoReclipperApp

# Константы
LOG_FILE = "autoreclipper.log"
LOG_ERROR_FILE = "autoreclipper_error.log"

def setup_logging():
    """Настраивает систему логирования с использованием Loguru."""
    logger.remove()
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    try:
        # Логирование в консоль
        logger.add(sys.stdout, colorize=True, format=log_format, level="INFO")
    except Exception as e:
        # Эта ошибка может возникнуть, если нет доступной консоли (например, при запуске с pythonw.exe)
        # Логируем это в файл для отладки, но не прерываем работу.
        logger.debug(f"Could not add console logger: {e}")
    
    # Логирование в файлы
    logger.add(LOG_FILE, rotation="10 MB", retention="7 days", encoding="utf-8", level="DEBUG", format=log_format)
    logger.add(LOG_ERROR_FILE, rotation="10 MB", retention="7 days", encoding="utf-8", level="ERROR", backtrace=True, diagnose=True)
    
    logger.info("Logging is configured.")

def main():
    """Основная функция для запуска приложения. Main application launch function."""
    setup_logging()

    # Загрузка переменных окружения
    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY not found in .env file.")
        # Поскольку GUI еще не запущен, используем стандартный messagebox
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "API Key Error",
            "The GEMINI_API_KEY was not found in the .env file. Please add it and restart the application.\n"
            "GEMINI_API_KEY не найден в файле .env. Пожалуйста, добавьте его и перезапустите приложение."
        )
        root.destroy()
        return

    try:
        app = AutoReclipperApp()
        app.mainloop()
    except Exception as e:
        logger.opt(exception=True).critical(f"An unhandled exception occurred: {e}")
        messagebox.showerror("Critical Error", f"Произошла критическая ошибка: {e}\n\nСмотрите {LOG_ERROR_FILE} для деталей.")
    finally:
        logger.info("Application shutting down.")

if __name__ == "__main__":
    main()