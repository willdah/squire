"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { HostInfo } from "@/lib/types";
import { ArrowLeft, Server, Wifi, WifiOff } from "lucide-react";

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

function HostDetail({ name }: { name: string }) {
  const { data: host, isLoading } = useSWR(`/api/hosts/${name}`, () =>
    apiGet<HostInfo>(`/api/hosts/${name}`)
  );

  if (isLoading || !host) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 rounded-lg" />
      </div>
    );
  }

  const isReachable = host.snapshot && !host.snapshot.error;

  return (
    <div className="space-y-6 animate-fade-in">
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
        </CardContent>
      </Card>
    </div>
  );
}

function HostList() {
  const { data: hosts, isLoading } = useSWR("/api/hosts", () =>
    apiGet<HostInfo[]>("/api/hosts")
  );

  if (isLoading || !hosts) {
    return <HostsSkeleton />;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl">Hosts</h1>
        <Badge variant="secondary">{hosts.length}</Badge>
      </div>
      <p className="text-sm text-muted-foreground">
        Hosts that Squire can connect to. For live metrics, use Beszel or Grafana.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {hosts.map((host) => {
          const isReachable = host.snapshot && !host.snapshot.error;

          return (
            <Link key={host.name} href={`/hosts?name=${host.name}`}>
              <Card className="hover:border-primary/50 transition-colors cursor-pointer">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Server className="h-4 w-4" />
                    {host.name}
                    {isReachable ? (
                      <Wifi className="h-3 w-3 text-green-500 ml-auto" />
                    ) : (
                      <WifiOff className="h-3 w-3 text-destructive ml-auto" />
                    )}
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
      </div>
    </div>
  );
}

export default function HostsPage() {
  return (
    <Suspense
      fallback={<HostsSkeleton />}
    >
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
