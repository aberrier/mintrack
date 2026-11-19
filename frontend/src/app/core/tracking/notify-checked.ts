import { injectTranslator } from '../i18n';
import { injectNotifyUndo } from '../notify';
import { episodeCode } from './episodes';

/** Say which episode a check marked watched, with an Undo action that runs `undo`. */
export function injectNotifyChecked(): (season: number, episode: number, undo: () => void) => void {
  const notifyUndo = injectNotifyUndo();
  const translate = injectTranslator('app');
  return (season, episode, undo) => {
    notifyUndo(translate('app.common.checked', { episode: episodeCode(season, episode, true) }), undo);
  };
}
