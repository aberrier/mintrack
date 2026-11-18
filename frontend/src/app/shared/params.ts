/** The `type` query parameter of a page: shows unless it says movie. */
export function mediaTypeParam(value: string | undefined): Model.Http.MediaType {
  return value === 'movie' ? 'movie' : 'tv';
}
