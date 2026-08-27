"use client";

import {
  Button,
  Card,
  CardBody,
  Chip,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  Progress,
  Spinner,
  Switch,
} from "@nextui-org/react";
import { useEffect, useState } from "react";

import { Spotlight } from "@/components/ui/spotlight";
import { api } from "@/lib/api";
import type {
  ArtworkLibraryPreview,
  ArtworkLibraryRun,
  ArtworkRunOutcome,
  ArtworkRunRecord,
  ArtworkScanRecord,
  ArtworkReviewedApplyRecord,
  ArtworkTarget,
  ArtworkTargetsResponse,
  StatusResponse,
} from "@/types/api";


function percent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}


function baselineLabel(source: string): string {
  switch (source) {
    case "durable_state":
      return "Durable State";
    case "item_store_bootstrap":
      return "3.0 Item Store Bootstrap";
    case "legacy_migration":
      return "Legacy Migration";
    case "new_library":
      return "New Library";
    default:
      return source;
  }
}


function episodeSourceLabel(
  source: string
): string {
  switch (source) {
    case "mediux":
      return "MediUX Curated";
    case "generated":
      return "Dakosys Generated";
    case "tmdb":
      return "TMDB Raw Still";
    case "tvdb":
      return "TVDB";
    case "plex":
      return "Plex / Existing";
    case "manual":
      return "Manual / Locked";
    default:
      return source;
  }
}


function scanPhaseLabel(
  phase: string,
  fallback: string
): string {
  switch (phase) {
    case "starting":
      return "Starting current-state scan";
    case "inventory":
      return "Reading Plex library inventory";
    case "identity":
      return "Resolving show identities";
    case "primary_managed":
      return "Checking managed artwork with MediUX";
    case "primary_discovery":
      return "Discovering artwork with MediUX";
    case "tmdb_managed":
      return "Checking managed episode gaps with TMDB";
    case "tmdb_discovery":
      return "Checking unmanaged episode gaps with TMDB";
    case "planning":
      return "Planning current-state changes";
    case "complete":
      return "Current-state scan complete";
    default:
      return fallback || phase;
  }
}


