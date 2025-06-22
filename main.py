import os
import sys
from tkinter import messagebox
import webbrowser
import subprocess

from loguru import logger
from dotenv import load_dotenv

from app_gui import AutoReclipperApp

# Константы
LOG_FILE = "autoreclipper.log"
LOG_ERROR_FILE = "autoreclipper_error.log"


def _ensure_env_file(env_path: str) -> None:
    """Create .env file with placeholder if it is missing or lacks the key."""
    placeholder = 'GEMINI_API_KEY="YOUR_API_KEY_HERE"\n'
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(placeholder)
        logger.info("Created .env file with API key placeholder.")
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "GEMINI_API_KEY" not in content:
            with open(env_path, "a", encoding="utf-8") as f:
                if not content.endswith("\n"):
                    f.write("\n")
                f.write(placeholder)
            logger.info("Added API key placeholder to existing .env file.")
    except IOError as e:
        logger.error(f"Failed to prepare .env file: {e}")


def _open_file_default(path: str) -> None:
    """Open a file with the default text editor."""
    try:
        if sys.platform.startswith("win"):
            editor_cmd = ["notepad", path]
            subprocess.run(editor_cmd, check=True)
            # os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform.startswith("darwin"):
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        logger.error(f"Failed to open file {path}: {e}")


def _prompt_api_key_setup(env_path: str) -> None:
    """Show a modal dialog instructing the user to add the API key."""
    import tkinter as tk

    root = tk.Tk()
    root.title("GEMINI_API_KEY Required")
    root.resizable(False, False)

    label = tk.Label(
        root,
        text=(
            "Generate a Google Gemini API key, paste it into .env and save.\n"
            "Сгенерируйте API ключ, вставьте его в .env и сохраните."
        ),
        justify="center",
        wraplength=360,
    )
    label.pack(padx=20, pady=10)

    frame = tk.Frame(root)
    frame.pack(pady=5)

    def go():
        webbrowser.open(
            "https://www.google.com/search?q=how+to+get+google+gemini+api+key+for+free"
        )
        _open_file_default(env_path)
        root.destroy()

    def cancel():
        root.destroy()

    go_btn = tk.Button(frame, text="GO", width=10, command=go)
    cancel_btn = tk.Button(frame, text="Cancel", width=10, command=cancel)
    go_btn.pack(side="left", padx=10)
    cancel_btn.pack(side="left", padx=10)

    root.mainloop()

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
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or len(api_key) < 50:
        logger.error("GEMINI_API_KEY not found in environment.")
        env_path = os.path.join(os.getcwd(), ".env")
        _ensure_env_file(env_path)
        _prompt_api_key_setup(env_path)
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
