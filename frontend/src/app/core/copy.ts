import { Clipboard } from '@angular/cdk/clipboard';
import { inject } from '@angular/core';

import { injectTranslator, TranslationPath } from './i18n';
import { injectNotify } from './notify';

/**
 * Copy a text and say whether it worked. The CDK copies without the async clipboard API, which plain HTTP does not
 * offer; the browser may still refuse.
 */
export function injectCopy(): (text: string, copied: TranslationPath<'app'>) => void {
  const clipboard = inject(Clipboard);
  const notify = injectNotify();
  const translate = injectTranslator('app');
  return (text, copied) => notify(translate(clipboard.copy(text) ? copied : 'app.errors.copyFailed'));
}
