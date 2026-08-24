"use client";

import {
  useCallback,
  useEffect,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  Card,
  CardBody,
  Chip,
  Spinner,
} from "@nextui-org/react";

import { api } from "@/lib/api";
import type {
  AnimeScheduleResponse,
  ArtworkRunRecord,
  StatusResponse,
} from "@/types/api";

import { ServiceHealthCard } from "@/components/dashboard/ServiceHealthCard";
import { StatsCard } from "@/components/dashboard/StatsCard";
import { NumberTicker } from "@/components/ui/number-ticker";
import { BackgroundBeams } from "@/components/ui/background-beams";

const SERVICE_LABELS: Record<string, string> = {
  anime_episode_type: "Anime Episode Type",
  tv_status_tracker: "TV Status",
  size_overlay: "Size Overlay",
};

function artworkRunAge(
  value: string
): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  const seconds = Math.max(
    0,
    Math.floor(
      (Date.now() - date.getTime()) / 1000
    )
  );

  if (seconds < 60) {
    return "just now";
  }

  const minutes = Math.floor(
    seconds / 60
  );

  if (minutes < 60) {
    return `${minutes} min ago`;
  }

  const hours = Math.floor(
    minutes / 60
  );

  if (hours < 24) {
    return `${hours} hr${
      hours === 1 ? "" : "s"
    } ago`;
  }

  const days = Math.floor(
    hours / 24
  );

  return `${days} day${
    days === 1 ? "" : "s"
  } ago`;
}


function artworkRunResult(
  run: ArtworkRunRecord | null
): string {
  if (!run) {
    return "No run recorded";
  }

  if (run.summary.failed > 0) {
    return "Failed";
  }

  if (run.summary.blocked > 0) {
    return "Blocked";
  }

  if (run.summary.pending_review > 0) {
    return "Pending Review";
  }

  if (run.summary.applied > 0) {
    return "Applied";
  }

  if (run.summary.no_changes > 0) {
    return "No Changes";
  }

  return "No Results";
}


function artworkRunCoverage(
  run: ArtworkRunRecord | null
): string {
  if (!run) {
    return "—";
  }

  const shows = run.libraries.filter(
    (library) =>
      library.media_type === "show"
  );

  const expected = shows.reduce(
    (total, library) =>
      total +
      library.coverage.expected_episodes,
    0
  );

  const cards = shows.reduce(
    (total, library) =>
      total +
      library.coverage.cards_after,
    0
  );

  if (expected <= 0) {
    return "—";
  }

  return `${(
    (cards / expected) *
    100
  ).toFixed(1)}%`;
}


