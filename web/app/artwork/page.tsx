"use client";

import {
  Button,
  Card,
  CardBody,
  Chip,
  Progress,
  Spinner,
} from "@nextui-org/react";
import { useEffect, useState } from "react";

import { Spotlight } from "@/components/ui/spotlight";
import { api } from "@/lib/api";
import type {
  ArtworkLibraryPreview,
  ArtworkTarget,
  ArtworkTargetsResponse,
} from "@/types/api";


function percent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}


function baselineLabel(source: string): string {
  switch (source) {
    case "durable_state":
      return "Durable State";
    case "legacy_migration":
      return "Legacy Migration";
    case "new_library":
      return "New Library";
    default:
      return source;
  }
}


function Stat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
      <p className="text-zinc-500 text-xs uppercase tracking-wider">
        {label}
      </p>
      <p className="text-zinc-100 text-lg font-semibold mt-1">
        {value}
      </p>
    </div>
  );
}


function PreviewPanel({
  preview,
}: {
  preview: ArtworkLibraryPreview;
}) {
  const coverage = preview.coverage;
  const output = preview.output;

  return (
    <div className="border-t border-zinc-800 p-5 space-y-5">
      <div className="flex flex-wrap gap-2">
        <Chip
          size="sm"
          variant="flat"
          color={
            preview.safety.safe_to_apply
              ? "success"
              : "danger"
          }
        >
          {preview.safety.safe_to_apply
            ? "Safe to Apply"
            : "Review Required"}
        </Chip>

        <Chip size="sm" variant="flat">
          {baselineLabel(
            preview.baseline.source
          )}
        </Chip>

        <Chip
          size="sm"
          variant="flat"
          color={
            output.changed_files > 0
              ? "warning"
              : "success"
          }
        >
          {output.changed_files > 0
            ? `${output.changed_files} file changes`
            : "No filesystem changes"}
        </Chip>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat
          label="Plex Shows"
          value={preview.inventory.plex_shows}
        />
        <Stat
          label="Managed"
          value={preview.inventory.managed_after}
        />
        <Stat
          label="Episodes"
          value={coverage.expected_episodes}
        />
        <Stat
          label="Gaps"
          value={coverage.gaps_after}
        />
      </div>

      <Card className="bg-zinc-950 border border-zinc-800">
        <CardBody className="p-4">
          <div className="flex items-center justify-between mb-2">
            <div>
              <p className="font-semibold text-white">
                Episode Artwork Coverage
              </p>
              <p className="text-zinc-500 text-xs">
                {coverage.cards_after.toLocaleString()} of{" "}
                {coverage.expected_episodes.toLocaleString()} episodes
              </p>
            </div>

            <span className="text-violet-300 font-semibold">
              {percent(
                coverage.coverage_after
              )}
            </span>
          </div>

          <Progress
            aria-label="Episode artwork coverage"
            value={
              coverage.coverage_after * 100
            }
            color="secondary"
            className="mb-3"
          />

          {coverage.coverage_change !== 0 && (
            <p className="text-xs text-zinc-400">
              Preview change:{" "}
              <span
                className={
                  coverage.coverage_change > 0
                    ? "text-green-400"
                    : "text-red-400"
                }
              >
                {coverage.coverage_change > 0
                  ? "+"
                  : ""}
                {percent(
                  coverage.coverage_change
                )}
              </span>
            </p>
          )}

          {coverage.sources.length > 0 && (
            <div className="mt-4 grid sm:grid-cols-2 gap-2">
              {coverage.sources.map(
                (source) => (
                  <div
                    key={source.source}
                    className="flex items-center justify-between bg-zinc-900 rounded-md px-3 py-2"
                  >
                    <span className="text-zinc-300 capitalize text-sm">
                      {source.source}
                    </span>

                    <span className="text-zinc-400 text-xs">
                      {source.before.toLocaleString()}
                      {" → "}
                      {source.after.toLocaleString()}
                    </span>
                  </div>
                )
              )}
            </div>
          )}
        </CardBody>
      </Card>

      <div className="grid md:grid-cols-3 gap-3">
        <Card className="bg-zinc-950 border border-zinc-800">
          <CardBody>
            <p className="text-zinc-400 text-xs uppercase tracking-wider mb-3">
              Provider Activity
            </p>

            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-zinc-400">
                  MediUX requests
                </span>
                <span className="text-zinc-200">
                  {
                    preview.provider_activity
                      .primary_requests
                  }
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-zinc-400">
                  TMDB requests
                </span>
                <span className="text-zinc-200">
                  {
                    preview.provider_activity
                      .tmdb.requests
                  }
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-zinc-400">
                  Identity enriched
                </span>
                <span className="text-zinc-200">
                  {
                    preview.provider_activity
                      .identity_enrichment
                      .enriched
                  }
                </span>
              </div>
            </div>
          </CardBody>
        </Card>

        <Card className="bg-zinc-950 border border-zinc-800">
          <CardBody>
            <p className="text-zinc-400 text-xs uppercase tracking-wider mb-3">
              Selection Activity
            </p>

            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-zinc-400">
                  Set refreshes
                </span>
                <span className="text-zinc-200">
                  {
                    preview.selection_activity
                      .set_refreshes
                  }
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-zinc-400">
                  Set migrations
                </span>
                <span className="text-zinc-200">
                  {
                    preview.selection_activity
                      .set_migrations
                  }
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-zinc-400">
                  Without state
                </span>
                <span className="text-zinc-200">
                  {
                    preview.inventory
                      .shows_without_state
                  }
                </span>
              </div>
            </div>
          </CardBody>
        </Card>

        <Card className="bg-zinc-950 border border-zinc-800">
          <CardBody>
            <p className="text-zinc-400 text-xs uppercase tracking-wider mb-3">
              Filesystem Plan
            </p>

            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-zinc-400">
                  Add
                </span>
                <span className="text-green-400">
                  {output.added}
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-zinc-400">
                  Update
                </span>
                <span className="text-yellow-400">
                  {output.updated}
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-zinc-400">
                  Remove
                </span>
                <span className="text-red-400">
                  {output.removed}
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-zinc-400">
                  Unchanged
                </span>
                <span className="text-zinc-200">
                  {output.unchanged}
                </span>
              </div>
            </div>
          </CardBody>
        </Card>
      </div>

      {preview.safety.issues.length > 0 && (
        <div className="bg-red-950/40 border border-red-900 rounded-lg p-4">
          <p className="text-red-300 font-semibold text-sm mb-2">
            Safety Issues
          </p>

          <div className="space-y-2">
            {preview.safety.issues.map(
              (issue, index) => (
                <div
                  key={`${issue.code}-${index}`}
                  className="text-sm"
                >
                  <span className="text-red-400 font-mono text-xs">
                    {issue.code}
                  </span>
                  <p className="text-zinc-300">
                    {issue.message}
                  </p>
                </div>
              )
            )}
          </div>
        </div>
      )}

      {preview.inventory.no_state_titles.length > 0 && (
        <div>
          <p className="text-zinc-400 text-xs uppercase tracking-wider mb-2">
            Shows Without Managed Artwork
          </p>

          <div className="flex flex-wrap gap-2">
            {preview.inventory.no_state_titles.map(
              (title) => (
                <Chip
                  key={title}
                  size="sm"
                  variant="flat"
                >
                  {title}
                </Chip>
              )
            )}
          </div>
        </div>
      )}

      {(output.added > 0 ||
        output.updated > 0 ||
        output.removed > 0) && (
        <div className="text-xs text-zinc-500">
          This page is preview-only. No Artwork Manager
          files have been written.
        </div>
      )}
    </div>
  );
}


