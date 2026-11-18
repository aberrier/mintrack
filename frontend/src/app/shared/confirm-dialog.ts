import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButton } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialog,
  MatDialogActions,
  MatDialogClose,
  MatDialogContent,
  MatDialogTitle,
} from '@angular/material/dialog';
import { filter, Observable } from 'rxjs';
import { injectTranslator } from '../core/i18n';

export interface ConfirmDialogData {
  title: string;
  message: string;
  confirm: string;
}

/** A yes / no question; closes with true when confirmed. */
@Component({
  selector: 'app-confirm-dialog',
  imports: [MatButton, MatDialogActions, MatDialogClose, MatDialogContent, MatDialogTitle],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content class="break-words">{{ data.message }}</mat-dialog-content>
    <mat-dialog-actions align="end">
      <button matButton type="button" [mat-dialog-close]="false">{{ translate('app.common.cancel') }}</button>
      <button matButton type="button" [mat-dialog-close]="true">{{ data.confirm }}</button>
    </mat-dialog-actions>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ConfirmDialog {
  protected readonly translate = injectTranslator('app');
  protected readonly data = inject<ConfirmDialogData>(MAT_DIALOG_DATA);
}

/** Ask a yes / no question: the observable emits once, only if the user confirms. */
export function injectConfirm(): (data: ConfirmDialogData) => Observable<true> {
  const dialog = inject(MatDialog);
  return (data) =>
    dialog
      .open<ConfirmDialog, ConfirmDialogData, boolean>(ConfirmDialog, { data })
      .afterClosed()
      .pipe(filter((confirmed): confirmed is true => confirmed === true));
}
