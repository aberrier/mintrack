import app from './translations/app.en';
import type profileTexts from './translations/profile.en';

export { injectTranslator, loadProfileTexts, withProfileTexts, type AppTranslate, type TranslationPath };

/** The translator of the app's texts, for helpers that take it from their component. */
type AppTranslate = ReturnType<typeof injectTranslator<['app']>>;

/**
 * Inject a translator for the given kinds of translations.
 * The English texts are bundled with the app, so they are available from the first render, except the Profile tab's,
 * which load with its pages (`withProfileTexts`).
 *
 * @example
 * ```html
 * <h1>{{ translate('app.nav.profile') }}</h1>
 * <p>{{ translate('app.admin.link.intro', { username }) }}</p>
 * ```
 *
 * ```typescript
 * class Profile {
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

const translations = { app: { ...app } as typeof app & typeof profileTexts };

/** Adds the Profile tab's texts, kept out of the initial bundle. */
async function loadProfileTexts(): Promise<void> {
  Object.assign(translations.app, (await import('./translations/profile.en')).default);
}

/** A page of the Profile tab, loaded together with its texts. */
async function withProfileTexts<T>(page: Promise<T>): Promise<T> {
  const [loaded] = await Promise.all([page, loadProfileTexts()]);
  return loaded;
}

type Translations = typeof translations;
type TranslationKinds = keyof Translations;

/** Given translation kinds, the paths available, such as `app.watchList.emptyTitle`. */
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
