/** Shapes exchanged with the MinTrack API. */
declare namespace Model {
  namespace Http {
    interface HealthResponse {
      status: 'ok' | 'degraded';
      database: 'ok' | 'unavailable';
    }

    interface User {
      id: string;
      username: string;
      is_admin: boolean;
      timezone: string;
    }

    interface PasswordLink {
      username: string;
    }

    type UserStatus = 'invited' | 'invitation_expired' | 'active' | 'disabled';

    interface AdminUser {
      id: string;
      username: string;
      is_admin: boolean;
      status: UserStatus;
      last_seen_at: string | null;
    }

    interface Link {
      link: string;
    }

    interface CreatedUser extends Link {
      user: AdminUser;
    }

    type MediaType = 'movie' | 'tv';
    /** Shows: watch_later, watching, up_to_date, finished, stopped. Movies: watch_later, watched. */
    type TrackingStatus = 'watch_later' | 'watching' | 'up_to_date' | 'finished' | 'stopped' | 'watched';

    interface SearchResult {
      tmdb_id: number;
      media_type: MediaType;
      title: string;
      year: number | null;
      poster_path: string | null;
      tracking_status: TrackingStatus | null;
    }

    interface Episode {
      id: string;
      season_number: number;
      episode_number: number;
      title: string;
      /** ISO date, such as 2026-03-01. */
      air_date: string | null;
      /** ISO date-time in UTC, when the exact air time is known. */
      airstamp: string | null;
    }

    interface Season {
      season_number: number;
      title: string;
      episodes: Episode[];
    }

    interface ShowTracking {
      status: TrackingStatus;
      /** Episode id -> ISO date-time it was watched. */
      watched: Record<string, string>;
    }

    interface MovieTracking {
      status: TrackingStatus;
      watched_at: string | null;
    }

    interface Media {
      tmdb_id: number;
      title: string;
      overview: string;
      poster_path: string | null;
      release_date: string | null;
      tmdb_status: string | null;
    }

    interface Show extends Media {
      seasons: Season[];
      tracking: ShowTracking | null;
    }

    interface Movie extends Media {
      tracking: MovieTracking | null;
    }

    interface LibraryItem {
      tmdb_id: number;
      media_type: MediaType;
      title: string;
      poster_path: string | null;
      status: TrackingStatus;
      watched_count: number;
      aired_count: number;
    }
  }
}
