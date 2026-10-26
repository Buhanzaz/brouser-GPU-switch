"""Unit tests for the five-language layer in :mod:`app.i18n`."""

from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock

from app import i18n
from app.state import ENV_DATA_DIR


class LanguageCatalogTests(unittest.TestCase):
    """The catalogue must cover the five languages promised in the UI."""

    def test_supported_languages(self) -> None:
        self.assertEqual(i18n.SUPPORTED_LANGUAGES, ("ru", "en", "zh", "es", "de"))
        self.assertEqual([code for code, _ in i18n.LANGUAGES], list(i18n.SUPPORTED_LANGUAGES))

    def test_every_language_has_the_same_keys(self) -> None:
        reference = set(i18n.TRANSLATIONS[i18n.DEFAULT_LANGUAGE])
        for code in i18n.SUPPORTED_LANGUAGES:
            self.assertEqual(set(i18n.TRANSLATIONS[code]), reference, code)

    def test_russian_is_the_canonical_wording(self) -> None:
        self.assertEqual(i18n.DEFAULT_LANGUAGE, "ru")
        self.assertEqual(
            i18n.Translator().t("ready_title"),
            "Все настроено, запустите браузер",
        )

    def test_version_label_says_release(self) -> None:
        self.assertEqual(i18n.Translator("ru").t("version_label", version="1.0.0"), "релиз 1.0.0")
        self.assertEqual(
            i18n.Translator("en").t("version_label", version="1.0.0"), "release 1.0.0"
        )


class TranslatorTests(unittest.TestCase):
    def test_normalizes_language_tags(self) -> None:
        self.assertEqual(i18n.normalize_language("en-US"), "en")
        self.assertEqual(i18n.normalize_language("zh_CN"), "zh")
        self.assertEqual(i18n.normalize_language("de"), "de")
        self.assertIsNone(i18n.normalize_language("fr"))
        self.assertIsNone(i18n.normalize_language(""))

    def test_unknown_language_falls_back_to_russian(self) -> None:
        translator = i18n.Translator("fr")
        self.assertEqual(translator.language, "ru")
        self.assertEqual(translator.t("apply"), "Применить")

    def test_missing_key_falls_back_to_russian(self) -> None:
        translator = i18n.Translator("en")
        self.assertEqual(translator.t("no_such_key"), "no_such_key")

    def test_format_placeholders(self) -> None:
        translator = i18n.Translator("es")
        self.assertIn("2", translator.t("gpu_found", count=2))

    def test_language_name(self) -> None:
        self.assertEqual(i18n.language_name("zh"), "中文")
        self.assertEqual(i18n.language_name("xx"), "xx")


class OptionTextTests(unittest.TestCase):
    """Backend options are always Russian; they are mapped for other languages."""

    def test_russian_is_returned_unchanged(self) -> None:
        translator = i18n.Translator("ru")
        label = "Высокая производительность — NVIDIA GeForce GTX 1050 Ti"
        self.assertEqual(i18n.translate_option_label(label, translator), label)
        self.assertEqual(i18n.translate_option_description("", translator), "")

    def test_prefix_label_is_translated_keeping_the_gpu_name(self) -> None:
        translator = i18n.Translator("en")
        translated = i18n.translate_option_label(
            "Высокая производительность — NVIDIA GeForce GTX 1050 Ti", translator
        )
        self.assertIn("High performance", translated)
        self.assertIn("NVIDIA GeForce GTX 1050 Ti", translated)

    def test_exact_label_is_translated(self) -> None:
        translator = i18n.Translator("de")
        self.assertEqual(
            i18n.translate_option_label("По умолчанию — Windows выбирает сам", translator),
            "Standard — Windows wählt",
        )

    def test_known_description_is_translated(self) -> None:
        translator = i18n.Translator("es")
        translated = i18n.translate_option_description(
            "Встроенная графика: тише и экономичнее, но слабее в играх и 3D.",
            translator,
        )
        self.assertIn("Gráficos integrados", translated)

    def test_unknown_text_is_returned_unchanged(self) -> None:
        translator = i18n.Translator("en")
        self.assertEqual(
            i18n.translate_option_label("Произвольная строка", translator),
            "Произвольная строка",
        )


class SavedLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        # A temporary directory inside the workspace: the system temp folder is
        # not always writable for the tests that run in a sandboxed session.
        self._dir = Path("scratch") / ("i18n-test-" + uuid.uuid4().hex)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self._dir, True)
        patcher = mock.patch.dict(os.environ, {ENV_DATA_DIR: str(self._dir)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_and_load_round_trip(self) -> None:
        i18n.save_language("zh")
        self.assertEqual(i18n.load_saved_language(), "zh")
        self.assertTrue((self._dir / i18n.SETTINGS_FILE_NAME).is_file())

    def test_missing_settings_returns_none(self) -> None:
        self.assertIsNone(i18n.load_saved_language())

    def test_broken_settings_returns_none(self) -> None:
        (self._dir / i18n.SETTINGS_FILE_NAME).write_text("{", encoding="utf-8")
        self.assertIsNone(i18n.load_saved_language())

    def test_initial_language_prefers_the_saved_choice(self) -> None:
        i18n.save_language("es")
        self.assertEqual(i18n.initial_language(), "es")


if __name__ == "__main__":
    unittest.main()
