/** A TMDB image: posters at w185 (lists) or w342 (grids), backdrops at w780. */
export function imageUrl(path: string | null, width: 'w185' | 'w342' | 'w780'): string | null {
  return path ? `https://image.tmdb.org/t/p/${width}${path}` : null;
}
