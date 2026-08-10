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
        canonical_name = locale_name.replace('-', '_')

        if canonical_name in traditional_locales:
            # If it's a Traditional Chinese locale, only allow zh_TW and then zh
            return ['zh_TW', 'zh']
        else:
            # Otherwise, default to Simplified and only allow zh_CN and then zh
            return ['zh_CN', 'zh']

    # --- Original logic for all other languages ---
    target_name = locale_name.replace('-', '_')
    base_lang_code = target_name.split('_', 1)[0]
    return [target_name] if target_name == base_lang_code else [target_name, base_lang_code]
