import { expect } from '@playwright/test';
import { Viewer } from './fixtures';

/** Record the app's vibrations from now on; returns whether this phone can vibrate from a web page at all. */
export async function recordVibrations(viewer: Viewer): Promise<boolean> {
  await viewer.app.recordVibrations();
  return viewer.app.canVibrate();
}

/** The vibrations since the app last loaded, in milliseconds, oldest first. */
export function vibrations(viewer: Viewer): Promise<VibratePattern[]> {
  return viewer.app.vibrations();
}

/** Whether Settings offers to turn vibration on or off. */
export async function vibrationOffered(viewer: Viewer): Promise<boolean> {
  await viewer.app.openSettings();
  await viewer.app.settingsLoaded();
  return (await viewer.app.vibrationSwitch().count()) > 0;
}

export async function turnVibrationOff(viewer: Viewer): Promise<void> {
  await viewer.app.openSettings();
  const toggle = viewer.app.vibrationSwitch();
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect(toggle).not.toBeChecked();
}
