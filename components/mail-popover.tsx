"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";

interface PopoverState {
  email: string;
  href: string;
  trigger: HTMLElement | null;
}

export function MailPopover() {
  const [state, setState] = useState<PopoverState | null>(null);
  const copyBtnRef = useRef<HTMLButtonElement>(null);
  const stateRef = useRef<PopoverState | null>(null);
  stateRef.current = state;

  const cerrar = useCallback(() => {
    stateRef.current?.trigger?.focus();
    setState(null);
  }, []);

  useEffect(() => {
    if (window.matchMedia("(any-pointer: coarse)").matches) return;

    const handleClick = (e: MouseEvent) => {
      const a = (e.target as Element).closest?.('a[href^="mailto:"]') as HTMLAnchorElement | null;
      if (!a) return;
      e.preventDefault();
      const href = a.getAttribute("href") ?? "";
      const email = href.replace(/^mailto:/, "").split("?")[0];
      setState({ email, href, trigger: a });
    };

    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, []);

  useEffect(() => {
    if (!state) return;
    copyBtnRef.current?.focus();
    const handleKey = (e: KeyboardEvent) => { if (e.key === "Escape") cerrar(); };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [state, cerrar]);

  if (!state) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(state.email).then(
      () => {
        if (copyBtnRef.current) copyBtnRef.current.textContent = "Copiado ✓";
        setTimeout(cerrar, 900);
      },
      () => {
        if (copyBtnRef.current) copyBtnRef.current.textContent = "No se pudo copiar";
      }
    );
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-5 bg-black/60"
      onMouseDown={(e) => { if (e.target === e.currentTarget) cerrar(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Contacto por email"
        className="relative w-full max-w-[420px] bg-popover border border-border rounded-xl px-6 pt-6 pb-5 shadow-2xl"
      >
        <button
          type="button"
          aria-label="Cerrar"
          onClick={cerrar}
          className="absolute top-2 right-2.5 text-muted-foreground hover:text-foreground text-2xl leading-none px-1.5 py-0.5 bg-transparent border-none cursor-pointer transition-colors"
        >
          ×
        </button>
        <div className="text-muted-foreground text-xs uppercase tracking-widest font-semibold mb-1.5">
          Contacto
        </div>
        <div className="text-foreground font-semibold text-base break-all select-all mb-4">
          {state.email}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            ref={copyBtnRef}
            type="button"
            onClick={handleCopy}
            className="bg-[#74ACDF] text-black border-none rounded-lg px-4 py-2 text-sm font-semibold cursor-pointer hover:bg-[#5a96cf] transition-colors"
          >
            Copiar email
          </button>
          <a
            href={state.href}
            className="text-muted-foreground text-sm underline underline-offset-2 hover:text-foreground transition-colors"
          >
            Abrir en tu app de correo
          </a>
        </div>
      </div>
    </div>,
    document.body
  );
}
