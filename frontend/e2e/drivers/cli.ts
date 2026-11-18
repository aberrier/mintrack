import { execFileSync } from 'node:child_process';

/**
 * The `mintrack` command of the running stack. In CI it runs inside the compose service; set MINTRACK_E2E_CLI to run
 * it another way (for example `uv run mintrack` against a local server).
 */
const command = process.env['MINTRACK_E2E_CLI'] ?? 'docker compose exec -T server mintrack';

/** Create an admin and return the password link the command prints. */
export function createAdmin(username: string): string {
  const output = execFileSync('sh', ['-c', `${command} users create-admin "$0"`, username], {
    cwd: '..',
    encoding: 'utf8',
  });
  return output.trim();
}
