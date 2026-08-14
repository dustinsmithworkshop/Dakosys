"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Button,
  Card,
  CardBody,
  Chip,
  Input,
  Spinner,
} from "@nextui-org/react";

import { api } from "@/lib/api";
import type {
  TraktAuthStatus,
  TraktDeviceCodeResponse,
  TraktOverviewResponse,
} from "@/types/api";

function ValueCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="bg-zinc-800/50 border border-zinc-800 rounded-lg p-4">
      <p className="text-xs text-zinc-500">
        {label}
      </p>
      <p className="text-xl font-semibold text-white mt-1">
        {value}
      </p>
      {detail && (
        <p className="text-xs text-zinc-500 mt-1">
          {detail}
        </p>
      )}
    </div>
  );
}

function RequirementRow({
  label,
  enabled,
  detail,
}: {
  label: string;
  enabled: boolean;
  detail: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div>
        <p className="text-sm text-zinc-200">
          {label}
        </p>
        <p className="text-xs text-zinc-500 mt-0.5">
          {detail}
        </p>
      </div>

      <Chip
        size="sm"
        variant="flat"
        color={enabled ? "secondary" : "default"}
      >
        {enabled ? "Uses Trakt" : "Off"}
      </Chip>
    </div>
  );
}

export default function TraktPage() {
  const [authStatus, setAuthStatus] =
    useState<TraktAuthStatus | null>(null);
  const [overview, setOverview] =
    useState<TraktOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] =
    useState<string | null>(null);

  const [reconnectOpen, setReconnectOpen] =
    useState(false);
  const [rcClientId, setRcClientId] =
    useState("");
  const [rcClientSecret, setRcClientSecret] =
    useState("");
  const [rcUsername, setRcUsername] =
    useState("");

  const [rcStep, setRcStep] =
    useState<"form" | "device">("form");
  const [rcDeviceInfo, setRcDeviceInfo] =
    useState<TraktDeviceCodeResponse | null>(
      null,
    );
  const [rcPolling, setRcPolling] =
    useState(false);
  const [rcSaving, setRcSaving] =
    useState(false);
  const [rcSuccess, setRcSuccess] =
    useState(false);
  const [rcError, setRcError] =
    useState<string | null>(null);
  const [rcCountdown, setRcCountdown] =
    useState(0);

  const pollIntervalRef =
    useRef<ReturnType<typeof setInterval> | null>(
      null,
    );
  const countdownIntervalRef =
    useRef<ReturnType<typeof setInterval> | null>(
      null,
    );

  const fetchData = useCallback(async () => {
    setLoading(true);
    setPageError(null);

    const [statusResult, overviewResult] =
      await Promise.allSettled([
        api.getTraktAuthStatus(),
        api.getTraktOverview(),
      ]);

    if (statusResult.status === "fulfilled") {
      setAuthStatus(statusResult.value);
    } else {
      setAuthStatus(null);
      setPageError(
        statusResult.reason instanceof Error
          ? statusResult.reason.message
          : "Failed to load Trakt status",
      );
    }

    if (overviewResult.status === "fulfilled") {
      setOverview(overviewResult.value);
    } else {
      setOverview(null);
      setPageError(
        overviewResult.reason instanceof Error
          ? overviewResult.reason.message
          : "Failed to load Trakt overview",
      );
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }

      if (countdownIntervalRef.current) {
        clearInterval(
          countdownIntervalRef.current,
        );
      }
    };
  }, []);

  function openReconnect() {
    setRcClientId(
      authStatus?.client_id ?? "",
    );

    // Never rehydrate the secret into browser state.
    setRcClientSecret("");
    setRcUsername(
      authStatus?.username ?? "",
    );

    setRcStep("form");
    setRcDeviceInfo(null);
    setRcPolling(false);
    setRcSaving(false);
    setRcSuccess(false);
    setRcError(null);
    setRcCountdown(0);
    setReconnectOpen(true);
  }

  function stopPolling() {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }

    if (countdownIntervalRef.current) {
      clearInterval(
        countdownIntervalRef.current,
      );
      countdownIntervalRef.current = null;
    }
  }

  async function closeReconnect() {
    stopPolling();
    setReconnectOpen(false);

    if (rcSuccess) {
      await fetchData();
    }
  }

  async function handleGetDeviceCode() {
    if (!rcClientId.trim()) {
      setRcError("Client ID is required");
      return;
    }

    if (!rcClientSecret.trim()) {
      setRcError(
        "Client Secret is required",
      );
      return;
    }

    if (!rcUsername.trim()) {
      setRcError("Username is required");
      return;
    }

    setRcError(null);

    try {
      const data =
        await api.getTraktDeviceCode(
          rcClientId.trim(),
        );

      setRcDeviceInfo(data);
      setRcStep("device");
      setRcCountdown(data.expires_in);
      setRcPolling(true);

      stopPolling();

      countdownIntervalRef.current =
        setInterval(() => {
          setRcCountdown((value) => {
            if (value <= 1) {
              if (
                countdownIntervalRef.current
              ) {
                clearInterval(
                  countdownIntervalRef.current,
                );
                countdownIntervalRef.current =
                  null;
              }

              return 0;
            }

            return value - 1;
          });
        }, 1000);

      pollIntervalRef.current =
        setInterval(async () => {
          try {
            const poll =
              await api.pollTraktDeviceToken(
                data.device_code,
                rcClientId.trim(),
                rcClientSecret.trim(),
              );

            if (poll.authorized) {
              stopPolling();
              setRcPolling(false);
              setRcSaving(true);

              try {
                await api.updateTraktCredentials(
                  rcClientId.trim(),
                  rcClientSecret.trim(),
                  rcUsername.trim(),
                );

                setRcSuccess(true);
                setRcError(null);
              } catch (e: unknown) {
                setRcError(
                  e instanceof Error
                    ? e.message
                    : "Authorization succeeded, but credentials could not be saved",
                );
              } finally {
                setRcSaving(false);
              }

              return;
            }

            if (poll.pending === false) {
              stopPolling();
              setRcPolling(false);
              setRcError(
                poll.error ??
                  "Authorization failed or expired",
              );
            }
          } catch {
            // Transient poll errors are retried until
            // Trakt expires the device code.
          }
        }, (data.interval ?? 5) * 1000);
    } catch (e: unknown) {
      setRcError(
        e instanceof Error
          ? e.message
          : "Failed to get Trakt device code",
      );
    }
  }

  const usage = overview?.usage ?? null;

  const accountLabel =
    usage?.vip === true
      ? "VIP"
      : usage?.vip === false
        ? "Non-VIP"
        : "Unknown";

  const formatNumber = (
    value: number | null | undefined,
  ) =>
    value === null || value === undefined
      ? "Unknown"
      : String(value);

  const tokenExpiry =
    authStatus?.token_expiry
      ? new Date(
          authStatus.token_expiry * 1000,
        ).toLocaleString()
      : null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">
            Trakt
          </h1>
          <p className="text-zinc-400 mt-1">
            Authentication, live account
            capabilities, and optional Trakt features
          </p>
        </div>

        <Button
          variant="flat"
          color="default"
          isDisabled={loading}
          onPress={fetchData}
        >
          Refresh
        </Button>
      </div>

      {loading && (
        <div className="flex justify-center items-center h-40">
          <Spinner color="secondary" />
        </div>
      )}

      {pageError && !loading && (
        <div className="bg-red-950/40 border border-red-800 rounded-lg p-4">
          <p className="text-red-400 text-sm">
            {pageError}
          </p>
        </div>
      )}

      {!loading && (
        <>
          {/* Connection */}
          <Card className="bg-zinc-900 border border-zinc-800">
            <CardBody className="p-6 space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-white">
                    Connection
                  </h2>
                  <p className="text-xs text-zinc-500 mt-1">
                    Trakt is only required when an
                    enabled feature uses Trakt.
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Chip
                    size="sm"
                    variant="flat"
                    color={
                      overview?.required
                        ? "secondary"
                        : "default"
                    }
                  >
                    {overview?.required
                      ? "Required"
                      : "Optional"}
                  </Chip>

                  <Chip
                    size="sm"
                    variant="flat"
                    color={
                      authStatus?.configured
                        ? "success"
                        : "default"
                    }
                  >
                    {authStatus?.configured
                      ? "Configured"
                      : "Not configured"}
                  </Chip>

                  <Chip
                    size="sm"
                    variant="flat"
                    color={
                      authStatus?.connected
                        ? "success"
                        : "danger"
                    }
                  >
                    {authStatus?.connected
                      ? "Token active"
                      : "Not authorized"}
                  </Chip>
                </div>
              </div>

              {!overview?.required &&
                !authStatus?.configured && (
                  <div className="bg-green-950/30 border border-green-900 rounded-lg p-3">
                    <p className="text-green-300 text-sm font-medium">
                      No Trakt configuration is needed
                    </p>
                    <p className="text-zinc-400 text-xs mt-1">
                      Your currently enabled services
                      can run without Trakt.
                    </p>
                  </div>
                )}

              {overview?.required &&
                !authStatus?.configured && (
                  <div className="bg-yellow-950/30 border border-yellow-900 rounded-lg p-3">
                    <p className="text-yellow-300 text-sm font-medium">
                      Trakt configuration required
                    </p>
                    <p className="text-zinc-400 text-xs mt-1">
                      One or more enabled features use
                      Trakt, but credentials are
                      incomplete.
                    </p>
                  </div>
                )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <ValueCard
                  label="Username"
                  value={
                    authStatus?.username ||
                    "Not configured"
                  }
                />

                <ValueCard
                  label="Client ID"
                  value={
                    authStatus?.client_id
                      ? "Configured"
                      : "Not configured"
                  }
                />

                <ValueCard
                  label="User token"
                  value={
                    authStatus?.connected
                      ? "Active"
                      : "Not active"
                  }
                  detail={
                    tokenExpiry
                      ? `Expires ${tokenExpiry}`
                      : undefined
                  }
                />
              </div>

              <div>
                <Button
                  size="sm"
                  color="secondary"
                  variant="flat"
                  onPress={openReconnect}
                >
                  {authStatus?.configured
                    ? "Reconnect"
                    : "Configure Trakt"}
                </Button>
              </div>
            </CardBody>
          </Card>

          {/* Feature requirements */}
          <Card className="bg-zinc-900 border border-zinc-800">
            <CardBody className="p-6">
              <h2 className="text-lg font-semibold text-white">
                Trakt-backed Features
              </h2>
              <p className="text-xs text-zinc-500 mt-1 mb-3">
                Automatic scheduling and legacy
                episode-list publishing are the only
                Trakt-backed features. TV/Anime Status
                Tracker, Next Airing, and Anime Episode
                Type run without Trakt.
              </p>

              <div className="divide-y divide-zinc-800">
                <RequirementRow
                  label="Automatic Active/Future Schedule"
                  enabled={
                    overview?.requirements
                      .auto_schedule ?? false
                  }
                  detail="Uses Trakt show metadata only; does not publish episode-type lists."
                />

                <RequirementRow
                  label="Legacy Episode-List Publishing"
                  enabled={
                    overview?.requirements
                      .legacy_episode_publishing ??
                    false
                  }
                  detail="Compatibility mode that publishes filler/canon classifications as personal Trakt lists."
                />
              </div>
            </CardBody>
          </Card>

          {/* Live capability data */}
          <Card className="bg-zinc-900 border border-zinc-800">
            <CardBody className="p-6 space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-white">
                  Live Account Capabilities
                </h2>
                <p className="text-xs text-zinc-500 mt-1">
                  Limits are read from Trakt at
                  runtime. Dakosys does not assume
                  limits based on account labels.
                </p>
              </div>

              {overview?.error && (
                <div className="bg-yellow-950/30 border border-yellow-900 rounded-lg p-3">
                  <p className="text-yellow-300 text-sm">
                    {overview.error}
                  </p>
                </div>
              )}

              {usage ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  <ValueCard
                    label="Account"
                    value={accountLabel}
                    detail={
                      usage.username
                        ? `Authenticated as ${usage.username}`
                        : undefined
                    }
                  />

                  <ValueCard
                    label="Personal lists"
                    value={`${usage.lists.current} / ${formatNumber(
                      usage.lists.maximum,
                    )}`}
                    detail={`${formatNumber(
                      usage.lists.remaining,
                    )} remaining`}
                  />

                  <ValueCard
                    label="Items per list"
                    value={formatNumber(
                      usage.items_per_list
                        .maximum,
                    )}
                    detail="Maximum reported by Trakt"
                  />

                  <ValueCard
                    label="Limits"
                    value={
                      usage.limits_known
                        ? "Known"
                        : "Incomplete"
                    }
                    detail="Unknown values remain unknown"
                  />
                </div>
              ) : (
                <p className="text-sm text-zinc-500">
                  Live capability data is not
                  available.
                </p>
              )}
            </CardBody>
          </Card>

          {/* Legacy publishing */}
          <Card className="bg-zinc-900 border border-zinc-800">
            <CardBody className="p-6 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-white">
                    Legacy Episode-List Publishing
                  </h2>
                  <p className="text-xs text-zinc-500 mt-1">
                    Optional compatibility mode for
                    publishing episode classifications
                    as Trakt personal lists.
                  </p>
                </div>

                <Chip
                  size="sm"
                  variant="flat"
                  color={
                    overview
                      ?.legacy_episode_publishing
                      ? "warning"
                      : "success"
                  }
                >
                  {overview
                    ?.legacy_episode_publishing
                    ? "Enabled"
                    : "Disabled"}
                </Chip>
              </div>

              {overview
                ?.legacy_episode_publishing ? (
                <div className="bg-yellow-950/30 border border-yellow-900 rounded-lg p-3">
                  <p className="text-yellow-300 text-sm font-medium">
                    High-volume compatibility mode is
                    enabled
                  </p>
                  <p className="text-zinc-400 text-xs mt-1">
                    Dakosys will enforce the personal
                    list and per-list item limits
                    reported by the authenticated
                    account.
                  </p>
                </div>
              ) : (
                <div className="bg-zinc-800/50 rounded-lg p-3">
                  <p className="text-zinc-300 text-sm">
                    Disabled as recommended for the
                    local episode backend.
                  </p>
                  <p className="text-zinc-500 text-xs mt-1">
                    Local Anime Episode Type
                    generation does not need these
                    personal lists.
                  </p>
                </div>
              )}

              {overview?.list_privacy && (
                <p className="text-xs text-zinc-500">
                  Personal-list privacy:{" "}
                  <span className="text-zinc-300">
                    {overview.list_privacy}
                  </span>
                </p>
              )}
            </CardBody>
          </Card>
        </>
      )}

      {/* Reconnect / configure modal */}
      {reconnectOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-lg bg-zinc-900 border border-zinc-700 rounded-xl p-6 shadow-2xl">
            {rcSuccess ? (
              <>
                <h2 className="text-lg font-bold text-white">
                  Trakt Connected
                </h2>

                <p className="text-green-300 text-sm mt-3">
                  Authorization and credentials were
                  saved successfully.
                </p>

                <div className="flex justify-end mt-5">
                  <Button
                    color="secondary"
                    onPress={closeReconnect}
                  >
                    Done
                  </Button>
                </div>
              </>
            ) : rcStep === "form" ? (
              <>
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-lg font-bold text-white">
                    Configure Trakt
                  </h2>

                  <button
                    onClick={closeReconnect}
                    className="text-zinc-500 hover:text-zinc-300 text-xl"
                    aria-label="Close"
                  >
                    ✕
                  </button>
                </div>

                <p className="text-xs text-zinc-500 mb-4">
                  For security, the saved client
                  secret is never returned to the
                  browser. Enter it again when
                  reconnecting.
                </p>

                <div className="space-y-3">
                  <Input
                    label="Client ID"
                    value={rcClientId}
                    onValueChange={setRcClientId}
                    variant="bordered"
                    classNames={{
                      input:
                        "text-white",
                      inputWrapper:
                        "bg-zinc-800 border-zinc-700",
                    }}
                  />

                  <Input
                    label="Client Secret"
                    type="password"
                    value={rcClientSecret}
                    onValueChange={
                      setRcClientSecret
                    }
                    variant="bordered"
                    classNames={{
                      input:
                        "text-white",
                      inputWrapper:
                        "bg-zinc-800 border-zinc-700",
                    }}
                  />

                  <Input
                    label="Trakt Username"
                    value={rcUsername}
                    onValueChange={setRcUsername}
                    variant="bordered"
                    classNames={{
                      input:
                        "text-white",
                      inputWrapper:
                        "bg-zinc-800 border-zinc-700",
                    }}
                  />
                </div>

                {rcError && (
                  <p className="text-red-400 text-sm mt-3">
                    {rcError}
                  </p>
                )}

                <div className="flex gap-2 justify-end mt-5">
                  <Button
                    variant="flat"
                    color="default"
                    onPress={closeReconnect}
                  >
                    Cancel
                  </Button>

                  <Button
                    color="secondary"
                    onPress={handleGetDeviceCode}
                  >
                    Get Authorization Code
                  </Button>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-lg font-bold text-white">
                    Authorize on Trakt
                  </h2>

                  <button
                    onClick={() => {
                      stopPolling();
                      setRcStep("form");
                      setRcPolling(false);
                      setRcDeviceInfo(null);
                      setRcError(null);
                    }}
                    className="text-zinc-500 hover:text-zinc-300 text-xl"
                    aria-label="Back"
                  >
                    ✕
                  </button>
                </div>

                <ol className="text-sm text-zinc-300 space-y-4">
                  <li>
                    1. Visit{" "}
                    <a
                      href={
                        rcDeviceInfo
                          ?.verification_url
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-violet-400 hover:text-violet-300 underline"
                    >
                      {
                        rcDeviceInfo
                          ?.verification_url
                      }
                    </a>
                  </li>

                  <li>
                    2. Enter code{" "}
                    <button
                      className="font-mono font-bold text-white bg-zinc-700 hover:bg-zinc-600 px-2 py-1 rounded"
                      onClick={() =>
                        navigator.clipboard.writeText(
                          rcDeviceInfo
                            ?.user_code ?? "",
                        )
                      }
                    >
                      {rcDeviceInfo?.user_code}
                    </button>
                  </li>

                  <li>
                    3. Approve access in your browser.
                  </li>
                </ol>

                <div className="flex items-center gap-3 bg-zinc-800 rounded-lg px-4 py-3 mt-5">
                  {rcPolling || rcSaving ? (
                    <Spinner
                      size="sm"
                      color="secondary"
                    />
                  ) : (
                    <span className="w-4 h-4 rounded-full bg-zinc-600" />
                  )}

                  <span className="text-sm text-zinc-300">
                    {rcSaving
                      ? "Saving credentials..."
                      : rcPolling
                        ? "Waiting for authorization..."
                        : "Polling stopped"}
                  </span>

                  {rcCountdown > 0 && (
                    <span className="ml-auto text-xs text-zinc-500">
                      {Math.floor(
                        rcCountdown / 60,
                      )}
                      :
                      {String(
                        rcCountdown % 60,
                      ).padStart(2, "0")}
                    </span>
                  )}
                </div>

                {rcError && (
                  <p className="text-red-400 text-sm mt-3">
                    {rcError}
                  </p>
                )}

                {rcCountdown === 0 &&
                  !rcPolling &&
                  !rcSaving && (
                    <div className="flex gap-2 justify-end mt-5">
                      <Button
                        variant="flat"
                        color="default"
                        onPress={() => {
                          setRcStep("form");
                          setRcDeviceInfo(null);
                          setRcError(null);
                        }}
                      >
                        Try Again
                      </Button>

                      <Button
                        variant="flat"
                        color="default"
                        onPress={closeReconnect}
                      >
                        Cancel
                      </Button>
                    </div>
                  )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
