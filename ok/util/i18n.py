from PySide6.QtCore import QLocale

from ok import Logger

logger = Logger.get_logger("i18n")


def get_language_fallbacks(locale_name: str) -> list[str]:
    """
    Generates a fallback list for a given locale name like 'en_US'.
    For Chinese locales, it maps them to either zh_CN or zh_TW.
    """
    # Special handling for Chinese locales to enforce strict fallbacks
    if locale_name.startswith('zh'):
        traditional_locales = {'zh_HK', 'zh_TW', 'zh_MO'}
        # Use QLocale to get the canonical name (e.g., zh-Hant-TW -> zh_TW)
        canonical_name = QLocale(locale_name).name()

        if canonical_name in traditional_locales:
            # If it's a Traditional Chinese locale, only allow zh_TW and then zh
            return ['zh_TW', 'zh']
        else:
            # Otherwise, default to Simplified and only allow zh_CN and then zh
            return ['zh_CN', 'zh']

    # --- Original logic for all other languages ---
    input_locale = QLocale(locale_name)
    target_language_enum = input_locale.language()

    target_name = input_locale.name()
    base_lang_locale = QLocale(target_language_enum)
    base_lang_code = base_lang_locale.name()
    fallbacks = []
    processed = set()

    fallbacks.append(target_name)
    processed.add(target_name)

    if base_lang_code != target_name and base_lang_code not in processed:
        fallbacks.append(base_lang_code)
        processed.add(base_lang_code)

    try:
        all_countries = list(QLocale.Country)

        for country_enum in all_countries:
            if country_enum == QLocale.Country.AnyCountry:
                continue
            variant_locale = QLocale(target_language_enum, country_enum)
            variant_name = variant_locale.name()
            if variant_locale.language() != QLocale.Language.C and variant_name not in processed:
                fallbacks.append(variant_name)
                processed.add(variant_name)
    except Exception as e:
        logger.error(f"Warning: Could not iterate through QLocale.Country enums", e)

    return fallbacks
