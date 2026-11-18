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

    interface UpcomingEpisode {
      episode_id: string;
      tmdb_id: number;
      show_title: string;
      poster_path: string | null;
      season_number: number;
      episode_number: number;
      title: string;
      /** Exact UTC air time, or null when only the day is known. */
      airstamp: string | null;
      /** The air day (YYYY-MM-DD) in the user's time zone, or null when unknown. */
      day: string | null;
    }

    interface UpcomingDay {
      day: string;
      episodes: UpcomingEpisode[];
    }

    interface UpcomingResponse {
      /** The user's IANA time zone, in which days are grouped and times shown. */
      time_zone: string;
      new: UpcomingEpisode[];
      days: UpcomingDay[];
    }

    interface UpNextResponse {
      episodes: UpcomingEpisode[];
    }

    interface PushKeyResponse {
      /** null when the server cannot send push. */
      public_key: string | null;
    }

    type JellyfinSyncStatus = 'ok' | 'unreachable' | 'unauthorized' | 'failed';

    interface JellyfinAccount {
      id: string;
      server_url: string;
      username: string;
      last_sync_at: string | null;
      last_success_at: string | null;
      last_sync_status: JellyfinSyncStatus | null;
      last_sync_imported: number;
      last_sync_skipped: number;
    }

    interface JellyfinLinkRequest {
      server_url: string;
      username: string;
      password: string;
    }

    type JellyfinLinkError =
      | 'jellyfin_invalid_credentials'
      | 'jellyfin_forbidden_address'
      | 'jellyfin_unreachable'
      | 'jellyfin_redirected'
      | 'jellyfin_bad_response';

    type ImportSource = 'yamtrack' | 'tvtime';
    type UnmatchedReason = 'unsupported' | 'not_found' | 'episode_not_found' | 'tmdb_unavailable';

    interface ImportJob {
      id: string;
      source: ImportSource;
      status: 'pending' | 'running' | 'done' | 'failed';
      filename: string;
      total: number;
      processed: number;
      report: {
        imported: number;
        already_present: number;
        unmatched_count: number;
        unmatched: { title: string; reason: UnmatchedReason }[];
      } | null;
      created_at: string;
      finished_at: string | null;
    }
  }
}
