import catalogs from "./catalogs.json";

type Locale = keyof typeof catalogs;
type Parameters = Record<string, string | number>;

function resolveLocale(language: string): Locale {
  const normalized = language.replace("-", "_");
  if (normalized.startsWith("zh")) {
    return /(?:Hant|HK|MO|TW)/i.test(normalized) ? "zh_TW" : "zh_CN";
  }
  const base = normalized.split("_")[0];
  const match = (Object.keys(catalogs) as Locale[]).find(
    (locale) => locale === normalized || locale.startsWith(`${base}_`)
  );
  return match ?? "en_US";
}

export const locale = resolveLocale(navigator.language);

export function t(source: string, parameters: Parameters = {}): string {
  const catalog = catalogs[locale] as Record<string, string>;
  const translated = catalog[source] ?? source;
  return Object.entries(parameters).reduce(
    (value, [key, replacement]) => value.replaceAll(`{${key}}`, String(replacement)),
    translated
  );
}
