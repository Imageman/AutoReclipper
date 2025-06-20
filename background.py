import time
import threading
from queue import Queue
from typing import Callable, Optional
import ctypes

import pyperclip
from PIL import Image, ImageGrab
from pynput import keyboard
from loguru import logger

try:
    import win32gui
    import win32con
    WM_CLIPBOARDUPDATE = 0x031D
except ImportError:
    logger.error("PyWin32 is not installed. Please run 'pip install pywin32'. This is required.")
    win32gui = None


class ClipboardMonitor(threading.Thread):
    """
    Мониторит буфер обмена с использованием системных сообщений Windows (WM_CLIPBOARDUPDATE).
    Это эффективный, событийно-ориентированный подход.
    """
    def __init__(self, task_queue: Queue, repeat_threshold: float = 0.5):
        if not win32gui:
            raise ImportError("Cannot start ClipboardMonitor because PyWin32 is not installed.")
        
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.repeat_threshold = repeat_threshold
        self._stop_event = threading.Event()
        
        self.hwnd: Optional[int] = None
        self._last_copy_time: float = time.time()
        self._last_text_content: Optional[str] = None
        self._ignore_next_update: bool = False
        
        logger.info("ClipboardMonitor thread initialized (using WM_CLIPBOARDUPDATE).")

    def run(self) -> None:
        logger.info("ClipboardMonitor thread started.")
        try:
            self._create_window()
            win32gui.PumpMessages()
        except Exception as e:
            logger.opt(exception=True).error(f"Error in ClipboardMonitor message loop: {e}")
        finally:
            self._destroy_window()
            logger.info("ClipboardMonitor message loop finished.")

    def _create_window(self) -> None:
        wc = win32gui.WNDCLASS()
        wc.lpszClassName = "AutoReclipperClipboardListener"
        wc.lpfnWndProc = self._wnd_proc
        class_atom = win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindowEx(0, class_atom, "Clipboard Listener Window", 0, 0, 0, 0, 0, win32con.HWND_MESSAGE, 0, 0, None)
        if not self.hwnd: raise RuntimeError("Failed to create the listener window.")
        if not ctypes.windll.user32.AddClipboardFormatListener(self.hwnd):
            raise RuntimeError("Failed to register clipboard format listener.")
        logger.debug(f"Hidden window created (HWND: {self.hwnd}) and listener registered.")

    def _destroy_window(self) -> None:
        if self.hwnd:
            ctypes.windll.user32.RemoveClipboardFormatListener(self.hwnd)
            win32gui.DestroyWindow(self.hwnd)
            logger.debug("Clipboard listener unregistered and hidden window destroyed.")

    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_CLIPBOARDUPDATE:
            self._handle_clipboard_update()
            return 0
        elif msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _handle_clipboard_update(self) -> None:
        if self._ignore_next_update:
            logger.debug("Ignoring clipboard update due to ignore flag.")
            self._ignore_next_update = False
            try: self._last_text_content = pyperclip.paste()
            except pyperclip.PyperclipException: self._last_text_content = None
            self._last_copy_time = time.time()
            return

        try:
            current_text = pyperclip.paste()
            if isinstance(current_text, str) and current_text:
                current_time = time.time()
                time_diff = current_time - self._last_copy_time
                
                if (self._last_text_content is not None and
                    current_text == self._last_text_content and
                    0.09 < time_diff < self.repeat_threshold):
                    
                    logger.info(f"Repeated text copy detected ({time_diff:.2f}s). Queueing task.")
                    image_content = ImageGrab.grabclipboard()
                    content_to_send = image_content if isinstance(image_content, Image.Image) else current_text
                    self.task_queue.put(("EXECUTE_FROM_CLIPBOARD", content_to_send))
                    self._ignore_next_update = True
                elif current_text != self._last_text_content:
                    self._last_text_content = current_text
                    self._last_copy_time = current_time
        except (pyperclip.PyperclipException, Image.DecompressionBombError):
            self._last_text_content = None
            self._last_copy_time = time.time()
        except Exception as e:
            logger.opt(exception=True).error(f"Error handling clipboard update: {e}")

    def stop(self) -> None:
        if self.hwnd:
            logger.info("Stopping ClipboardMonitor thread by posting WM_DESTROY.")
            win32gui.PostMessage(self.hwnd, win32con.WM_DESTROY, 0, 0)
        self._stop_event.set()


class HotkeyListener(threading.Thread):
    """
    Слушает глобальную горячую клавишу для вызова/скрытия окна, используя pynput.
    Этот метод не конфликтует с обработкой горячих клавиш внутри Tkinter.
    """
    def __init__(self, hotkey_str: str, callback: Callable):
        super().__init__(daemon=True)
        self.hotkey_str = hotkey_str
        self.callback = callback
        self._listener = None
        logger.info(f"HotkeyListener thread initialized for hotkey '{hotkey_str}' (using pynput).")

    def run(self) -> None:
        logger.info("HotkeyListener thread started.")
        try:
            # Создаем слушатель GlobalHotKeys внутри потока
            with keyboard.GlobalHotKeys({self.hotkey_str: self.on_activate}) as self._listener:
                self._listener.join()
        except Exception as e:
            logger.opt(exception=True).error(f"Error in HotkeyListener: {e}")
        logger.info("HotkeyListener thread stopped.")

    def on_activate(self) -> None:
        """Колбэк, вызываемый при нажатии горячей клавиши."""
        logger.info(f"Global hotkey '{self.hotkey_str}' activated.")
        # Помещаем задачу в очередь, чтобы избежать прямого вызова GUI из другого потока
        self.callback()

    def stop(self) -> None:
        """Останавливает слушатель."""
        if self._listener:
            self._listener.stop()
            logger.info("Stopping HotkeyListener thread.")