"""
Тесты для модуля нормализации городов.

Запуск:
python tests/test_city_normalizer.py
"""

import sys
import os

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.utils.city_normalizer import normalize_city


class TestCityNormalizer:
    """Тесты функции normalize_city"""
    
    def test_moscow_variants(self):
        """Тест всех вариантов написания Москвы"""
        expected = "москва"
        
        test_cases = [
            "Москва",
            "москва",
            "МСК",
            "мск",
            "MSK",
            "Moscow",
            "Moskow",
            "МОСКВА",
            "  Москва  ",
            "г. Москва",
            "Москва.",
        ]
        
        for city in test_cases:
            result = normalize_city(city)
            assert result == expected, f"Для '{city}' ожидалось '{expected}', получено '{result}'"
    
    def test_saint_petersburg_variants(self):
        """Тест всех вариантов написания Санкт-Петербурга"""
        expected = "санкт-петербург"
        
        test_cases = [
            "Санкт-Петербург",
            "санкт-петербург",
            "Санкт петербург",
            "санкт петербург",
            "СПБ",
            "спб",
            "Питер",
            "питер",
            "Петербург",
            "петербург",
            "spb",
            "SPB",
            "Saint Petersburg",
            "saint petersburg",
            "  Санкт-Петербург  ",
            "г. Санкт-Петербург",
        ]
        
        for city in test_cases:
            result = normalize_city(city)
            assert result == expected, f"Для '{city}' ожидалось '{expected}', получено '{result}'"
    
    def test_yekaterinburg_variants(self):
        """Тест всех вариантов написания Екатеринбурга"""
        expected = "екатеринбург"
        
        test_cases = [
            "Екатеринбург",
            "екатеринбург",
            "ЕКБ",
            "екб",
            "EKB",
            "ekb",
            "Yekaterinburg",
            "yekaterinburg",
            "  Екатеринбург  ",
        ]
        
        for city in test_cases:
            result = normalize_city(city)
            assert result == expected, f"Для '{city}' ожидалось '{expected}', получено '{result}'"
    
    def test_unknown_city(self):
        """Тест неизвестного города (без алиасов)"""
        expected = "тула"
        
        test_cases = [
            "Тула",
            "тула",
            "ТУЛА",
            "  Тула  ",
            "Тула.",
        ]
        
        for city in test_cases:
            result = normalize_city(city)
            assert result == expected, f"Для '{city}' ожидалось '{expected}', получено '{result}'"
    
    def test_empty_string(self):
        """Тест пустой строки"""
        assert normalize_city("") == ""
        assert normalize_city(None) == ""
    
    def test_whitespace_only(self):
        """Тест строки только из пробелов"""
        assert normalize_city("   ") == ""
        assert normalize_city("  \t  ") == ""
    
    def test_special_characters_removal(self):
        """Тест удаления специальных символов"""
        # Для неизвестного города
        assert normalize_city("Тула!!!") == "тула"
        assert normalize_city("Тула, Москва") == "тула москва"
    
    def test_multiple_spaces(self):
        """Тест замены множественных пробелов"""
        assert normalize_city("Санкт  Петербург") == "санкт-петербург"
        assert normalize_city("  Москва   город  ") == "москва город"
    
    def test_case_insensitive(self):
        """Тест, что регистр не влияет на результат"""
        assert normalize_city("МОСКВА") == normalize_city("москва")
        assert normalize_city("СПБ") == normalize_city("спб")


if __name__ == "__main__":
    test = TestCityNormalizer()
    
    print("Запуск тестов нормализации городов...")
    print("=" * 50)
    
    try:
        test.test_moscow_variants()
        print("✅ test_moscow_variants пройден")
    except AssertionError as e:
        print(f"❌ test_moscow_variants провален: {e}")
    
    try:
        test.test_saint_petersburg_variants()
        print("✅ test_saint_petersburg_variants пройден")
    except AssertionError as e:
        print(f"❌ test_saint_petersburg_variants провален: {e}")
    
    try:
        test.test_yekaterinburg_variants()
        print("✅ test_yekaterinburg_variants пройден")
    except AssertionError as e:
        print(f"❌ test_yekaterinburg_variants провален: {e}")
    
    try:
        test.test_unknown_city()
        print("✅ test_unknown_city пройден")
    except AssertionError as e:
        print(f"❌ test_unknown_city провален: {e}")
    
    try:
        test.test_empty_string()
        print("✅ test_empty_string пройден")
    except AssertionError as e:
        print(f"❌ test_empty_string провален: {e}")
    
    try:
        test.test_whitespace_only()
        print("✅ test_whitespace_only пройден")
    except AssertionError as e:
        print(f"❌ test_whitespace_only провален: {e}")
    
    try:
        test.test_special_characters_removal()
        print("✅ test_special_characters_removal пройден")
    except AssertionError as e:
        print(f"❌ test_special_characters_removal провален: {e}")
    
    try:
        test.test_multiple_spaces()
        print("✅ test_multiple_spaces пройден")
    except AssertionError as e:
        print(f"❌ test_multiple_spaces провален: {e}")
    
    try:
        test.test_case_insensitive()
        print("✅ test_case_insensitive пройден")
    except AssertionError as e:
        print(f"❌ test_case_insensitive провален: {e}")
    
    print("=" * 50)
    print("Все тесты завершены!")
