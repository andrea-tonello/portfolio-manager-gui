import json
import os

from utils.constants import DEFAULT_LANG, I18N_DIR


class Translator:
    def __init__(self, language_code=DEFAULT_LANG, locales_dir=None):
        self.language_code = language_code
        self.strings = {}
        self.locales_dir = locales_dir or I18N_DIR
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

    def load_text(self, name):
        """Return the longer text `<name>_<language>.txt` from the translations folder (Markdown, for the dialogs).

        Falls back to the English text when there is none in the current
        language, and returns None when there is none at all.
        Example: load_text("privacy_policy") reads privacy_policy_it.txt when the app is in Italian.
        """
        for language in dict.fromkeys([self.language_code, DEFAULT_LANG]):
            try:
                with open(os.path.join(self.locales_dir, f"{name}_{language}.txt"), encoding="utf-8") as f:
                    return f.read()
            except FileNotFoundError:
                pass
        return None
