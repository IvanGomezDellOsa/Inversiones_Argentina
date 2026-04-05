"use client";
import React from "react";

import { motion } from "framer-motion";
import { InversionCard, type Inversion } from "./inversion-card";
import { SearchX } from "lucide-react";

interface InversionesGridProps {
  inversiones: Inversion[];
  isLoading?: boolean;
}

export function InversionesGrid({
  inversiones,
  isLoading = false,
}: InversionesGridProps) {
  if (isLoading) {
    return (
      <div className="space-y-6">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="flex gap-4 md:gap-6">
            <div className="flex flex-col items-center pt-1">
              <div className="w-3 h-3 rounded-full bg-muted animate-pulse" />
              <div className="w-0.5 flex-1 bg-border mt-2" />
            </div>
            <div className="flex-1 pb-8">
              <div className="h-4 w-32 bg-muted rounded animate-pulse mb-3" />
              <div className="bg-card border border-border rounded-lg p-5 md:p-6">
                <div className="flex justify-between items-start mb-3">
                  <div className="h-6 w-40 bg-muted rounded animate-pulse" />
                  <div className="h-6 w-24 bg-muted rounded-full animate-pulse" />
                </div>
                <div className="h-8 w-32 bg-muted rounded animate-pulse mb-3" />
                <div className="space-y-2">
                  <div className="h-4 w-full bg-muted rounded animate-pulse" />
                  <div className="h-4 w-5/6 bg-muted rounded animate-pulse" />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (inversiones.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex flex-col items-center justify-center py-16 px-4"
      >
        <div className="w-14 h-14 rounded-full bg-muted flex items-center justify-center mb-4">
          <SearchX className="w-7 h-7 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-2">
          No se encontraron inversiones
        </h3>
        <p className="text-muted-foreground text-center max-w-md text-sm">
          Probá ajustando tu búsqueda o esperá a que se agreguen nuevas inversiones.
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="relative"
    >
      {inversiones.map((inversion, index) => (
        <InversionCard
          key={`${inversion.empresa}-${inversion.fecha_anuncio}`}
          inversion={inversion}
          index={index}
        />
      ))}
    </motion.div>
  );
}
