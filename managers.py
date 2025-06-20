import os
import json
from datetime import datetime
from collections import deque
from typing import List, Dict, Optional, Any, Tuple

from loguru import logger
from PIL import Image

from utils import SETTINGS_FILE, TEMPLATES_DIR, HISTORY_MAX_LEN, HistoryEntry

class SettingsManager:
    """
    Управляет загрузкой и сохранением настроек приложения.
    """
    def __init__(self, filepath: str = SETTINGS_FILE):
        self.filepath = filepath
        logger.info(f"Initializing SettingsManager with file: {self.filepath}")

    def load_settings(self) -> Dict[str, Any]:
        """
        Загружает настройки из JSON-файла.
        Возвращает дефолтные значения, если файл не найден или поврежден.
        """
        # --- ИСПРАВЛЕНИЕ: Добавлены настройки шрифта по умолчанию ---
        defaults = {
            "geometry": "600x700",
            "last_template": None,
            "font_family": "Segoe UI",
            "font_size": 13,
        }
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            logger.info(f"Settings loaded successfully from {self.filepath}")
            # Дополняем загруженные настройки значениями по умолчанию, если каких-то ключей нет
            defaults.update(settings)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load settings from {self.filepath}: {e}. Returning defaults.")
        return defaults

    def save_settings(self, settings: Dict[str, Any]) -> None:
        """
        Сохраняет текущие настройки в JSON-файл.
        """
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            logger.info(f"Settings saved successfully to {self.filepath}")
        except IOError as e:
            logger.error(f"Failed to save settings to {self.filepath}: {e}")

class TemplateManager:
    """
    Управляет загрузкой и доступом к шаблонам (промптам).
    """
    def __init__(self, directory: str = TEMPLATES_DIR):
        self.directory = directory
        self.templates: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Initializing TemplateManager with directory: {self.directory}")
        self.load_templates()

    def load_templates(self) -> None:
        """
        Сканирует директорию, загружает и валидирует все .json шаблоны.
        """
        if not os.path.isdir(self.directory):
            logger.error(f"Templates directory not found: {self.directory}")
            os.makedirs(self.directory)
            logger.info(f"Created templates directory: {self.directory}")
            return

        self.templates = {}
        for filename in os.listdir(self.directory):
            if filename.endswith(".json"):
                filepath = os.path.join(self.directory, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        template_data = json.load(f)
                    
                    if self._is_valid(template_data):
                        name = template_data["name"]
                        self.templates[name] = template_data
                        logger.debug(f"Successfully loaded template: {name}")
                    else:
                        logger.warning(f"Invalid template file (missing required keys): {filepath}")
                except (json.JSONDecodeError, IOError) as e:
                    logger.error(f"Failed to load or parse template {filepath}: {e}")
        logger.info(f"Loaded {len(self.templates)} templates.")

    def _is_valid(self, data: Dict[str, Any]) -> bool:
        """Проверяет наличие обязательных полей в шаблоне."""
        required_keys = ["name", "description", "api_provider", "model", "input_type", "prompt"]
        return all(key in data for key in required_keys)

    def get_template_names(self) -> List[str]:
        """Возвращает отсортированный список имен всех загруженных шаблонов."""
        return sorted(list(self.templates.keys()))

    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Возвращает данные шаблона по его имени."""
        return self.templates.get(name)

class HistoryManager:
    """
    Управляет историей выполненных операций.
    """
    def __init__(self, max_len: int = HISTORY_MAX_LEN):
        self.history: deque[HistoryEntry] = deque(maxlen=max_len)
        logger.info(f"Initializing HistoryManager with max length: {max_len}")

    def add_entry(self, source_content: Any, template_name: str, result_text: str) -> None:
        """
        Добавляет новую запись в историю.
        """
        entry = HistoryEntry(
            source_content=source_content,
            template_name=template_name,
            result_text=result_text,
            timestamp=datetime.now()
        )
        self.history.appendleft(entry)
        logger.info(f"Added new entry to history for template: {template_name}")

    def get_history_display_list(self) -> List[str]:
        """
        Возвращает список строк для отображения в ComboBox.
        """
        return [str(entry) for entry in self.history]

    def get_entry_by_str(self, entry_str: str) -> Optional[HistoryEntry]:
        """
        Находит запись в истории по ее строковому представлению.
        """
        for entry in self.history:
            if str(entry) == entry_str:
                return entry
        logger.warning(f"Could not find history entry for: {entry_str}")
        return None