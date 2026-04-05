"use client";

import { useState, useMemo, useEffect } from "react";
import { HeroSection } from "./hero-section";
import { SearchInput } from "./search-input";
import { InversionesGrid } from "./inversiones-grid";
import type { Inversion } from "./inversion-card";



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
  const debouncedQuery = useDebounce(searchQuery, 300);

  useEffect(() => {
    let active = true;
    setIsLoading(true);

    const fetchData = async () => {
      try {
        const url = debouncedQuery.trim() 
            ? `/api/inversiones?q=${encodeURIComponent(debouncedQuery.trim())}` 
            : "/api/inversiones";
        
        const response = await fetch(url);
        if (!response.ok) throw new Error("Error en red");
        const data = await response.json();
        
        if (active) {
          setInversiones(data);
          setIsLoading(false);
        }
      } catch (error) {
        console.error("Error fetching inversiones:", error);
        if (active) {
          setInversiones([]);
          setIsLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      active = false;
    };
  }, [debouncedQuery]);

  return (
    <div className="min-h-screen bg-background">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 pb-16">
        <HeroSection videoSrc="/bandera-argentina.mp4" />

        <section className="py-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border mb-8">
          <SearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Buscar empresa o sector..."
          />
          
          {debouncedQuery.trim() && !isLoading && (
            <p className="text-sm text-muted-foreground">
              {`${inversiones.length} ${inversiones.length === 1 ? "resultado" : "resultados"}`}
            </p>
          )}
        </section>

        <section aria-label="Cronología de inversiones">
          <h2 className="sr-only">Cronología de inversiones</h2>
          <InversionesGrid
            inversiones={inversiones}
            isLoading={isLoading}
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
 