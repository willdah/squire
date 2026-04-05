"use client";

import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import useSWR, { mutate } from "swr";
import Link from "next/link";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  HostInfo,
  HostEnrollmentResponse,
  HostVerifyResponse,
} from "@/lib/types";
import {
  ArrowLeft,
  Check,
  Copy,
  Loader2,
  Plus,
  Server,
  ShieldAlert,
  Trash2,
  Wifi,
  WifiOff,
} from "lucide-react";

function HostsSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-32" />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-40 rounded-lg" />
        ))}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "active") {
    return (
      <Badge variant="secondary" className="gap-1">
        <Check className="h-3 w-3" />
        Active
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 border-amber-500 text-amber-600">
      <ShieldAlert className="h-3 w-3" />
      Pending Key
    </Badge>
  );
}

function AddHostDialog() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<HostEnrollmentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const form = new FormData(e.currentTarget);
    const tagsStr = (form.get("tags") as string) || "";
    const servicesStr = (form.get("services") as string) || "";

    try {
      const res = await apiPost<HostEnrollmentResponse>("/api/hosts", {
        name: form.get("name"),
        address: form.get("address"),
        user: form.get("user") || "root",
        port: Number(form.get("port")) || 22,
        tags: tagsStr
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        services: servicesStr
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        service_root: form.get("service_root") || "/opt",
      });
      setResult(res);
      mutate("/api/hosts");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enrollment failed");
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setOpen(false);
    setResult(null);
    setError(null);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" className="gap-1" />}>
        <Plus className="h-4 w-4" />
        Add Host
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {result ? "Enrollment Result" : "Add Host"}
          </DialogTitle>
          <DialogDescription>
            {result
              ? "Review the enrollment result below."
              : "Enter the connection details for the remote host."}
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <StatusBadge status={result.status} />
              <span className="text-sm">{result.message}</span>
            </div>
            {result.status === "pending_key" && (
              <CopyableKey publicKey={result.public_key} />
            )}
            <Button onClick={handleClose} className="w-full">
              Done
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  name="name"
                  placeholder="media-server"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="address">Address</Label>
                <Input
                  id="address"
                  name="address"
                  placeholder="10.0.0.5"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="user">User</Label>
                <Input
                  id="user"
                  name="user"
                  placeholder="root"
                  defaultValue="root"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="port">Port</Label>
                <Input
                  id="port"
                  name="port"
                  type="number"
                  placeholder="22"
                  defaultValue="22"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="tags">Tags (comma-separated)</Label>
              <Input
                id="tags"
                name="tags"
                placeholder="production, docker"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="services">Services (comma-separated)</Label>
              <Input
                id="services"
                name="services"
                placeholder="nginx, postgres"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="service_root">Service Root</Label>
              <Input
                id="service_root"
                name="service_root"
                placeholder="/opt"
                defaultValue="/opt"
              />
            </div>
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Enroll Host
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function CopyableKey({ publicKey }: { publicKey: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(publicKey);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = publicKey;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">
        Add this public key to{" "}
        <code className="text-xs">~/.ssh/authorized_keys</code> on the remote
        host:
      </p>
      <div className="relative">
        <pre className="bg-muted p-3 rounded text-xs break-all whitespace-pre-wrap">
          {publicKey}
        </pre>
        <Button
          size="icon"
          variant="ghost"
          className="absolute top-1 right-1 h-7 w-7"
          onClick={handleCopy}
        >
          {copied ? (
            <Check className="h-3 w-3" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
        </Button>
      </div>
    </div>
  );
}

function HostDetail({ name }: { name: string }) {
  const router = useRouter();
  const { data: host, isLoading } = useSWR(`/api/hosts/${name}`, () =>
    apiGet<HostInfo>(`/api/hosts/${name}`)
  );
  const { data: keyData } = useSWR(
    host?.status === "pending_key" ? `/api/hosts/${name}/public-key` : null,
    () => apiGet<{ name: string; public_key: string }>(`/api/hosts/${name}/public-key`)
  );
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<"success" | "failed" | null>(null);
  const [removing, setRemoving] = useState(false);

  if (isLoading || !host) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 rounded-lg" />
      </div>
    );
  }

  const isReachable = host.snapshot && !host.snapshot.error;

  const handleVerify = async () => {
    setVerifying(true);
    setVerifyResult(null);
    try {
      const res = await apiPost<HostVerifyResponse>(`/api/hosts/${name}/verify`);
      await mutate(`/api/hosts/${name}`);
      await mutate("/api/hosts");
      setVerifyResult(res.reachable ? "success" : "failed");
      if (res.reachable) {
        setTimeout(() => setVerifyResult(null), 3000);
      }
    } catch {
      setVerifyResult("failed");
    } finally {
      setVerifying(false);
    }
  };

  const handleRemove = async () => {
    if (!confirm(`Remove host '${name}'? This deletes the SSH key.`)) return;
    setRemoving(true);
    try {
      await apiDelete(`/api/hosts/${name}`);
      await mutate("/api/hosts");
      router.push("/hosts");
    } finally {
      setRemoving(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="flex items-center gap-3">
        <Link href="/hosts">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="text-2xl">{host.name}</h1>
        {isReachable ? (
          <Badge variant="secondary" className="gap-1">
            <Wifi className="h-3 w-3" />
            Reachable
          </Badge>
        ) : (
          <Badge variant="destructive" className="gap-1">
            <WifiOff className="h-3 w-3" />
            Unreachable
          </Badge>
        )}
        <StatusBadge status={host.status} />
      </div>

      <Card>
        <CardContent className="pt-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Address</p>
              <p className="font-mono">
                {host.address}
                {host.port !== 22 && `:${host.port}`}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">User</p>
              <p className="font-mono">{host.user}</p>
            </div>
            {host.snapshot?.hostname && (
              <div>
                <p className="text-muted-foreground">Hostname</p>
                <p className="font-mono">{host.snapshot.hostname}</p>
              </div>
            )}
            {host.snapshot?.os_info && (
              <div>
                <p className="text-muted-foreground">OS</p>
                <p className="font-mono">{host.snapshot.os_info}</p>
              </div>
            )}
          </div>

          {host.services.length > 0 && (
            <div>
              <p className="text-sm text-muted-foreground mb-2">Services</p>
              <div className="flex flex-wrap gap-1">
                {host.services.map((svc) => (
                  <Badge key={svc} variant="outline">
                    {svc}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {host.tags.length > 0 && (
            <div>
              <p className="text-sm text-muted-foreground mb-2">Tags</p>
              <div className="flex flex-wrap gap-1">
                {host.tags.map((tag) => (
                  <Badge key={tag} variant="secondary">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {host.status === "pending_key" && keyData?.public_key && (
            <CopyableKey publicKey={keyData.public_key} />
          )}

          {host.source === "managed" && (
            <div className="space-y-2 pt-2 border-t">
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleVerify}
                  disabled={verifying}
                >
                  {verifying && (
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                  )}
                  Test Connection
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={handleRemove}
                  disabled={removing}
                >
                  {removing ? (
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                  ) : (
                    <Trash2 className="h-3 w-3 mr-1" />
                  )}
                  Remove
                </Button>
                {verifyResult === "success" && (
                  <span className="text-sm text-green-600 flex items-center gap-1">
                    <Check className="h-3 w-3" />
                    Connected
                  </span>
                )}
                {verifyResult === "failed" && (
                  <span className="text-sm text-destructive">
                    Connection failed
                  </span>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function HostList() {
  const { data: hosts, isLoading } = useSWR("/api/hosts", () =>
    apiGet<HostInfo[]>("/api/hosts")
  );

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl">Hosts</h1>
        {hosts && <Badge variant="secondary">{hosts.length}</Badge>}
        <div className="ml-auto">
          <AddHostDialog />
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        Hosts that Squire can connect to and manage.
      </p>
      {(isLoading || !hosts) && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40 rounded-lg" />
          ))}
        </div>
      )}
      {hosts && hosts.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No hosts configured. Click &quot;Add Host&quot; to enroll a remote
          host.
        </p>
      )}
      {hosts && <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {hosts.map((host) => {
          const isReachable = host.snapshot && !host.snapshot.error;

          return (
            <Link key={host.name} href={`/hosts?name=${host.name}`}>
              <Card className="hover:border-primary/50 transition-colors cursor-pointer">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Server className="h-4 w-4" />
                    {host.name}
                    <div className="ml-auto flex items-center gap-1">
                      <StatusBadge status={host.status} />
                      {isReachable ? (
                        <Wifi className="h-3 w-3 text-green-500" />
                      ) : (
                        <WifiOff className="h-3 w-3 text-destructive" />
                      )}
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-sm text-muted-foreground font-mono">
                    {host.user}@{host.address}
                    {host.port !== 22 && `:${host.port}`}
                  </p>
                  {host.services.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {host.services.map((svc) => (
                        <Badge
                          key={svc}
                          variant="outline"
                          className="text-xs"
                        >
                          {svc}
                        </Badge>
                      ))}
                    </div>
                  )}
                  {host.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {host.tags.map((tag) => (
                        <Badge
                          key={tag}
                          variant="secondary"
                          className="text-xs"
                        >
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>}
    </div>
  );
}

export default function HostsPage() {
  return (
    <Suspense fallback={<HostsSkeleton />}>
      <HostsPageInner />
    </Suspense>
  );
}

function HostsPageInner() {
  const searchParams = useSearchParams();
  const name = searchParams.get("name");

  if (name) {
    return <HostDetail name={name} />;
  }

  return <HostList />;
}
