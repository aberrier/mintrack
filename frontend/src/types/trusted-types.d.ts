/** The part of the Trusted Types API the app uses; TypeScript's DOM library does not declare it yet. */
interface Window {
  trustedTypes?: {
    createPolicy(name: string, rules: { createScriptURL?: (url: string) => string | null }): unknown;
  };
}
