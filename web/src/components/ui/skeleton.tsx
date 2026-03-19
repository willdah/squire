import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-md bg-muted",
        className
      )}
      style={{
        backgroundImage: "linear-gradient(90deg, transparent 0%, oklch(0.8 0.005 270 / 0.15) 50%, transparent 100%)",
        backgroundSize: "200% 100%",
        animation: "skeleton-shimmer 1.5s ease-in-out infinite",
      }}
      {...props}
    />
  );
}