function TargetCard({
  target,
  preview,
  previewing,
  onPreview,
}: {
  target: ArtworkTarget;
  preview: ArtworkLibraryPreview | null;
  previewing: boolean;
  onPreview: () => void;
}) {
  return (
    <Card className="bg-zinc-900 border border-zinc-800">
      <CardBody className="p-0">
        <div className="p-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-white font-semibold text-lg">
                  {target.library}
                </h2>

                <Chip
                  size="sm"
                  variant="flat"
                  color={
                    target.supported
                      ? "success"
                      : "default"
                  }
                >
                  {target.media_type === "show"
                    ? "Shows"
                    : "Movies"}
                </Chip>
              </div>

              <p className="text-zinc-500 text-xs mt-2 font-mono break-all">
                {target.output_path}
              </p>
            </div>

            {target.supported ? (
              <Button
                color="secondary"
                variant={
                  preview
                    ? "flat"
                    : "solid"
                }
                isLoading={previewing}
                onPress={onPreview}
              >
                {preview
                  ? "Refresh Preview"
                  : "Preview Changes"}
              </Button>
            ) : (
              <Chip
                variant="flat"
                color="warning"
              >
                Movie support pending
              </Chip>
            )}
          </div>
        </div>

        {preview && (
          <PreviewPanel
            preview={preview}
          />
        )}
      </CardBody>
    </Card>
  );
}


