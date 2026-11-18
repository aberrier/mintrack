/** Shapes exchanged with the MinTrack API. */
declare namespace Model {
  namespace Http {
    interface HealthResponse {
      status: 'ok' | 'degraded';
      database: 'ok' | 'unavailable';
    }
  }
}
