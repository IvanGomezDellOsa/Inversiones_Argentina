"use client";

import { useState, useEffect, useRef, useCallback } from "react";

const SITE_URL = "https://inversionesargentina.com.ar";

export function ShareButton() {
  const [open, setOpen] = useState(false);
  const [toastVisible, setToastVisible] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        close();
      }
    };
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, [close]);

  const shareX = () => {
    window.open(
      `https://x.com/intent/tweet?url=${encodeURIComponent(SITE_URL)}`,
      "_blank",
      "noopener,noreferrer"
    );
    close();
  };

  const copyLink = () => {
    navigator.clipboard.writeText(SITE_URL).then(() => {
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 2000);
    });
    close();
  };

  return (
    <>
      <div ref={wrapRef} className="relative flex items-center">
        <button
          type="button"
          aria-expanded={open}
          aria-haspopup="true"
          onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground bg-muted border border-border px-4 py-1.5 rounded-full font-medium cursor-pointer whitespace-nowrap transition-colors hover:text-foreground hover:border-foreground/30"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
          Compartir web
        </button>

        {open && (
          <div className="absolute bottom-full mb-2 right-0 min-w-[172px] bg-popover border border-border rounded-xl p-1 z-50 shadow-xl">
            <button
              type="button"
              onClick={shareX}
              className="flex items-center gap-2 w-full px-3 py-2.5 text-sm text-foreground bg-transparent border-none rounded-lg cursor-pointer text-left transition-colors hover:bg-muted"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.746l7.73-8.835L2.25 2.25H8.08l4.253 5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
              </svg>
              Compartir en X
            </button>
            <button
              type="button"
              onClick={copyLink}
              className="flex items-center gap-2 w-full px-3 py-2.5 text-sm text-foreground bg-transparent border-none rounded-lg cursor-pointer text-left transition-colors hover:bg-muted"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              Copiar link
            </button>
          </div>
        )}
      </div>

      {toastVisible && (
        <div className="fixed bottom-6 right-6 z-50 bg-popover border border-border text-foreground px-4 py-3 rounded-xl text-sm font-medium shadow-xl">
          Link copiado
        </div>
      )}
    </>
  );
}