export default function ArtworkPage() {
  const [
    targetsResponse,
    setTargetsResponse,
  ] = useState<ArtworkTargetsResponse | null>(
    null
  );

  const [
    previews,
    setPreviews,
  ] = useState<
    Record<string, ArtworkLibraryPreview>
  >({});

  const [
    previewing,
    setPreviewing,
  ] = useState<string | null>(null);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    error,
    setError,
  ] = useState<string | null>(null);

  const loadTargets = async () => {
    setLoading(true);

    try {
      const result =
        await api.getArtworkTargets();

      setTargetsResponse(result);
      setError(null);
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "Failed to load Artwork Manager"
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTargets();
  }, []);

  const previewLibrary = async (
    library: string
  ) => {
    setPreviewing(library);

    try {
      const result =
        await api.getArtworkPreview(
          library
        );

      const preview =
        result.libraries.find(
          (item) =>
            item.library === library
        );

      if (!preview) {
        throw new Error(
          `No preview returned for ${library}`
        );
      }

      setPreviews(
        (current) => ({
          ...current,
          [library]: preview,
        })
      );

      setError(null);
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : `Failed to preview ${library}`
      );
    } finally {
      setPreviewing(null);
    }
  };

  const targets =
    targetsResponse?.targets ?? [];

  const showCount =
    targets.filter(
      (target) =>
        target.media_type === "show"
    ).length;

  const pendingCount =
    targets.filter(
      (target) =>
        !target.supported
    ).length;

  return (
    <div>
      <Spotlight className="rounded-2xl mb-6 p-6 bg-zinc-900/50 border border-zinc-800">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white">
              Artwork Manager
            </h1>

            <p className="text-zinc-400 mt-1">
              Discover, preview, and review
              artwork management across Plex
              libraries.
            </p>
          </div>

          {targetsResponse && (
            <div className="flex gap-2">
              <Chip
                variant="flat"
                color="secondary"
              >
                {showCount} show{" "}
                {showCount === 1
                  ? "library"
                  : "libraries"}
              </Chip>

              {pendingCount > 0 && (
                <Chip
                  variant="flat"
                  color="warning"
                >
                  {pendingCount} pending
                </Chip>
              )}
            </div>
          )}
        </div>
      </Spotlight>

      {loading && (
        <div className="flex justify-center items-center h-40">
          <Spinner color="secondary" />
        </div>
      )}

      {error && (
        <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 mb-5">
          <p className="text-red-400 text-sm">
            {error}
          </p>
        </div>
      )}

      {!loading &&
        targetsResponse &&
        !targetsResponse.enabled && (
          <Card className="bg-zinc-900 border border-zinc-800">
            <CardBody className="p-6">
              <p className="text-white font-semibold">
                Artwork Manager is disabled
              </p>
              <p className="text-zinc-400 text-sm mt-1">
                Enable
                {" "}
                <span className="font-mono text-violet-300">
                  services.artwork_manager.enabled
                </span>
                {" "}
                in Dakosys configuration.
              </p>
            </CardBody>
          </Card>
        )}

      {!loading &&
        targetsResponse?.enabled &&
        targets.length === 0 && (
          <div className="text-center text-zinc-500 py-16">
            No supported Plex libraries were discovered.
          </div>
        )}

      <div className="space-y-4">
        {targets.map(
          (target) => (
            <TargetCard
              key={target.library}
              target={target}
              preview={
                previews[
                  target.library
                ] ?? null
              }
              previewing={
                previewing ===
                target.library
              }
              onPreview={() =>
                previewLibrary(
                  target.library
                )
              }
            />
          )
        )}
      </div>
    </div>
  );
}
