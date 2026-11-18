/** SVG files are imported as text (angular.json `loader`), so only the icons we use are bundled. */
declare module '*.svg' {
  const content: string;
  export default content;
}
