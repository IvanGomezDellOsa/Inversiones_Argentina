"use client";

import { useState, useEffect, useCallback } from "react";
import { HeroSection } from "./hero-section";
import { TelegramCta } from "./telegram-cta";
import { SearchInput } from "./search-input";
import { InversionesGrid } from "./inversiones-grid";
import type { Inversion } from "./inversion-card";

const PAGE_SIZE = 10;

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

export function InversionesDashboard() {
  const [searchQuery, setSearchQuery] = useState("");
  const [inversiones, setInversiones] = useState<Inversion[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const debouncedQuery = useDebounce(searchQuery, 300);

  // Carga inicial y cuando cambia la búsqueda
  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setInversiones([]);
    setHasMore(false);
    setTotal(0);

    const fetchData = async () => {
      try {
        const params = new URLSearchParams({
          limit: String(PAGE_SIZE),
          offset: "0",
        });
        if (debouncedQuery.trim()) {
          params.set("q", debouncedQuery.trim());
        }

        const response = await fetch(`/api/inversiones?${params}`);
        if (!response.ok) throw new Error("Error en red");
        const json = await response.json();

        if (active) {
          setInversiones(json.data);
          setHasMore(json.hasMore);
          setTotal(json.total);
          setIsLoading(false);
        }
      } catch (error) {
        console.error("Error fetching inversiones:", error);
        if (active) {
          setInversiones([]);
          setHasMore(false);
          setTotal(0);
          setIsLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      active = false;
    };
  }, [debouncedQuery]);

  // Cargar más resultados
  const handleLoadMore = useCallback(async () => {
    if (isLoadingMore || !hasMore) return;
    setIsLoadingMore(true);

    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(inversiones.length),
      });
      if (debouncedQuery.trim()) {
        params.set("q", debouncedQuery.trim());
      }

      const response = await fetch(`/api/inversiones?${params}`);
      if (!response.ok) throw new Error("Error en red");
      const json = await response.json();

      setInversiones((prev) => [...prev, ...json.data]);
      setHasMore(json.hasMore);
      setTotal(json.total);
    } catch (error) {
      console.error("Error loading more inversiones:", error);
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore, hasMore, inversiones.length, debouncedQuery]);

  return (
    <div className="min-h-screen bg-background">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 pb-16">
        <HeroSection videoSrc="/bandera-argentina.mp4" />
        <TelegramCta />

        <section className="py-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border mb-8">
          <SearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Buscar empresa o sector..."
          />
          
          {debouncedQuery.trim() && !isLoading && (
            <p className="text-sm text-muted-foreground">
              {`${total} ${total === 1 ? "resultado" : "resultados"}`}
            </p>
          )}
        </section>

        <section aria-label="Cronología de inversiones">
          <h2 className="sr-only">Cronología de inversiones</h2>
          <InversionesGrid
            inversiones={inversiones}
            isLoading={isLoading}
            isLoadingMore={isLoadingMore}
            hasMore={hasMore}
            total={total}
            onLoadMore={handleLoadMore}
          />
        </section>
      </main>

      <footer className="border-t border-border py-8">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <p className="text-sm text-muted-foreground">
            Contactame en:{" "}
            <a 
              href="mailto:ivangomezdellosa@gmail.com"
              className="text-foreground hover:text-primary transition-colors underline underline-offset-2"
            >
              ivangomezdellosa@gmail.com
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}