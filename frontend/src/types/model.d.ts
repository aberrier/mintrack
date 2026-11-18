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
  }
}
