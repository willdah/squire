"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet, apiPut } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { WatchConfigResponse } from "@/lib/types";

interface WatchConfigDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const riskLevels = [
  { value: 1, label: "Read" },
  { value: 2, label: "Low" },
  { value: 3, label: "Mod" },
  { value: 4, label: "High" },
  { value: 5, label: "Full" },
];

export function WatchConfigDrawer({ open, onOpenChange }: WatchConfigDrawerProps) {
  const { data: config } = useSWR(
    open ? "/api/watch/config" : null,
    () => apiGet<WatchConfigResponse>("/api/watch/config"),
  );

  const [interval, setInterval_] = useState(5);
  const [risk, setRisk] = useState(3);
  const [prompt, setPrompt] = useState("");
  const [maxIdenticalActions, setMaxIdenticalActions] = useState(2);
  const [blockedCooldown, setBlockedCooldown] = useState(3);
  const [maxRemoteActions, setMaxRemoteActions] = useState(4);
  const [prevConfig, setPrevConfig] = useState(config);

  if (config && config !== prevConfig) {
    setPrevConfig(config);
    setInterval_(config.interval_minutes);
    setRisk(config.risk_tolerance ?? 3);
    setPrompt(config.checkin_prompt);
    setMaxIdenticalActions(config.max_identical_actions_per_cycle);
    setBlockedCooldown(config.blocked_action_cooldown_cycles);
    setMaxRemoteActions(config.max_remote_actions_per_cycle);
  }

  const handleApply = async () => {
    await apiPut("/api/watch/config", {
      interval_minutes: interval,
      risk_tolerance: risk,
      checkin_prompt: prompt,
      max_identical_actions_per_cycle: maxIdenticalActions,
      blocked_action_cooldown_cycles: blockedCooldown,
      max_remote_actions_per_cycle: maxRemoteActions,
    });
    onOpenChange(false);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Watch Configuration</SheetTitle>
          <SheetDescription>Changes take effect next cycle.</SheetDescription>
        </SheetHeader>
        <div className="space-y-6 py-6">
          <div className="space-y-2">
            <Label>Interval (minutes)</Label>
            <Input
              type="number"
              min={1}
              value={interval}
              onChange={(e) => setInterval_(parseInt(e.target.value) || 1)}
            />
          </div>
          <div className="space-y-2">
            <Label>Risk Tolerance</Label>
            <div className="flex gap-1">
              {riskLevels.map((level) => (
                <Button
                  key={level.value}
                  variant={risk === level.value ? "default" : "outline"}
                  size="sm"
                  className="flex-1 text-xs"
                  onClick={() => setRisk(level.value)}
                >
                  {level.value} {level.label}
                </Button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <Label>Check-in Prompt</Label>
            <Textarea
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Max identical actions per cycle</Label>
            <Input
              type="number"
              min={1}
              value={maxIdenticalActions}
              onChange={(e) => setMaxIdenticalActions(parseInt(e.target.value) || 1)}
            />
          </div>
          <div className="space-y-2">
            <Label>Blocked action cooldown (cycles)</Label>
            <Input
              type="number"
              min={1}
              value={blockedCooldown}
              onChange={(e) => setBlockedCooldown(parseInt(e.target.value) || 1)}
            />
          </div>
          <div className="space-y-2">
            <Label>Max remote actions per cycle</Label>
            <Input
              type="number"
              min={1}
              value={maxRemoteActions}
              onChange={(e) => setMaxRemoteActions(parseInt(e.target.value) || 1)}
            />
          </div>
        </div>
        <SheetFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleApply}>Apply</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
