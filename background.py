import time
import threading
from queue import Queue
from typing import Callable, Optional

import pyperclip
from PIL import Image, ImageGrab
from pynput import keyboard
from loguru import logger

class ClipboardMonitor(threading.Thread):
    """
    Мониторит буфер обмена на предмет двойного копирования (Ctrl+C+C).
    Работает в отдельном потоке.
    """
    def __init__(self, task_queue: Queue, repeat_threshold: float = 0.5):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.repeat_threshold = repeat_threshold
        self._stop_event = threading.Event()
        self._last_copy_time: float = 0.0
        self._last_text_content: Optional[str] = None
        logger.info("ClipboardMonitor thread initialized.")

    def run(self) -> None:
        """Основной цикл работы монитора."""
        logger.info("ClipboardMonitor thread started.")
        # Простая реализация на pyperclip.paste, т.к. win32gui сложнее и требует окна.
        # Для надежности можно вернуть реализацию с WM_CLIPBOARDUPDATE, если потребуется.
        while not self._stop_event.is_set():
            try:
                # Проверяем текст
                current_text = pyperclip.paste()
                
                if isinstance(current_text, str) and current_text:
                    current_time = time.time()
                    if (self._last_text_content is not None and
                        current_text == self._last_text_content and
                        (current_time - self._last_copy_time) < self.repeat_threshold):
                        
                        logger.info("Repeated text copy detected. Queueing task.")
                        # Проверяем, нет ли в буфере изображения, на случай если скопировали его
                        image_content = ImageGrab.grabclipboard()
                        if isinstance(image_content, Image.Image):
                             self.task_queue.put(("EXECUTE_FROM_CLIPBOARD", image_content))
                        else:
                             self.task_queue.put(("EXECUTE_FROM_CLIPBOARD", current_text))
                        
                        # Сбрасываем, чтобы избежать многократного срабатывания
                        self._last_text_content = None
                        self._last_copy_time = 0
                    else:
                        self._last_text_content = current_text
                        self._last_copy_time = current_time

            except pyperclip.PyperclipException:
                # Ошибка может возникнуть, если в буфере не текст. Игнорируем.
                self._last_text_content = None
            
            time.sleep(0.1) # Пауза для снижения нагрузки на ЦП
        
        logger.info("ClipboardMonitor thread stopped.")

    def stop(self) -> None:
        """Останавливает поток мониторинга."""
        self._stop_event.set()
        logger.info("Stopping ClipboardMonitor thread.")

class HotkeyListener(threading.Thread):
    """
    Слушает глобальную горячую клавишу для вызова/скрытия окна.
    Работает в отдельном потоке.
    """
    def __init__(self, hotkey: str, callback: Callable):
        super().__init__(daemon=True)
        self.hotkey_str = hotkey
        self.callback = callback
        self._listener = None
        logger.info(f"HotkeyListener thread initialized for hotkey '{hotkey}'.")

    def run(self) -> None:
        """Запускает слушатель pynput."""
        logger.info("HotkeyListener thread started.")
        try:
            with keyboard.GlobalHotKeys({self.hotkey_str: self.on_activate}) as self._listener:
                self._listener.join()
        except Exception as e:
            logger.opt(exception=True).error(f"Error in HotkeyListener: {e}")
        logger.info("HotkeyListener thread stopped.")

    def on_activate(self) -> None:
        """Колбэк, вызываемый при нажатии горячей клавиши."""
        logger.info(f"Global hotkey '{self.hotkey_str}' activated.")
        self.callback()

    def stop(self) -> None:
        """Останавливает слушатель."""
        if self._listener:
            self._listener.stop()
            logger.info("Stopping HotkeyListener thread.")