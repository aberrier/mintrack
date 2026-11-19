import { Validators } from '@angular/forms';

/** The server's rules for a username: letters, digits, dots, dashes and underscores, up to 150. */
export const usernameValidators = [Validators.required, Validators.pattern(/^[A-Za-z0-9._-]{1,150}$/)];

/** The server's rules for a new password: 15 to 128 characters. */
export const newPasswordValidators = [Validators.required, Validators.minLength(15), Validators.maxLength(128)];
