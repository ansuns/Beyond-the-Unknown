import type { LoginData } from "../network/types";

export class SessionStore {
  private current?: LoginData;

  set(session: LoginData): void {
    this.current = session;
  }

  accessToken(): string | undefined {
    return this.current?.access_token;
  }

  playerId(): string | undefined {
    return this.current?.player_id;
  }

  clear(): void {
    this.current = undefined;
  }

  isAuthenticated(): boolean {
    return Boolean(this.current?.access_token);
  }
}