function ArtworkStatusCard({
  artwork,
  latestRun,
}: {
  artwork: StatusResponse["artwork"];
  latestRun: ArtworkRunRecord | null;
}) {
  const generator = artwork.generator;

  const latestLibraryCount =
    latestRun?.summary.library_count ??
    artwork.libraries.length;

  const provider =
    artwork.primary_provider
      ? artwork.primary_provider.charAt(0).toUpperCase() +
        artwork.primary_provider.slice(1)
      : "Not configured";

  const applyMode =
    artwork.apply_mode === "auto"
      ? "Automatic"
      : "Manual Review";

  return (
    <Card className="bg-zinc-900 border border-zinc-800 mb-8">
      <CardBody className="p-5">
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-white">
                Artwork
              </h2>

              <Chip
                size="sm"
                variant="flat"
                color={
                  artwork.enabled
                    ? "success"
                    : "default"
                }
              >
                {artwork.enabled
                  ? "Manager Enabled"
                  : "Manager Disabled"}
              </Chip>

              <Chip
                size="sm"
                variant="flat"
                color={
                  generator.enabled
                    ? "secondary"
                    : "default"
                }
              >
                {generator.enabled
                  ? "Generator Enabled"
                  : "Generator Disabled"}
              </Chip>
            </div>

            <p className="text-sm text-zinc-400 mt-1">
              Artwork source priority and generated
              episode-card fallback status.
            </p>
          </div>

          <div className="text-xs text-zinc-500">
            {latestLibraryCount > 0
              ? `${latestLibraryCount} ${
                  latestLibraryCount === 1
                    ? "library"
                    : "libraries"
                } in latest run`
              : "Library discovery available on Artwork page"}
          </div>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-5">
          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">
              Primary Source
            </p>
            <p className="text-zinc-100 font-semibold mt-1">
              {artwork.enabled
                ? provider
                : "Disabled"}
            </p>
          </div>

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">
              Apply Mode
            </p>
            <p className="text-zinc-100 font-semibold mt-1">
              {artwork.enabled
                ? applyMode
                : "—"}
            </p>
          </div>

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">
              Episode Fallback
            </p>
            <p className="text-zinc-100 font-semibold mt-1">
              {generator.enabled
                ? "Dakosys Generated"
                : artwork.tmdb_enabled
                  ? "TMDB / Existing"
                  : "Existing Artwork"}
            </p>
          </div>

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">
              Default Font
            </p>
            <p className="text-zinc-100 font-semibold mt-1 capitalize">
              {generator.enabled &&
              generator.default_font
                ? generator.default_font.replaceAll(
                    "_",
                    " "
                  )
                : "—"}
            </p>
          </div>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-3">
          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">
              Last Run
            </p>
            <p className="text-zinc-100 font-semibold mt-1">
              {latestRun
                ? artworkRunAge(
                    latestRun.generated_at
                  )
                : "No run recorded"}
            </p>
          </div>

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">
              Result
            </p>
            <p className="text-zinc-100 font-semibold mt-1">
              {artworkRunResult(
                latestRun
              )}
            </p>
          </div>

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">
              Episode Coverage
            </p>
            <p className="text-zinc-100 font-semibold mt-1">
              {artworkRunCoverage(
                latestRun
              )}
            </p>
          </div>

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">
              Latest Run Libraries
            </p>
            <p className="text-zinc-100 font-semibold mt-1">
              {latestRun
                ? latestRun.summary.library_count
                : "—"}
            </p>
          </div>
        </div>

        {artwork.enabled && (
          <div className="mt-5 bg-zinc-950 border border-zinc-800 rounded-lg p-4">
            <p className="text-zinc-500 text-xs uppercase tracking-wider mb-3">
              Episode Artwork Priority
            </p>

            <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 text-sm">
              <span className="text-violet-300 font-medium">
                {provider} Curated
              </span>

              <span className="text-zinc-600 hidden sm:inline">
                →
              </span>

              {generator.enabled && (
                <>
                  <span className="text-zinc-200 font-medium">
                    Dakosys Generated
                  </span>

                  <span className="text-zinc-600 hidden sm:inline">
                    →
                  </span>
                </>
              )}

              <span className="text-zinc-400">
                {artwork.tmdb_enabled
                  ? "TMDB / Existing Fallback"
                  : "Existing Fallback"}
              </span>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}


function TraktDependencyCard({
  trakt,
}: {
  trakt: StatusResponse["trakt"];
}) {
  const enabledFeatures = [
    trakt.features.auto_schedule
      ? "Automatic Schedule"
      : null,
    trakt.features.legacy_episode_publishing
      ? "Legacy Publishing"
      : null,
  ].filter(Boolean) as string[];

  return (
    <Card className="bg-zinc-900 border border-zinc-800 mb-8">
      <CardBody className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-white">
              Trakt Dependency
            </h2>

            <p className="text-sm text-zinc-400 mt-1">
              {trakt.required
                ? "One or more enabled features use Trakt."
                : "No enabled feature currently requires Trakt."}
            </p>
          </div>

          <div className="flex gap-2 flex-wrap">
            <Chip
              size="sm"
              variant="flat"
              color={
                trakt.required
                  ? "secondary"
                  : "success"
              }
            >
              {trakt.required
                ? "Required"
                : "Not required"}
            </Chip>

            {trakt.required && (
              <Chip
                size="sm"
                variant="flat"
                color={
                  trakt.configured
                    ? "success"
                    : "warning"
                }
              >
                {trakt.configured
                  ? "Credentials configured"
                  : "Setup required"}
              </Chip>
            )}
          </div>
        </div>

        {trakt.required &&
          enabledFeatures.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-4">
              {enabledFeatures.map((feature) => (
                <Chip
                  key={feature}
                  size="sm"
                  variant="flat"
                  color="default"
                >
                  {feature}
                </Chip>
              ))}
            </div>
          )}

        <p className="text-xs text-zinc-600 mt-3">
          Live authentication and account capacity
          are shown on the Trakt page. Dashboard
          loading never contacts Trakt.
        </p>
      </CardBody>
    </Card>
  );
}

export default function DashboardPage() {
  const router = useRouter();

  const [data, setData] =
    useState<StatusResponse | null>(null);
  const [animeSchedule, setAnimeSchedule] =
    useState<AnimeScheduleResponse | null>(
      null,
    );

  const [
    latestArtworkRun,
    setLatestArtworkRun,
  ] = useState<ArtworkRunRecord | null>(
    null
  );
  const [error, setError] =
    useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [
        statusResult,
        scheduleResult,
        artworkLatestResult,
      ] = await Promise.all([
        api.getStatus(),
        api.getAnimeSchedule(),
        api
          .getArtworkLatestRun()
          .catch(() => ({
            run: null,
          })),
      ]);

      if (statusResult.config_missing) {
        router.replace("/setup");
        return;
      }

      setData(statusResult);
      setAnimeSchedule(scheduleResult);
      setLatestArtworkRun(
        artworkLatestResult.run
      );
      setError(null);
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "Failed to load status",
      );
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchData();

    const interval = setInterval(
      fetchData,
      30000,
    );

    return () => clearInterval(interval);
  }, [fetchData]);

  const activeFutureCount =
    animeSchedule?.count ?? 0;

  const autoScheduleEnabled =
    animeSchedule?.auto_enabled ?? false;

  return (
    <div className="relative min-h-full">
      <BackgroundBeams className="opacity-40" />

      <div className="relative z-10">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white">
            Dashboard
          </h1>

          <p className="text-zinc-400 mt-1">
            DAKOSYS service health and statistics
          </p>
        </div>

        {loading && (
          <div className="flex items-center justify-center h-40">
            <Spinner
              color="secondary"
              size="lg"
            />
          </div>
        )}

        {error && (
          <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 mb-6">
            <p className="text-red-400 text-sm">
              {error}
            </p>
          </div>
        )}

        {data && (
          <>
            {/* Stats */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
              <StatsCard
                label="TV Shows Tracked"
                value={data.stats.total_shows}
                icon="📺"
              />

              <StatsCard
                label="Total Size"
                value={
                  data.stats.total_size_gb
                }
                unit="GB"
                decimals={1}
                icon="💾"
                subtitle={`across ${
                  data.stats.total_libraries
                } ${
                  data.stats
                    .total_libraries === 1
                    ? "library"
                    : "libraries"
                }`}
              />

              <Card className="bg-zinc-900 border border-zinc-800">
                <CardBody className="p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="text-zinc-400 text-xs font-medium uppercase tracking-wider mb-3">
                        Anime
                      </p>

                      <div className="flex items-center gap-6">
                        <div>
                          <NumberTicker
                            value={
                              activeFutureCount
                            }
                            className="text-3xl font-bold text-white"
                          />

                          <p className="text-zinc-500 text-xs mt-1">
                            active / future
                          </p>
                        </div>

                        <div className="w-px h-8 bg-zinc-700" />

                        <div>
                          <p className="text-xl font-semibold text-white">
                            Local
                          </p>

                          <p className="text-zinc-500 text-xs mt-1">
                            Plex + AFL
                          </p>
                        </div>
                      </div>

                      {!autoScheduleEnabled && (
                        <p className="text-zinc-600 text-xs mt-3">
                          Automatic active/future
                          scheduling is disabled.
                        </p>
                      )}
                    </div>

                    <div className="text-4xl opacity-50">
                      🎌
                    </div>
                  </div>
                </CardBody>
              </Card>
            </div>

            <TraktDependencyCard
              trakt={data.trakt}
            />

            <ArtworkStatusCard
              artwork={data.artwork}
              latestRun={latestArtworkRun}
            />

            {/* Services */}
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-white mb-4">
                Services
              </h2>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {(
                  [
                    "anime_episode_type",
                    "tv_status_tracker",
                    "size_overlay",
                  ] as const
                ).map((key) => (
                  <ServiceHealthCard
                    key={key}
                    name={
                      SERVICE_LABELS[key]
                    }
                    serviceKey={key}
                    status={
                      data.services[key]
                    }
                    onRefresh={fetchData}
                  />
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
