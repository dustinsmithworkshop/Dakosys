// API response types for DAKOSYS web dashboard

export interface ServiceStatus {
  enabled: boolean;
  running: boolean;
  next_run: string | null;
}

export interface StatusStats {
  total_shows: number;
  total_libraries: number;
  total_size_gb: number;
}

export interface StatusResponse {
  services: {
    anime_episode_type: ServiceStatus;
    tv_status_tracker: ServiceStatus;
    size_overlay: ServiceStatus;
  };
  stats: StatusStats;
  trakt: {
    required: boolean;
    configured: boolean;
    features: {
      auto_schedule: boolean;
      legacy_episode_publishing: boolean;
    };
  };
  config_missing?: boolean;
}

export interface TVShow {
  title: string;
  status: string;
  date: string;
  text: string;
}

export interface TVStatusResponse {
  shows: TVShow[];
}

export interface LibraryItem {
  title: string;
  size_gb: number;
  episode_count?: number;
}

export interface Library {
  name: string;
  total_size_gb: number;
  item_count: number;
  episode_count: number | null;
  last_updated: string;
  items: LibraryItem[];
}

export interface LibrariesResponse {
  libraries: Library[];
}

export interface ConfigResponse {
  config: string;
  error?: string;
}

export interface LogsResponse {
  lines: string[];
  service: string;
}

export interface RunResponse {
  started: boolean;
  message: string;
}

export interface RunStatusResponse {
  service: string;
  running: boolean;
}

export type ServiceName = "anime_episode_type" | "tv_status_tracker" | "size_overlay";

export interface AnimeEntry {
  afl_name: string;
  display_name: string;
  trakt_title?: string;
  trakt_status?: string;
  decision?: string;
  override?: "include" | null;
}

export interface AnimeScheduleResponse {
  anime: AnimeEntry[];
  count: number;
  auto_enabled: boolean;
  generated_at?: string | null;
  source?: string | null;
  schedule_path?: string;
  review_count?: number;
  ignored_count?: number;
  stats?: Record<string, number>;
  always_include?: string[];
  always_exclude?: string[];
  error?: string | null;
}

export interface PlexShowsResponse {
  shows: string[];
  error: string | null;
}

export interface AflSearchResponse {
  shows: string[];
  error: string | null;
}

export interface AflEpisodeCounts {
  [episodeType: string]: number;
}

export interface AflEpisodesResponse {
  afl_name: string;
  counts: AflEpisodeCounts;
  total: number;
  error: string | null;
}

export interface AddAnimeResponse {
  success: boolean;
  afl_name: string;
  plex_name: string;
  schedule_override?: "include" | null;
  refresh_required?: boolean;
}

export interface AnimeScheduleOverrideResponse {
  success: boolean;
  afl_name: string;
  mode: "include" | "exclude" | "auto";
  always_include: string[];
  always_exclude: string[];
  refresh_required: boolean;
}

export interface FailedEpisodeDetail {
  number: number | null;
  name: string;
}

export interface MappingError {
  anime_name: string;
  episode_type: string;
  plex_name: string;
  failed_episodes: string[];
  failed_episode_details: FailedEpisodeDetail[];
  details: string[];
  timestamp: string;
}

export interface MappingErrorsResponse {
  errors: MappingError[];
  count: number;
  error?: string;
}

export interface FixMappingResponse {
  success: boolean;
  saved: number;
}

export interface TitleMappingEntry {
  plex_title: string;
  trakt_title: string;
}

export interface TitleMappingGroup {
  anime_name: string;
  matches: TitleMappingEntry[];
}

export interface TitleMappingsResponse {
  mappings: TitleMappingGroup[];
  count: number;
  error?: string;
}

export interface NextAiringShow {
  rank: number;
  title: string;
  year: number | null;
  library: string;
  plex_rating_key: string;
  tmdb_id: number | null;
  tvdb_id: number | null;
  imdb_id: string | null;
  external_url: string | null;
  poster_url: string | null;
  status: string;
  date: string;
  source: string;
  season: number | null;
  episode: number | null;
  episode_title: string | null;
}

export interface NextAiringResponse {
  shows: NextAiringShow[];
  count: number;
  generated_at?: string | null;
  timezone?: string | null;
  error?: string;
}

export interface PlexLibrarySection {
  title: string;
  type: "show" | "movie";
}

export interface PlexLibrariesSetupResponse {
  libraries: PlexLibrarySection[];
  error: string | null;
}

export interface TraktAuthStatus {
  connected: boolean;
  configured: boolean;
  username: string;
  client_id: string;
  client_secret_configured: boolean;
  token_expiry: number | null;
}

export interface TraktOverviewResponse {
  configured: boolean;
  required: boolean;
  requirements: {
    auto_schedule: boolean;
    legacy_episode_publishing: boolean;
  };
  legacy_episode_publishing: boolean;
  list_privacy: string | null;
  usage: {
    username: string | null;
    vip: boolean | null;
    vip_ep: boolean | null;
    limits_known: boolean;
    lists: {
      current: number;
      maximum: number | null;
      remaining: number | null;
    };
    items_per_list: {
      maximum: number | null;
    };
  } | null;
  error: string | null;
}

export interface TraktDeviceCodeResponse {
  device_code: string;
  user_code: string;
  verification_url: string;
  expires_in: number;
  interval: number;
}

export interface TraktDevicePollResponse {
  authorized: boolean;
  pending?: boolean;
  access_token?: string;
  error?: string;
}

export interface SetupResponse {
  success: boolean;
}

export interface TraktTestResult {
  config_ok: boolean;
  config_username: string | null;
  token_exists: boolean;
  token_has_refresh: boolean;
  token_expires_in_days: number | null;
  auth_ok: boolean;
  authenticated_username: string | null;
  username_match: boolean | null;
  total_lists: number | null;
  dakosys_lists: number | null;
  error: string | null;
}

export interface IgnoredMappingEntry {
  anime_name: string;
  episode_type: string;
  plex_name: string;
}

export interface IgnoredMappingsResponse {
  ignored: IgnoredMappingEntry[];
  error?: string;
}
