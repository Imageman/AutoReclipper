import os
import threading
from typing import Dict, Any, Optional

import google.generativeai as genai
from loguru import logger
from PIL import Image
import winsound

from utils import RESOURCES_DIR

class LLMService:
    """
    Сервис для взаимодействия с API языковых моделей.
    """
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment variables.")
        
        genai.configure(api_key=self.api_key)
        logger.info("LLMService initialized and Gemini API configured.")

    def execute_request(self, template: Dict[str, Any], content: str | Image.Image) -> Optional[str]:
        """
        Выполняет запрос к LLM на основе шаблона и контента.
        
        :param template: Словарь с данными шаблона.
        :param content: Текст или изображение из буфера обмена.
        :return: Результат от LLM или None в случае ошибки.
        """
        provider = template.get("api_provider")
        if provider == "gemini":
            return self._execute_gemini_request(template, content)
        else:
            logger.error(f"Unsupported API provider: {provider}")
            return None

    def _execute_gemini_request(self, template: Dict[str, Any], content: Any) -> Optional[str]:
        """
        Выполняет запрос к Gemini API.
        """
        model_name = template["model"]
        input_type = template["input_type"]
        prompt_template = template["prompt"]
        
        model = genai.GenerativeModel(model_name)
        
        # Формируем промпт
        full_prompt = prompt_template.format(clipboard_text=content if isinstance(content, str) else "")

        logger.info(f"Executing request to Gemini model '{model_name}' with input type '{input_type}'.")

        try:
            if input_type == "text" and isinstance(content, str):
                response = model.generate_content(full_prompt)
            elif input_type == "image" and isinstance(content, Image.Image):
                # Для vision моделей передаем промпт и изображение
                response = model.generate_content([full_prompt, content])
            else:
                logger.error(f"Mismatched input type: template requires '{input_type}' but content is '{type(content).__name__}'.")
                return f"Error: Template requires {input_type}, but received different content type."

            result_text = response.text.strip()
            logger.info("Successfully received response from Gemini.")
            logger.debug(f"Gemini response: {result_text[:100]}...")
            return result_text
        
        except Exception as e:
            logger.opt(exception=True).error(f"An error occurred while querying Gemini API: {e}")
            return None

class SoundService:
    """
    Сервис для воспроизведения звуковых сигналов.
    """
    def __init__(self, resource_dir: str = RESOURCES_DIR):
        self.in_sound_path = os.path.join(resource_dir, "in.wav")
        self.out_sound_path = os.path.join(resource_dir, "out.wav")
        logger.info("SoundService initialized.")

    def _play_sound(self, sound_path: str):
        """Воспроизводит звук в отдельном потоке, чтобы не блокировать GUI."""
        if not os.path.exists(sound_path):
            logger.warning(f"Sound file not found: {sound_path}")
            return
        try:
            threading.Thread(target=lambda: winsound.PlaySound(sound_path, winsound.SND_FILENAME), daemon=True).start()
        except Exception as e:
            logger.error(f"Could not play sound {sound_path}: {e}")

    def play_in(self):
        """Воспроизводит звук начала операции."""
        logger.debug("Playing 'in' sound.")
        self._play_sound(self.in_sound_path)

    def play_out(self):
        """Воспроизводит звук завершения операции."""
        logger.debug("Playing 'out' sound.")
        self._play_sound(self.out_sound_path)