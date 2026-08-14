"use client";

import { useEffect, useState } from "react";
import { Card, CardBody, Chip, Spinner } from "@nextui-org/react";
import { api } from "@/lib/api";
import type { NextAiringShow } from "@/types/api";

const STATUS_CONFIG: Record<string, { color: "success" | "default" | "danger" | "primary" | "secondary" | "warning"; label: string }> = {
  AIRING: { color: "success", label: "Airing" },
  ENDED: { color: "default", label: "Ended" },
  CANCELLED: { color: "danger", label: "Cancelled" },
  RETURNING: { color: "primary", label: "Returning" },
  SEASON_FINALE: { color: "secondary", label: "Season Finale" },
  MID_SEASON_FINALE: { color: "warning", label: "Mid-Season Finale" },
  FINAL_EPISODE: { color: "danger", label: "Final Episode" },
  SEASON_PREMIERE: { color: "success", label: "Season Premiere" },
  UNKNOWN: { color: "default", label: "Unknown" },
};

function PosterCard({ show }: { show: NextAiringShow }) {
  const [imgError, setImgError] = useState(false);
  const cfg = STATUS_CONFIG[show.status?.toUpperCase()] ?? { color: "default" as const, label: show.status || "Unknown" };

  const STOP_WORDS = new Set(["the", "a", "an", "of", "in", "at", "on", "to", "for", "and", "or", "but"]);
  const words = show.title.split(/\s+/).filter((w) => w.length > 1 && !STOP_WORDS.has(w.toLowerCase()));
  const initials = (words.length > 0 ? words : show.title.split(/\s+/))
    .slice(0, 3)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <a
      href={show.external_url ?? undefined}
      target="_blank"
      rel="noopener noreferrer"
      className="group block rounded-xl overflow-hidden bg-zinc-900 border border-zinc-800 hover:border-violet-600/50 transition-all hover:shadow-lg hover:shadow-violet-900/20"
    >
      {/* Poster */}
      <div className="relative w-full aspect-[2/3] bg-zinc-800 overflow-hidden">
        {show.poster_url && !imgError ? (
          <img
            src={show.poster_url}
            alt={show.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <span className="text-3xl font-bold text-zinc-600">{initials}</span>
          </div>
        )}
        {/* Rank badge */}
        <div className="absolute top-2 left-2 bg-black/70 text-zinc-300 text-xs font-mono px-1.5 py-0.5 rounded">
          #{show.rank}
        </div>
      </div>

      {/* Info */}
      <div className="p-2.5">
        <p className="text-white text-xs font-medium leading-tight mb-1.5 line-clamp-2 min-h-[2.5em]" title={show.title}>
          {show.title}
        </p>
        <Chip size="sm" color={cfg.color} variant="flat" className="text-xs mb-1">
          {cfg.label}
        </Chip>
        {show.date && (
          <p className="text-zinc-500 text-xs mt-1">{show.date}</p>
        )}
      </div>
    </a>
  );
}

export default function NextAiringPage() {
  const [shows, setShows] = useState<NextAiringShow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getNextAiring()
      .then((r) => {
        setShows(r.shows);
        if (r.error) setError(r.error);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white">Next Airing</h1>
        <p className="text-zinc-400 mt-1">
          Provider-resolved upcoming episodes in air-date order
        </p>
      </div>

      {loading && (
        <div className="flex justify-center h-40 items-center">
          <Spinner color="secondary" />
        </div>
      )}

      {error && (
        <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {!loading && shows.length === 0 && !error && (
        <p className="text-zinc-500 text-sm">
          No provider-derived upcoming episodes are available yet.
        </p>
      )}

      {shows.length > 0 && (
        <>
          <p className="text-zinc-500 text-xs mb-4">{shows.length} shows</p>
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-7 gap-3">
            {shows.map((show) => (
              <PosterCard
                key={show.plex_rating_key || show.title}
                show={show}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
