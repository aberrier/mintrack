import { ChangeDetectionStrategy, Component } from '@angular/core';
import { MatButton } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import { appRoutes } from '../../../app.paths';
import { injectTranslator, TranslationPath } from '../../../core/i18n';
import { PhonePlatform, platformsFor } from '../../../core/push/platform';
import { BackButton } from '../../../shared/back-button';

interface Guide {
  title: TranslationPath<'app'>;
  steps: TranslationPath<'app'>[];
  /** What to check when nothing arrives. */
  troubleshoot: TranslationPath<'app'>;
}

const GUIDES: Record<PhonePlatform, Guide> = {
  android: {
    title: 'app.pushHelp.android.title',
    steps: ['app.pushHelp.android.open', 'app.pushHelp.android.install', 'app.pushHelp.turnOn'],
    troubleshoot: 'app.pushHelp.android.troubleshoot',
  },
  ios: {
    title: 'app.pushHelp.ios.title',
    steps: ['app.pushHelp.ios.open', 'app.pushHelp.ios.install', 'app.pushHelp.turnOn'],
    troubleshoot: 'app.pushHelp.ios.troubleshoot',
  },
};

/** How to get episode notifications on a phone: the visitor's system first, then the other, the test, the needs. */
@Component({
  selector: 'app-push-help',
  imports: [BackButton, MatButton, RouterLink],
  templateUrl: './push-help.html',
  styleUrl: '../help-page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class PushHelp {
  protected readonly translate = injectTranslator('app');
  protected readonly appRoutes = appRoutes;
  protected readonly guides = platformsFor(navigator).map((platform) => ({ platform, ...GUIDES[platform] }));
}
