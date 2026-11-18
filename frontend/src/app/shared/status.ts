import { injectTranslator } from '../core/i18n';

/** A function giving the label of a tracking status. */
export function injectStatusLabel(): (status: Model.Http.TrackingStatus) => string {
  const translate = injectTranslator('app');
  return (status) => translate(`app.status.${status}`);
}
