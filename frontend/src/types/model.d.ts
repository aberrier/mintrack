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
    /** What a user sets on a show; the other statuses follow from the episodes watched. */
    type ShowTrackingChoice = 'watching' | 'watch_later' | 'stopped';

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
      backdrop_path: string | null;
      /** The show's first network, or null. */
      network: string | null;
      /** The movie's length in minutes, or null. */
      runtime: number | null;
    }

    interface Show extends Media {
      seasons: Season[];
      tracking: ShowTracking | null;
    }

    interface Movie extends Media {
      tracking: MovieTracking | null;
    }

    type LibrarySort = 'last_watched' | 'last_added' | 'title';
    /** A tracking status, or not_started: in the library with nothing watched. */
    type LibraryStatus = TrackingStatus | 'not_started';

    interface LibraryItem {
      tmdb_id: number;
      media_type: MediaType;
      title: string;
      poster_path: string | null;
      status: TrackingStatus;
      watched_count: number;
      aired_count: number;
      added_at: string;
      last_watched_at: string | null;
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

    /** next: watched within 30 days; dormant: not watched since, or never. */
    type WatchListSection = 'next' | 'dormant';

    interface WatchListEpisode extends UpcomingEpisode {
      /** Aired regular episodes after this one that the user has not watched. */
      remaining: number;
      last_watched_at: string | null;
      section: WatchListSection;
    }

    interface WatchListResponse {
      /** Most recently watched first. */
      episodes: WatchListEpisode[];
    }

    interface HistoryEntry {
      /** The episode's id, or the movie's: with watched_at, the cursor of the next page. */
      id: string;
      media_type: MediaType;
      tmdb_id: number;
      title: string;
      poster_path: string | null;
      /** null for movies. */
      season_number: number | null;
      episode_number: number | null;
      episode_title: string | null;
      watched_at: string;
    }

    interface HistoryResponse {
      /** Newest first. */
      entries: HistoryEntry[];
      has_more: boolean;
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

    interface ApiToken {
      id: string;
      name: string;
      created_at: string;
      last_used_at: string | null;
    }

    interface CreatedApiToken extends ApiToken {
      token: string;
    }
  }
}
