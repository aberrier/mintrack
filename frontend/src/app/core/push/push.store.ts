import { HttpErrorResponse, HttpStatusCode } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { SwPush } from '@angular/service-worker';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../api/api.service';
import { injectTranslator, TranslationPath } from '../i18n';

/**
 * - `install`: an iPhone or iPad browser tab; push needs the app added to the Home Screen.
 * - `unsupported`: no service worker or no push in this browser (or a plain-HTTP address).
 * - `unconfigured`: the server cannot send push.
 * - `blocked`: notifications are denied in the browser settings.
 */
export type PushState = 'loading' | 'install' | 'unsupported' | 'unconfigured' | 'blocked' | 'off' | 'on';

/** This device's push subscription, kept in step with the server. */
@Injectable({ providedIn: 'root' })
export class PushStore {
  private readonly swPush = inject(SwPush);
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = injectTranslator('app');

  private readonly supported = this.swPush.isEnabled && 'PushManager' in window && 'Notification' in window;
  /** undefined while loading, null when the server has no key. */
  private readonly $key = signal<string | null | undefined>(undefined);
  private readonly $permission = signal<NotificationPermission>(this.supported ? Notification.permission : 'default');
  /** undefined until the service worker controls the page (SwPush waits for it). */
  private readonly $subscription = signal<PushSubscription | null | undefined>(undefined);
  private readonly $pending = signal(false);

  readonly $busy = this.$pending.asReadonly();
  readonly $state = computed((): PushState => {
    if (!this.supported) return isIosBrowserTab() ? 'install' : 'unsupported';
    const key = this.$key();
    if (key === null) return 'unconfigured';
    if (key === undefined || this.$subscription() === undefined) return 'loading';
    if (this.$permission() === 'denied') return 'blocked';
    return this.$subscription() ? 'on' : 'off';
  });

  constructor() {
    if (!this.supported) return;
    this.api.push.key().subscribe({
      next: ({ public_key }) => {
        this.$key.set(public_key);
        if (public_key) void this.sync(public_key);
      },
      error: () => this.$key.set(null),
    });
  }

  /** Asks for permission first, while the tap still counts as a user gesture (Safari requires it). */
  async enable(): Promise<void> {
    const key = this.$key();
    if (!key) return;
    this.$pending.set(true);
    try {
      const permission = await Notification.requestPermission();
      this.$permission.set(permission);
      if (permission !== 'granted') return;
      const subscription = await this.swPush.requestSubscription({ serverPublicKey: key });
      await firstValueFrom(this.api.push.subscribe(subscription.toJSON()));
      this.$subscription.set(subscription);
    } catch {
      this.notify('app.push.errors.enable');
    } finally {
      this.$pending.set(false);
    }
  }

  async disable(): Promise<void> {
    const subscription = this.$subscription();
    if (!subscription) return;
    this.$pending.set(true);
    try {
      // A failure here leaves a dead subscription on the server, deleted on its first push.
      await firstValueFrom(this.api.push.unsubscribe(subscription.endpoint)).catch(() => undefined);
      await this.swPush.unsubscribe();
      this.$subscription.set(null);
    } catch {
      this.notify('app.push.errors.disable');
    } finally {
      this.$pending.set(false);
    }
  }

  async sendTest(): Promise<void> {
    const subscription = this.$subscription();
    if (!subscription) return;
    this.$pending.set(true);
    try {
      await firstValueFrom(this.api.push.test(subscription.endpoint));
      this.notify('app.push.test.sent');
    } catch (error: unknown) {
      if (error instanceof HttpErrorResponse && error.status === HttpStatusCode.NotFound) {
        await this.swPush.unsubscribe().catch(() => undefined);
        this.$subscription.set(null);
        this.notify('app.push.test.expired');
      } else {
        this.notify('app.push.test.failed');
      }
    } finally {
      this.$pending.set(false);
    }
  }

  /**
   * Sends the existing subscription again, so the server follows the signed-in user and a recreated database.
   * A subscription made for another server key (the secret key changed) is replaced without asking again.
   */
  private async sync(key: string): Promise<void> {
    let subscription: PushSubscription | null;
    try {
      subscription = await firstValueFrom(this.swPush.subscription);
      if (subscription && !madeFor(subscription, key)) {
        await subscription.unsubscribe();
        subscription = await this.swPush.requestSubscription({ serverPublicKey: key });
      }
    } catch {
      subscription = null;
    }
    this.$subscription.set(subscription);
    // A failure leaves the device as it is; the next start sends it again.
    if (subscription) this.api.push.subscribe(subscription.toJSON()).subscribe({ error: () => undefined });
  }

  private notify(message: TranslationPath<'app'>): void {
    this.snackBar.open(this.translate(message), undefined, { duration: 4000 });
  }
}

function madeFor(subscription: PushSubscription, key: string): boolean {
  const applicationServerKey = subscription.options.applicationServerKey;
  return applicationServerKey !== null && base64Url(applicationServerKey) === key;
}

function base64Url(buffer: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replace(/=+$/, '');
}

/** Safari on iOS and iPadOS defines `navigator.standalone`; it is false in a browser tab. */
function isIosBrowserTab(): boolean {
  return 'standalone' in navigator && navigator.standalone === false;
}
