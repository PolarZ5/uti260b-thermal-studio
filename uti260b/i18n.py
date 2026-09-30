"""Thai / English user interface text.

Source strings in the code are Thai; tr() returns the English text when the
language is 'en'. Templates use str.format placeholders: tr("… {n} …", n=3).
The language is chosen once at start-up (switching restarts the app).
"""
import sys

from .i18n_en import EN

LANGUAGES = {"th": "ไทย", "en": "English"}
_lang = "th"


def system_language() -> str:
    """'th' when Windows' UI language is Thai, otherwise 'en'."""
    if sys.platform == "win32":
        try:
            import ctypes
            return "th" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x1E else "en"
        except Exception:
            pass
    import locale
    return "th" if (locale.getlocale()[0] or "").lower().startswith("th") else "en"


def set_language(lang: str):
    global _lang
    _lang = lang if lang in LANGUAGES else "en"


def language() -> str:
    return _lang


def tr(text: str, **kw) -> str:
    s = EN.get(text, text) if _lang == "en" else text
    return s.format(**kw) if kw else s
