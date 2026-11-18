import app from './translations/app.en';

export { injectTranslator, type TranslationPath };

/**
 * Inject a translator for the given kinds of translations.
 * The English texts are bundled with the app, so they are available from the first render.
 *
 * @example
 * ```html
 * <h1>{{ translate('app.home.title') }}</h1>
 * <p>{{ translate('app.adminUsers.link.intro', { username }) }}</p>
 * ```
 *
 * ```typescript
 * class HomePage {
 *   protected readonly translate = injectTranslator('app');
 * }
 * ```
 */
function injectTranslator<K extends TranslationKinds[]>(..._kinds: K) {
  return (path: TranslationPath<K[number]>, params: Record<string, string> = {}): string => {
    let target: unknown = translations;
    for (const crumb of path.split('.')) target = (target as Record<string, unknown> | undefined)?.[crumb];
    if (typeof target !== 'string') throw new Error(`Missing translation: ${path}`);
    return target.replace(/\{(\w+)\}/g, (placeholder, name: string) => params[name] ?? placeholder);
  };
}

const translations = { app };

type Translations = typeof translations;
type TranslationKinds = keyof Translations;

/** Given translation kinds, the paths available, such as `app.home.status.online`. */
type TranslationPath<K extends TranslationKinds> = string & PathInto<Pick<Translations, K>>;

type PathInto<T extends object> = keyof {
  [
    K in keyof T as T[K] extends string
      ? `${K & string}`
      : T[K] extends object
        ? `${K & string}.${PathInto<T[K]> & string}`
        : never
  ]: never;
};
