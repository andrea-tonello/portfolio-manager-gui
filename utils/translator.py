import json
import os
import sys


class Translator:
    def __init__(self, language_code="en", locales_dir=None):
        self.language_code = language_code
        self.strings = {}
        if locales_dir:
            self.locales_dir = locales_dir
        elif getattr(sys, "frozen", False):
            self.locales_dir = os.path.join(sys._MEIPASS, "locales")
        else:
            self.locales_dir = os.path.join(os.getcwd(), "locales")
        self.load_language(language_code)

    def load_language(self, language_code):
        self.language_code = language_code
        path = os.path.join(self.locales_dir, f"{language_code}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.strings = json.load(f)
        except FileNotFoundError:
            self.strings = {}

    def get(self, key, **kwargs):
        try:
            keys = key.split(".")
            value = self.strings
            for k in keys:
                value = value[k]
            template = value
            return template.format(**kwargs)
        except (KeyError, TypeError, AttributeError):
            return f"<{key}>"