function applyPhaseLabel(
  phase: string,
  fallback: string
): string {
  switch (phase) {
    case "starting":
      return "Starting reviewed apply";
    case "refreshing":
      return "Refreshing current state after apply";
    case "complete":
      return fallback || "Reviewed apply complete";
    default:
      return scanPhaseLabel(
        phase,
        fallback
      );
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


function runTime(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}


function outcomeLabel(
  outcome: ArtworkRunOutcome
): string {
  switch (outcome) {
    case "applied":
      return "Applied";
    case "no_changes":
      return "No Changes";
    case "pending_review":
      return "Pending Review";
    case "blocked":
      return "Blocked";
    case "failed":
      return "Failed";
    default:
      return outcome;
  }
}


function outcomeColor(
  outcome: ArtworkRunOutcome
):
  | "success"
  | "secondary"
  | "warning"
  | "danger"
  | "default" {
  switch (outcome) {
    case "applied":
      return "success";
    case "no_changes":
      return "default";
    case "pending_review":
      return "warning";
    case "blocked":
    case "failed":
      return "danger";
    default:
      return "default";
  }
}


function LibraryRunRow({
  run,
}: {
  run: ArtworkLibraryRun;
}) {
  const decision = run.decision;

  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-zinc-100 font-medium">
              {run.library}
            </p>

            <Chip
              size="sm"
              variant="flat"
              color={outcomeColor(
                decision.outcome
              )}
            >
              {outcomeLabel(
                decision.outcome
              )}
            </Chip>
          </div>

          <p className="text-zinc-500 text-xs mt-1 font-mono break-all">
            {run.output_path}
          </p>
        </div>

        <div className="text-sm text-zinc-400 sm:text-right">
          {run.selection_activity.set_refreshes > 0 && (
            <p>
              {run.selection_activity.set_refreshes} set{" "}
              {run.selection_activity.set_refreshes === 1
                ? "refresh"
                : "refreshes"}
            </p>
          )}

          {run.selection_activity.set_migrations > 0 && (
            <p>
              {run.selection_activity.set_migrations} set{" "}
              {run.selection_activity.set_migrations === 1
                ? "migration"
                : "migrations"}
            </p>
          )}

          {decision.needs_apply && (
            <p>
              {run.output.changed_files} file{" "}
              {run.output.changed_files === 1
                ? "change"
                : "changes"}
            </p>
          )}
        </div>
      </div>

      {run.error && (
        <div className="mt-3 bg-red-950/40 border border-red-900 rounded-md px-3 py-2">
          <p className="text-red-300 text-sm">
            {run.error.type
              ? `${run.error.type}: `
              : ""}
            {run.error.message}
          </p>
        </div>
      )}

      {decision.outcome === "pending_review" &&
        decision.review_fingerprint && (
          <div className="mt-3">
            <p className="text-zinc-500 text-xs uppercase tracking-wider">
              Review identity
            </p>

            <p className="text-zinc-400 text-xs font-mono mt-1 break-all">
              {decision.review_fingerprint}
            </p>
          </div>
        )}
    </div>
  );
}


function ArtworkRunDashboard({
  latest,
  recent,
  loading,
  onRefresh,
}: {
  latest: ArtworkRunRecord | null;
  recent: ArtworkRunRecord[];
  loading: boolean;
  onRefresh: () => void;
}) {
  if (!latest) {
    return (
      <Card className="bg-zinc-900 border border-zinc-800 mb-6">
        <CardBody className="p-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <p className="text-white font-semibold text-lg">
                Automation Status
              </p>

              <p className="text-zinc-400 text-sm mt-1">
                No Artwork Manager run has been recorded yet.
              </p>
            </div>

            <Button
              variant="flat"
              color="secondary"
              isLoading={loading}
              onPress={onRefresh}
            >
              Refresh Artwork Status
            </Button>
          </div>
        </CardBody>
      </Card>
    );
  }

  const summary = latest.summary;

  return (
    <div className="space-y-4 mb-6">
      <Card className="bg-zinc-900 border border-zinc-800">
        <CardBody className="p-5 space-y-5">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-white font-semibold text-lg">
                  Automation Status
                </p>

                <Chip
                  size="sm"
                  variant="flat"
                  color={
                    latest.apply_mode === "auto"
                      ? "success"
                      : "warning"
                  }
                >
                  {latest.apply_mode === "auto"
                    ? "Automatic Apply"
                    : "Manual Review"}
                </Chip>
              </div>

              <p className="text-zinc-400 text-sm mt-1">
                Last run {runTime(latest.generated_at)}
              </p>

              <p className="text-zinc-600 text-xs font-mono mt-1">
                {latest.run_id}
              </p>
            </div>

            <Button
              variant="flat"
              color="secondary"
              isLoading={loading}
              onPress={onRefresh}
            >
              Refresh Artwork Status
            </Button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Stat
              label="Applied"
              value={summary.applied}
            />

            <Stat
              label="No Changes"
              value={summary.no_changes}
            />

            <Stat
              label="Pending"
              value={summary.pending_review}
            />

            <Stat
              label="Blocked"
              value={summary.blocked}
            />

            <Stat
              label="Failed"
              value={summary.failed}
            />
          </div>

          {latest.libraries.length > 0 && (
            <div>
              <p className="text-zinc-400 text-xs uppercase tracking-wider mb-3">
                Library Results
              </p>

              <div className="space-y-2">
                {latest.libraries.map(
                  (run) => (
                    <LibraryRunRow
                      key={run.library}
                      run={run}
                    />
                  )
                )}
              </div>
            </div>
          )}

          {latest.skipped.length > 0 && (
            <div>
              <p className="text-zinc-400 text-xs uppercase tracking-wider mb-2">
                Skipped
              </p>

              <div className="flex flex-wrap gap-2">
                {latest.skipped.map(
                  (item) => (
                    <Chip
                      key={`${item.library}-${item.reason}`}
                      size="sm"
                      variant="flat"
                      color="warning"
                    >
                      {item.library}: {item.reason}
                    </Chip>
                  )
                )}
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      {recent.length > 1 && (
        <Card className="bg-zinc-900 border border-zinc-800">
          <CardBody className="p-5">
            <p className="text-zinc-400 text-xs uppercase tracking-wider mb-3">
              Recent Runs
            </p>

            <div className="divide-y divide-zinc-800">
              {recent.slice(0, 5).map(
                (run) => (
                  <div
                    key={run.run_id}
                    className="py-3 first:pt-0 last:pb-0 flex flex-col md:flex-row md:items-center justify-between gap-2"
                  >
                    <div>
                      <p className="text-zinc-200 text-sm">
                        {runTime(
                          run.generated_at
                        )}
                      </p>

                      <p className="text-zinc-600 text-xs font-mono">
                        {run.run_id}
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {run.summary.applied > 0 && (
                        <Chip
                          size="sm"
                          variant="flat"
                          color="success"
                        >
                          {run.summary.applied} applied
                        </Chip>
                      )}

                      {run.summary.pending_review > 0 && (
                        <Chip
                          size="sm"
                          variant="flat"
                          color="warning"
                        >
                          {run.summary.pending_review} pending
                        </Chip>
                      )}

                      {run.summary.blocked > 0 && (
                        <Chip
                          size="sm"
                          variant="flat"
                          color="danger"
                        >
                          {run.summary.blocked} blocked
                        </Chip>
                      )}

                      {run.summary.failed > 0 && (
                        <Chip
                          size="sm"
                          variant="flat"
                          color="danger"
                        >
                          {run.summary.failed} failed
                        </Chip>
                      )}

                      {run.summary.no_changes > 0 && (
                        <Chip
                          size="sm"
                          variant="flat"
                        >
                          {run.summary.no_changes} unchanged
                        </Chip>
                      )}
                    </div>
                  </div>
                )
              )}
            </div>
          </CardBody>
        </Card>
      )}
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
  const isMovie =
    preview.media_type === "movie";

  const generator =
    preview.generator ?? {
      changed_shows: 0,
      planned_cards: 0,
      cached_cards: 0,
      materialization_needed: 0,
      failures: 0,
    };

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
          label={
            isMovie
              ? "Plex Movies"
              : "Plex Shows"
          }
          value={preview.inventory.plex_shows}
        />
        <Stat
          label="Managed"
          value={preview.inventory.managed_after}
        />
        <Stat
          label={
            isMovie
              ? "Posters"
              : "Episodes"
          }
          value={
            isMovie
              ? preview.presentation.show_posters
              : coverage.expected_episodes
          }
        />
        <Stat
          label={
            isMovie
              ? "Backgrounds"
              : "Gaps"
          }
          value={
            isMovie
              ? preview.presentation.backgrounds
              : coverage.gaps_after
          }
        />
      </div>

      {!isMovie && (
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
              Current-state change:{" "}
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
                      {episodeSourceLabel(
                        source.source
                      )}
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
      )}

      {preview.media_type === "show" && (
        <Card className="bg-zinc-950 border border-zinc-800">
          <CardBody className="p-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
              <div>
                <p className="font-semibold text-white">
                  Artwork Generator Plan
                </p>

                <p className="text-zinc-500 text-xs mt-1">
                  Generated episode-card activity in this
                  read-only current-state plan.
                </p>
              </div>

              <Chip
                size="sm"
                variant="flat"
                color={
                  generator.failures > 0
                    ? "danger"
                    : generator
                          .materialization_needed > 0
                      ? "secondary"
                      : "default"
                }
              >
                {generator.failures > 0
                  ? `${generator.failures} failed`
                  : generator
                        .materialization_needed > 0
                    ? `${generator.materialization_needed.toLocaleString()} to materialize`
                    : "No materialization needed"}
              </Chip>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Stat
                label="Changed Shows"
                value={
                  generator.changed_shows
                }
              />

              <Stat
                label="Planned Cards"
                value={
                  generator.planned_cards
                    .toLocaleString()
                }
              />

              <Stat
                label="Cached"
                value={
                  generator.cached_cards
                    .toLocaleString()
                }
              />

              <Stat
                label="Need Materialization"
                value={
                  generator
                    .materialization_needed
                    .toLocaleString()
                }
              />

              <Stat
                label="Failures"
                value={
                  generator.failures
                }
              />
            </div>
          </CardBody>
        </Card>
      )}

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
                  MediUX unavailable
                </span>
                <span className={
                  preview.provider_activity
                    .primary_unavailable > 0
                    ? "text-yellow-400"
                    : "text-zinc-200"
                }>
                  {
                    preview.provider_activity
                      .primary_unavailable ?? 0
                  }
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-zinc-400">
                  MediUX errors
                </span>
                <span className={
                  preview.provider_activity
                    .primary_errors > 0
                    ? "text-red-400"
                    : "text-zinc-200"
                }>
                  {
                    preview.provider_activity
                      .primary_errors
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
            {isMovie
              ? "Movies Without Managed Artwork"
              : "Shows Without Managed Artwork"}
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
          Current state is read-only. No Artwork Manager
          files have been written.
        </div>
      )}
    </div>
  );
}


function TargetCard({
  target,
  preview,
  scan,
  apply,
  applyBusy,
  previewError,
  scannedAt,
  reviewFingerprint,
  onRefresh,
  onReviewApply,
}: {
  target: ArtworkTarget;
  preview: ArtworkLibraryPreview | null;
  scan: ArtworkScanRecord | null;
  apply: ArtworkReviewedApplyRecord | null;
  applyBusy: boolean;
  previewError: string | null;
  scannedAt: string | null;
  reviewFingerprint: string | null;
  onRefresh: (
    library: string
  ) => void;
  onReviewApply: (
    target: ArtworkTarget,
    preview: ArtworkLibraryPreview,
    reviewFingerprint: string,
  ) => void;
}) {
  const collapseStorageKey =
    `dakosys:artwork:collapsed:${target.library}`;

  const [
    collapsePreference,
    setCollapsePreference,
  ] = useState(false);

  useEffect(() => {
    try {
      setCollapsePreference(
        window.localStorage.getItem(
          collapseStorageKey
        ) === "true"
      );
    } catch {
      // localStorage is optional. Failure to persist
      // presentation state must not affect Artwork Manager.
    }
  }, [collapseStorageKey]);

  const scanning =
    scan?.status === "running";

  const applying =
    apply?.status === "running";

  const retryScan =
    previewError !== null ||
    (
      preview !== null &&
      !preview.safety.safe_to_apply
    );

  const canRefresh =
    target.supported &&
    !scanning &&
    !applying &&
    !applyBusy;

  const canReviewApply =
    target.supported &&
    preview !== null &&
    preview.safety.safe_to_apply &&
    preview.output.needs_apply &&
    reviewFingerprint !== null &&
    !scanning &&
    !applyBusy &&
    previewError === null;

  const requiresAttention =
    scanning ||
    applying ||
    previewError !== null ||
    (
      preview !== null &&
      !preview.safety.safe_to_apply
    ) ||
    apply?.status === "stale" ||
    apply?.status === "blocked" ||
    apply?.status === "failed";

  const collapsed =
    collapsePreference &&
    !requiresAttention;

  const toggleCollapsed = () => {
    if (requiresAttention) {
      return;
    }

    const next =
      !collapsePreference;

    setCollapsePreference(
      next
    );

    try {
      window.localStorage.setItem(
        collapseStorageKey,
        String(next)
      );
    } catch {
      // Presentation persistence is best-effort only.
    }
  };

  const progress =
    scanning
      ? scan.progress
      : null;

  const progressPercent =
    progress !== null &&
    progress.total > 0 &&
    progress.fraction !== null
      ? progress.fraction * 100
      : undefined;

  const determinate =
    progressPercent !== undefined;

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

              {preview && scannedAt && (
                <p className="text-zinc-500 text-xs mt-2">
                  Last scanned {runTime(scannedAt)}
                </p>
              )}
            </div>

            {target.supported ? (
              <div className="flex flex-wrap items-center gap-2">
                <Chip
                  variant="flat"
                  color={
                    applying
                      ? "secondary"
                      : scanning
                        ? "secondary"
                        : previewError
                        ? "danger"
                        : preview
                          ? "success"
                          : "default"
                  }
                >
                  {applying
                    ? "Applying"
                    : scanning
                      ? preview
                        ? "Refreshing"
                        : "Scanning"
                      : previewError
                      ? preview
                        ? "Refresh Failed"
                        : "Scan Failed"
                      : preview
                        ? "Current State"
                        : "Waiting"}
                </Chip>

                <Button
                  size="sm"
                  variant="flat"
                  color={
                    retryScan
                      ? "warning"
                      : "default"
                  }
                  isLoading={scanning}
                  isDisabled={!canRefresh}
                  onPress={() => {
                    onRefresh(
                      target.library
                    );
                  }}
                >
                  {scanning
                    ? "Refreshing"
                    : retryScan
                      ? "Retry Scan"
                      : "Refresh Current State"}
                </Button>

                {canReviewApply && (
                  <Button
                    size="sm"
                    color="secondary"
                    variant="flat"
                    onPress={() => {
                      if (
                        preview &&
                        reviewFingerprint
                      ) {
                        onReviewApply(
                          target,
                          preview,
                          reviewFingerprint,
                        );
                      }
                    }}
                  >
                    Apply Reviewed Plan
                  </Button>
                )}

                <Button
                  size="sm"
                  variant="light"
                  isDisabled={requiresAttention}
                  aria-expanded={!collapsed}
                  aria-label={
                    `${
                      collapsed
                        ? "Expand"
                        : "Collapse"
                    } ${target.library} artwork details`
                  }
                  onPress={toggleCollapsed}
                >
                  {collapsed
                    ? "Expand"
                    : "Collapse"}
                </Button>
              </div>
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

        {!collapsed && scanning && progress && (
          <div className="border-t border-zinc-800 p-5">
            <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-4">
              <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2 mb-3">
                <div>
                  <p className="text-zinc-100 font-medium">
                    {scanPhaseLabel(
                      progress.phase,
                      progress.message
                    )}
                  </p>

                  <p className="text-zinc-500 text-xs mt-1">
                    Current phase
                  </p>
                </div>

                {progress.total > 0 && (
                  <p className="text-violet-300 text-sm font-medium">
                    {progress.completed.toLocaleString()}
                    {" / "}
                    {progress.total.toLocaleString()}
                  </p>
                )}
              </div>

              <Progress
                aria-label={`${target.library} current scan phase progress`}
                color="secondary"
                isIndeterminate={!determinate}
                value={progressPercent}
              />

              {progress.current_title && (
                <p className="text-zinc-400 text-sm mt-3">
                  Processing{" "}
                  <span className="text-zinc-200">
                    {progress.current_title}
                  </span>
                </p>
              )}

              {preview && scannedAt && (
                <p className="text-zinc-500 text-xs mt-3">
                  Showing cached results from{" "}
                  {runTime(scannedAt)} while the
                  refresh runs.
                </p>
              )}
            </div>
          </div>
        )}

        {!collapsed && apply && (
          <div className="border-t border-zinc-800 p-5">
            <div
              className={
                apply.status === "applied"
                  ? "bg-green-950/30 border border-green-900 rounded-lg p-4"
                  : apply.status === "stale"
                    ? "bg-yellow-950/30 border border-yellow-900 rounded-lg p-4"
                    : apply.status === "blocked" ||
                        apply.status === "failed"
                      ? "bg-red-950/40 border border-red-900 rounded-lg p-4"
                      : "bg-zinc-950 border border-zinc-800 rounded-lg p-4"
              }
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <p className="text-zinc-100 font-medium">
                    {apply.status === "running"
                      ? applyPhaseLabel(
                          apply.progress.phase,
                          apply.progress.message
                        )
                      : apply.status === "applied"
                        ? "Reviewed plan applied"
                        : apply.status === "no_changes"
                          ? "Reviewed plan already current"
                          : apply.status === "stale"
                            ? "Reviewed plan changed"
                            : apply.status === "blocked"
                              ? "Reviewed apply blocked"
                              : "Reviewed apply failed"}
                  </p>

                  <p className="text-zinc-500 text-xs mt-1">
                    Manual reviewed apply
                  </p>
                </div>

                <Chip
                  size="sm"
                  variant="flat"
                  color={
                    apply.status === "applied"
                      ? "success"
                      : apply.status === "stale"
                        ? "warning"
                        : apply.status === "blocked" ||
                            apply.status === "failed"
                          ? "danger"
                          : apply.status === "running"
                            ? "secondary"
                            : "default"
                  }
                >
                  {apply.status === "running"
                    ? "Applying"
                    : apply.status === "no_changes"
                      ? "No Changes"
                      : apply.status === "stale"
                        ? "Refresh Required"
                        : apply.status.charAt(0).toUpperCase() +
                          apply.status.slice(1)}
                </Chip>
              </div>

              {apply.status === "running" && (
                <div className="mt-4">
                  <Progress
                    aria-label={`${target.library} reviewed apply progress`}
                    color="secondary"
                    isIndeterminate={
                      apply.progress.total <= 0 ||
                      apply.progress.fraction === null ||
                      apply.progress.phase === "complete" ||
                      apply.progress.phase === "refreshing"
                    }
                    value={
                      apply.progress.total > 0 &&
                      apply.progress.fraction !== null
                        ? apply.progress.fraction * 100
                        : undefined
                    }
                  />

                  {apply.progress.current_title && (
                    <p className="text-zinc-400 text-sm mt-3">
                      Processing{" "}
                      <span className="text-zinc-200">
                        {apply.progress.current_title}
                      </span>
                    </p>
                  )}
                </div>
              )}

              {apply.status === "stale" && (
                <p className="text-yellow-200 text-sm mt-3">
                  The library changed after this plan was reviewed.
                  Dakosys did not apply the stale plan. A fresh
                  current-state scan is required before trying again.
                </p>
              )}

              {apply.status === "applied" &&
                apply.result?.current_state_refreshed && (
                  <p className="text-green-200 text-sm mt-3">
                    Artwork was applied and the dashboard current
                    state was refreshed successfully.
                  </p>
                )}

              {apply.refresh_error && (
                <div className="mt-3 bg-yellow-950/40 border border-yellow-900 rounded-md px-3 py-2">
                  <p className="text-yellow-200 text-sm">
                    Apply succeeded, but the current-state refresh
                    failed: {apply.refresh_error.message}
                  </p>
                </div>
              )}

              {apply.error &&
                apply.status !== "stale" && (
                  <div className="mt-3 bg-red-950/40 border border-red-900 rounded-md px-3 py-2">
                    <p className="text-red-300 text-sm">
                      {apply.error.message}
                    </p>
                  </div>
                )}
            </div>
          </div>
        )}

        {!collapsed && previewError && (
          <div className="border-t border-zinc-800 p-5">
            <div className="bg-red-950/40 border border-red-900 rounded-lg p-4">
              <p className="text-red-300 font-semibold text-sm">
                {preview
                  ? "Current-state refresh failed"
                  : "Current state could not be loaded"}
              </p>

              <p className="text-zinc-300 text-sm mt-1">
                {previewError}
              </p>

              {preview && (
                <p className="text-zinc-500 text-xs mt-2">
                  The previous cached result has been retained.
                </p>
              )}
            </div>
          </div>
        )}

        {!collapsed && preview && (
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
    artworkStatus,
    setArtworkStatus,
  ] = useState<
    StatusResponse["artwork"] | null
  >(null);

  const [
    previews,
    setPreviews,
  ] = useState<
    Record<string, ArtworkLibraryPreview>
  >({});

  const [
    scannedAt,
    setScannedAt,
  ] = useState<
    Record<string, string>
  >({});

  const [
    reviewFingerprints,
    setReviewFingerprints,
  ] = useState<
    Record<string, string | null>
  >({});

  const [
    reviewDialog,
    setReviewDialog,
  ] = useState<{
    target: ArtworkTarget;
    preview: ArtworkLibraryPreview;
    reviewFingerprint: string;
  } | null>(null);

  const [
    scans,
    setScans,
  ] = useState<
    Record<string, ArtworkScanRecord>
  >({});

  const [
    applies,
    setApplies,
  ] = useState<
    Record<string, ArtworkReviewedApplyRecord>
  >({});

  const [
    startingApplyLibrary,
    setStartingApplyLibrary,
  ] = useState<string | null>(null);

  const [
    latestRun,
    setLatestRun,
  ] = useState<ArtworkRunRecord | null>(
    null
  );

  const [
    recentRuns,
    setRecentRuns,
  ] = useState<ArtworkRunRecord[]>([]);

  const [
    historyLoading,
    setHistoryLoading,
  ] = useState(false);

  const [
    previewErrors,
    setPreviewErrors,
  ] = useState<Record<string, string>>({});

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    artworkToggleBusy,
    setArtworkToggleBusy,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(null);

  const clearLibraryError = (
    library: string
  ) => {
    setPreviewErrors(
      (current) => {
        const next = {
          ...current,
        };

        delete next[
          library
        ];

        return next;
      }
    );
  };

  const setLibraryError = (
    library: string,
    message: string
  ) => {
    setPreviewErrors(
      (current) => ({
        ...current,
        [library]: message,
      })
    );
  };

  const loadCachedLibraryState = async (
    library: string
  ): Promise<boolean> => {
    try {
      const result =
        await api.getArtworkCurrentState(
          library
        );

      if (!result.state) {
        return false;
      }

      setPreviews(
        (current) => ({
          ...current,
          [library]:
            result.state!.preview,
        })
      );

      setScannedAt(
        (current) => ({
          ...current,
          [library]:
            result.state!.scanned_at,
        })
      );

      setReviewFingerprints(
        (current) => ({
          ...current,
          [library]:
            result.state!
              .review_fingerprint,
        })
      );

      clearLibraryError(
        library
      );

      return true;
    } catch (e: unknown) {
      setLibraryError(
        library,
        e instanceof Error
          ? e.message
          : `Failed to load cached state for ${library}`
      );

      return false;
    }
  };

  const markLocalScanFailed = (
    library: string,
    message: string
  ) => {
    setScans(
      (current) => {
        const existing =
          current[
            library
          ];

        if (!existing) {
          return current;
        }

        return {
          ...current,
          [library]: {
            ...existing,
            status: "failed",
            updated_at:
              new Date().toISOString(),
            error: {
              type: "ClientError",
              message,
            },
          },
        };
      }
    );
  };

  const pollArtworkScan = async (
    library: string,
    scanId: string
  ) => {
    while (true) {
      await new Promise(
        (resolve) =>
          setTimeout(
            resolve,
            1000
          )
      );

      let result;

      try {
        result =
          await api.getArtworkScan(
            scanId
          );
      } catch (e: unknown) {
        const message =
          e instanceof Error
            ? e.message
            : `Lost scan status for ${library}`;

        markLocalScanFailed(
          library,
          message
        );

        setLibraryError(
          library,
          message
        );

        return;
      }

      const scan =
        result.scan;

      setScans(
        (current) => ({
          ...current,
          [library]: scan,
        })
      );

      if (
        scan.status === "complete"
      ) {
        const loaded =
          await loadCachedLibraryState(
            library
          );

        if (!loaded) {
          setLibraryError(
            library,
            (
              `${library} scan completed, ` +
              "but its cached result could not be loaded"
            )
          );
        }

        return;
      }

      if (
        scan.status === "failed"
      ) {
        setLibraryError(
          library,
          scan.error?.message ??
            `Current-state scan failed for ${library}`
        );

        return;
      }
    }
  };

  const scanLibraryState = async (
    library: string
  ) => {
    clearLibraryError(
      library
    );

    try {
      const started =
        await api.startArtworkScan(
          library
        );

      const scan =
        started.scan;

      setScans(
        (current) => ({
          ...current,
          [library]: scan,
        })
      );

      if (
        scan.status === "complete"
      ) {
        await loadCachedLibraryState(
          library
        );

        return;
      }

      if (
        scan.status === "failed"
      ) {
        setLibraryError(
          library,
          scan.error?.message ??
            `Current-state scan failed for ${library}`
        );

        return;
      }

      await pollArtworkScan(
        library,
        scan.scan_id
      );
    } catch (e: unknown) {
      const message =
        e instanceof Error
          ? e.message
          : `Failed to start current-state scan for ${library}`;

      setLibraryError(
        library,
        message
      );
    }
  };

  const loadSupportedLibraryStates = async (
    targets: ArtworkTarget[]
  ) => {
    const supported =
      targets.filter(
        (target) =>
          target.supported
      );

    await Promise.allSettled(
      supported.map(
        async (target) => {
          const cached =
            await loadCachedLibraryState(
              target.library
            );

          if (!cached) {
            await scanLibraryState(
              target.library
            );
          }
        }
      )
    );
  };

  const refreshSupportedLibraryStates = async (
    targets: ArtworkTarget[]
  ) => {
    const supported =
      targets.filter(
        (target) =>
          target.supported
      );

    await Promise.allSettled(
      supported.map(
        (target) =>
          scanLibraryState(
            target.library
          )
      )
    );
  };

  const loadArtworkStatus = async () => {
    try {
      const result =
        await api.getStatus();

      setArtworkStatus(
        result.artwork
      );
    } catch {
      // Configuration status is supplemental.
      // Target/history loading should remain usable
      // if the dashboard status endpoint is unavailable.
    }
  };


  const loadTargets = async () => {
    setLoading(true);

    try {
      const result =
        await api.getArtworkTargets();

      setTargetsResponse(result);
      setError(null);

      if (result.enabled) {
        void loadSupportedLibraryStates(
          result.targets
        );
      }
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

  const loadHistory = async () => {
    setHistoryLoading(true);

    try {
      const [
        latest,
        history,
      ] = await Promise.all([
        api.getArtworkLatestRun(),
        api.getArtworkHistory(10),
      ]);

      setLatestRun(
        latest.run
      );

      setRecentRuns(
        history.runs
      );
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "Failed to load Artwork Manager history"
      );
    } finally {
      setHistoryLoading(false);
    }
  };

  const clearReviewFingerprint = (
    library: string
  ) => {
    setReviewFingerprints(
      (current) => ({
        ...current,
        [library]: null,
      })
    );
  };

  const handleArtworkApplyTerminal = async (
    library: string,
    apply: ArtworkReviewedApplyRecord
  ) => {
    await loadHistory();

    if (
      (
        apply.status === "applied" ||
        apply.status === "no_changes"
      ) &&
      apply.result
        ?.current_state_refreshed
    ) {
      const loaded =
        await loadCachedLibraryState(
          library
        );

      if (!loaded) {
        clearReviewFingerprint(
          library
        );

        setLibraryError(
          library,
          (
            `${library} apply completed, ` +
            "but refreshed current state could not be loaded"
          )
        );
      }

      return;
    }

    clearReviewFingerprint(
      library
    );

    await scanLibraryState(
      library
    );
  };


  const pollArtworkApply = async (
    library: string,
    applyId: string
  ) => {
    while (true) {
      await new Promise(
        (resolve) =>
          setTimeout(
            resolve,
            1000
          )
      );

      let result;

      try {
        result =
          await api.getArtworkReviewedApply(
            applyId
          );
      } catch (e: unknown) {
        const message =
          e instanceof Error
            ? e.message
            : `Lost reviewed apply status for ${library}`;

        clearReviewFingerprint(
          library
        );

        setApplies(
          (current) => {
            const existing =
              current[
                library
              ];

            if (!existing) {
              return current;
            }

            return {
              ...current,
              [library]: {
                ...existing,
                status: "failed",
                updated_at:
                  new Date().toISOString(),
                finished_at:
                  new Date().toISOString(),
                error: {
                  type: "ClientError",
                  message,
                },
              },
            };
          }
        );

        setLibraryError(
          library,
          message
        );

        return;
      }

      const apply =
        result.apply;

      setApplies(
        (current) => ({
          ...current,
          [library]: apply,
        })
      );

      if (
        apply.status === "running"
      ) {
        continue;
      }

      await handleArtworkApplyTerminal(
        library,
        apply
      );

      return;
    }
  };

  const submitReviewedApply = async (
    request: {
      target: ArtworkTarget;
      preview: ArtworkLibraryPreview;
      reviewFingerprint: string;
    }
  ) => {
    const library =
      request.target.library;

    const currentFingerprint =
      reviewFingerprints[
        library
      ] ?? null;

    if (
      currentFingerprint !==
      request.reviewFingerprint
    ) {
      setReviewDialog(null);
      clearReviewFingerprint(
        library
      );

      setLibraryError(
        library,
        "The reviewed plan changed locally. Refresh current state before applying."
      );

      return;
    }

    setStartingApplyLibrary(
      library
    );

    clearLibraryError(
      library
    );

    try {
      const started =
        await api.startArtworkReviewedApply(
          library,
          request.reviewFingerprint
        );

      const apply =
        started.apply;

      setApplies(
        (current) => ({
          ...current,
          [library]: apply,
        })
      );

      setReviewDialog(null);

      setStartingApplyLibrary(
        null
      );

      if (
        apply.status === "running"
      ) {
        void pollArtworkApply(
          library,
          apply.apply_id
        );
      } else {
        await handleArtworkApplyTerminal(
          library,
          apply
        );
      }
    } catch (e: unknown) {
      const message =
        e instanceof Error
          ? e.message
          : `Failed to start reviewed apply for ${library}`;

      // A 409 means the exact cached plan is no longer
      // immediately actionable. Never silently submit another.
      if (
        message.includes(
          "API error 409"
        )
      ) {
        clearReviewFingerprint(
          library
        );
        setReviewDialog(null);
      }

      setLibraryError(
        library,
        message
      );
    } finally {
      setStartingApplyLibrary(
        null
      );
    }
  };


  const refreshArtworkStatus = async () => {
    const targets =
      targetsResponse?.targets ?? [];

    await Promise.allSettled([
      loadHistory(),
      loadArtworkStatus(),
      targets.length > 0
        ? refreshSupportedLibraryStates(
            targets
          )
        : loadTargets(),
    ]);
  };

  useEffect(() => {
    loadTargets();
    loadHistory();
    loadArtworkStatus();
  }, []);

  const targets =
    targetsResponse?.targets ?? [];

  const applyBusy =
    startingApplyLibrary !== null ||
    Object.values(
      applies
    ).some(
      (apply) =>
        apply.status === "running"
    );

  const scanBusy =
    Object.values(
      scans
    ).some(
      (scan) =>
        scan.status === "running"
    );

  const setArtworkManagerEnabled = async (
    enabled: boolean
  ) => {
    setArtworkToggleBusy(
      true
    );

    try {
      await api.setServiceEnabled(
        "artwork_manager",
        enabled
      );

      await Promise.allSettled([
        loadArtworkStatus(),
        loadTargets(),
      ]);

      setError(
        null
      );
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "Failed to update Artwork Manager"
      );
    } finally {
      setArtworkToggleBusy(
        false
      );
    }
  };

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
              Monitor automated artwork management
              across Plex libraries and inspect
              proposed changes when needed.
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

      {artworkStatus && (
        <Card className="bg-zinc-900 border border-zinc-800 mb-6">
          <CardBody className="p-4">
            <div className="flex items-center justify-between gap-4">
              <Switch
                isSelected={artworkStatus.enabled}
                isDisabled={
                  artworkToggleBusy ||
                  scanBusy ||
                  applyBusy
                }
                onValueChange={(value) => {
                  void setArtworkManagerEnabled(
                    value
                  );
                }}
                color="success"
                size="sm"
              >
                <span
                  className={`text-sm font-semibold ${
                    artworkStatus.enabled
                      ? "text-green-400"
                      : "text-zinc-500"
                  }`}
                >
                  {artworkStatus.enabled
                    ? "Enabled"
                    : "Disabled"}
                </span>
              </Switch>

              <div className="text-right">
                <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">
                  Apply Mode
                </p>

                <p className="text-violet-300 font-semibold">
                  {artworkStatus.apply_mode === "auto"
                    ? "Automatic"
                    : "Manual Review"}
                </p>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {artworkStatus && (
        <Card className="bg-zinc-900 border border-zinc-800 mb-6">
          <CardBody className="p-5 space-y-5">
            <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-white font-semibold text-lg">
                    Artwork Configuration
                  </p>

                  <Chip
                    size="sm"
                    variant="flat"
                    color={
                      artworkStatus.enabled
                        ? "success"
                        : "default"
                    }
                  >
                    {artworkStatus.enabled
                      ? "Manager Enabled"
                      : "Manager Disabled"}
                  </Chip>

                  <Chip
                    size="sm"
                    variant="flat"
                    color={
                      artworkStatus.generator.enabled
                        ? "secondary"
                        : "default"
                    }
                  >
                    {artworkStatus.generator.enabled
                      ? "Generator Enabled"
                      : "Generator Disabled"}
                  </Chip>
                </div>

                <p className="text-zinc-400 text-sm mt-1">
                  Resolved Artwork Manager and episode-card
                  generator configuration.
                </p>
              </div>

              <div className="text-zinc-500 text-xs">
                Canonical runtime configuration
              </div>
            </div>

            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <Stat
                label="Primary Source"
                value={
                  artworkStatus.enabled &&
                  artworkStatus.primary_provider
                    ? artworkStatus.primary_provider
                        .charAt(0)
                        .toUpperCase() +
                      artworkStatus.primary_provider.slice(1)
                    : "Disabled"
                }
              />

              <Stat
                label="Apply Mode"
                value={
                  artworkStatus.enabled
                    ? artworkStatus.apply_mode === "auto"
                      ? "Automatic"
                      : "Manual Review"
                    : "—"
                }
              />

              <Stat
                label="Episode Generator"
                value={
                  artworkStatus.generator.enabled
                    ? "Enabled"
                    : "Disabled"
                }
              />

              <Stat
                label="Default Font"
                value={
                  artworkStatus.generator.enabled &&
                  artworkStatus.generator.default_font
                    ? artworkStatus.generator.default_font
                        .replaceAll(
                          "_",
                          " "
                        )
                    : "—"
                }
              />
            </div>

            {artworkStatus.enabled && (
              <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-4">
                <p className="text-zinc-500 text-xs uppercase tracking-wider mb-3">
                  Episode Artwork Priority
                </p>

                <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 text-sm">
                  <span className="text-violet-300 font-medium">
                    {artworkStatus.primary_provider
                      ? `${
                          artworkStatus.primary_provider
                            .charAt(0)
                            .toUpperCase() +
                          artworkStatus.primary_provider
                            .slice(1)
                        } Curated`
                      : "Curated Artwork"}
                  </span>

                  <span className="text-zinc-600 hidden sm:inline">
                    →
                  </span>

                  {artworkStatus.generator.enabled && (
                    <>
                      <span className="text-zinc-100 font-medium">
                        Dakosys Generated
                      </span>

                      <span className="text-zinc-600 hidden sm:inline">
                        →
                      </span>
                    </>
                  )}

                  <span className="text-zinc-400">
                    {artworkStatus.tmdb_enabled
                      ? "TMDB / Existing Fallback"
                      : "Existing Fallback"}
                  </span>
                </div>
              </div>
            )}

            <div className="grid lg:grid-cols-3 gap-3">
              <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
                <p className="text-zinc-500 text-xs uppercase tracking-wider">
                  Generator Config
                </p>

                <p className="text-zinc-300 text-xs font-mono mt-2 break-all">
                  {artworkStatus.generator.config_file ??
                    "—"}
                </p>
              </div>

              <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
                <p className="text-zinc-500 text-xs uppercase tracking-wider">
                  Local Generated Cache
                </p>

                <p className="text-zinc-300 text-xs font-mono mt-2 break-all">
                  {artworkStatus.generator.local_asset_root ??
                    "—"}
                </p>
              </div>

              <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
                <p className="text-zinc-500 text-xs uppercase tracking-wider">
                  Kometa Generated Path
                </p>

                <p className="text-zinc-300 text-xs font-mono mt-2 break-all">
                  {artworkStatus.generator.kometa_asset_root ??
                    "—"}
                </p>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      <ArtworkRunDashboard
        latest={latestRun}
        recent={recentRuns}
        loading={
          historyLoading ||
          scanBusy ||
          applyBusy
        }
        onRefresh={refreshArtworkStatus}
      />

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
              scan={
                scans[
                  target.library
                ] ?? null
              }
              apply={
                applies[
                  target.library
                ] ?? null
              }
              applyBusy={
                applyBusy
              }
              previewError={
                previewErrors[
                  target.library
                ] ?? null
              }
              scannedAt={
                scannedAt[
                  target.library
                ] ?? null
              }
              reviewFingerprint={
                reviewFingerprints[
                  target.library
                ] ?? null
              }
              onRefresh={(library) => {
                void scanLibraryState(
                  library
                );
              }}
              onReviewApply={(
                selectedTarget,
                selectedPreview,
                reviewFingerprint,
              ) => {
                setReviewDialog({
                  target:
                    selectedTarget,
                  preview:
                    selectedPreview,
                  reviewFingerprint,
                });
              }}
            />
          )
        )}
      </div>

      <Modal
        isOpen={
          reviewDialog !== null
        }
        onClose={() => {
          if (
            startingApplyLibrary === null
          ) {
            setReviewDialog(null);
          }
        }}
        backdrop="blur"
        size="lg"
      >
        <ModalContent>
          {(onClose) => {
            if (!reviewDialog) {
              return null;
            }

            const preview =
              reviewDialog.preview;

            const isMovie =
              preview.media_type === "movie";

            const generator =
              preview.generator ?? {
                changed_shows: 0,
                planned_cards: 0,
                cached_cards: 0,
                materialization_needed: 0,
                failures: 0,
              };

            return (
              <>
                <ModalHeader className="flex flex-col gap-1">
                  Apply {reviewDialog.target.library} Artwork?
                </ModalHeader>

                <ModalBody>
                  <p className="text-zinc-400 text-sm">
                    Review the exact cached plan before applying it.
                    Dakosys will rebuild and verify this plan again
                    before writing anything.
                  </p>

                  {isMovie ? (
                    <div className="grid grid-cols-2 gap-3">
                      <Stat
                        label="File Changes"
                        value={
                          preview.output.changed_files
                            .toLocaleString()
                        }
                      />

                      <Stat
                        label="Posters"
                        value={
                          preview.presentation.show_posters
                            .toLocaleString()
                        }
                      />

                      <Stat
                        label="Backgrounds"
                        value={
                          preview.presentation.backgrounds
                            .toLocaleString()
                        }
                      />

                      <Stat
                        label="Safety Issues"
                        value={
                          preview.safety.issues.length
                        }
                      />
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-3">
                      <Stat
                        label="Changed Shows"
                        value={
                          generator.changed_shows
                            .toLocaleString()
                        }
                      />

                      <Stat
                        label="Generated Cards"
                        value={
                          generator.planned_cards
                            .toLocaleString()
                        }
                      />

                      <Stat
                        label="To Materialize"
                        value={
                          generator
                            .materialization_needed
                            .toLocaleString()
                        }
                      />

                      <Stat
                        label="Safety Issues"
                        value={
                          preview.safety.issues.length
                        }
                      />
                    </div>
                  )}

                  <Card className="bg-zinc-950 border border-zinc-800">
                    <CardBody className="p-4">
                      <p className="text-zinc-400 text-xs uppercase tracking-wider mb-3">
                        Filesystem Changes
                      </p>

                      <div className="grid grid-cols-3 gap-3 text-center">
                        <div>
                          <p className="text-green-400 text-lg font-semibold">
                            {preview.output.added}
                          </p>
                          <p className="text-zinc-500 text-xs">
                            Added
                          </p>
                        </div>

                        <div>
                          <p className="text-yellow-400 text-lg font-semibold">
                            {preview.output.updated}
                          </p>
                          <p className="text-zinc-500 text-xs">
                            Updated
                          </p>
                        </div>

                        <div>
                          <p className="text-red-400 text-lg font-semibold">
                            {preview.output.removed}
                          </p>
                          <p className="text-zinc-500 text-xs">
                            Removed
                          </p>
                        </div>
                      </div>
                    </CardBody>
                  </Card>

                  {isMovie ? (
                    <Card className="bg-zinc-950 border border-zinc-800">
                      <CardBody className="p-4">
                        <p className="text-zinc-400 text-xs uppercase tracking-wider">
                          Managed Movies
                        </p>

                        <p className="text-zinc-200 text-lg font-semibold mt-2">
                          {preview.inventory.managed_before
                            .toLocaleString()}
                          {" → "}
                          {preview.inventory.managed_after
                            .toLocaleString()}
                        </p>

                        <p className="text-zinc-500 text-xs mt-1">
                          of{" "}
                          {preview.inventory.plex_shows
                            .toLocaleString()} Plex movies
                        </p>
                      </CardBody>
                    </Card>
                  ) : (
                    <Card className="bg-zinc-950 border border-zinc-800">
                      <CardBody className="p-4">
                        <p className="text-zinc-400 text-xs uppercase tracking-wider">
                          Episode Coverage
                        </p>

                        <p className="text-zinc-200 text-lg font-semibold mt-2">
                          {preview.coverage.cards_before
                            .toLocaleString()}
                          {" → "}
                          {preview.coverage.cards_after
                            .toLocaleString()}
                        </p>

                        <p className="text-zinc-500 text-xs mt-1">
                          of{" "}
                          {preview.coverage.expected_episodes
                            .toLocaleString()} expected episodes
                        </p>
                      </CardBody>
                    </Card>
                  )}

                  <div className="bg-violet-950/30 border border-violet-900/60 rounded-lg p-4">
                    <p className="text-violet-200 text-sm font-medium">
                      Exact reviewed plan
                    </p>

                    <p className="text-zinc-400 text-xs mt-1">
                      If Plex, provider data, generator inputs,
                      configuration, or filesystem state changed
                      since this preview, Dakosys will refuse the
                      apply and ask for a fresh scan.
                    </p>
                  </div>
                </ModalBody>

                <ModalFooter>
                  <Button
                    variant="flat"
                    isDisabled={
                      startingApplyLibrary !== null
                    }
                    onPress={onClose}
                  >
                    Cancel
                  </Button>

                  <Button
                    color="secondary"
                    isLoading={
                      startingApplyLibrary ===
                      reviewDialog.target.library
                    }
                    isDisabled={
                      startingApplyLibrary !== null
                    }
                    onPress={() => {
                      void submitReviewedApply(
                        reviewDialog
                      );
                    }}
                  >
                    Apply {reviewDialog.target.library}
                  </Button>
                </ModalFooter>
              </>
            );
          }}
        </ModalContent>
      </Modal>
    </div>
  );
}
