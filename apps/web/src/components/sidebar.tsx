"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Mic2, Library, History, Settings, Sparkles, Code2 } from "lucide-react";
import clsx from "clsx";

const items = [
  { href: "/", label: "대시보드", icon: Home },
  { href: "/studio", label: "스튜디오", icon: Mic2 },
  { href: "/speakers", label: "화자", icon: Library },
  { href: "/history", label: "히스토리", icon: History },
  { href: "/api-docs", label: "API", icon: Code2 },
  { href: "/settings", label: "설정", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-card px-3 py-4 md:flex">
      <div className="mb-6 flex items-center gap-2 px-2">
        <Sparkles className="h-5 w-5 text-primary" />
        <span className="text-sm font-semibold tracking-tight">OmniVoice Web</span>
      </div>
      <nav className="flex flex-col gap-1">
        {items.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === href : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/20 text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto border-t border-border pt-3 text-xs text-muted-foreground">
        <p className="px-2">v0.1 · MVP</p>
      </div>
    </aside>
  );
}
