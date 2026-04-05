"use client";
import React from "react";

import { motion } from "framer-motion";

export interface Inversion {
  empresa: string;
  descripcion: string;
  monto_usd: number | null;
  fecha_anuncio: string;
  estado: "confirmada" | "anunciada" | "en_evaluacion";
  ubicacion: string | null;
  empleos: number | null;
}

interface InversionCardProps {
  inversion: Inversion;
  index: number;
}

const estadoConfig = {
  confirmada: {
    label: "Confirmada",
    className: "bg-success text-success-foreground",
  },
  anunciada: {
    label: "Anunciada",
    className: "bg-primary text-primary-foreground",
  },
  en_evaluacion: {
    label: "En evaluación",
    className: "bg-warning text-warning-foreground",
  },
};

function formatCurrency(amount: number): string {
  if (amount >= 1000000000) {
    return `USD ${(amount / 1000000000).toFixed(1).replace(".0", "")}B`;
  }
  if (amount >= 1000000) {
    return `USD ${(amount / 1000000).toFixed(0)}M`;
  }
  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

const MONTHS_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
];

function formatDate(dateString: string): string {
  const [year, month, day] = dateString.split("-").map(Number);
  return `${day} de ${MONTHS_ES[month - 1]} de ${year}`;
}

export function InversionCard({ inversion, index }: InversionCardProps) {
  const { empresa, descripcion, monto_usd, fecha_anuncio, estado, ubicacion, empleos } = inversion;
  const estadoInfo = estadoConfig[estado];

  return (
    <motion.article
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.4,
        delay: index * 0.08,
        ease: [0.25, 0.46, 0.45, 0.94],
      }}
      className="group relative"
    >
      <div className="flex gap-4 md:gap-6">
        <div className="flex flex-col items-center pt-1">
          <div className="w-3 h-3 rounded-full bg-primary border-2 border-background ring-4 ring-secondary" />
          <div className="w-0.5 flex-1 bg-border mt-2" />
        </div>

        <div className="flex-1 pb-8 md:pb-10">
          <time 
            dateTime={fecha_anuncio}
            className="text-sm text-muted-foreground font-medium"
          >
            {formatDate(fecha_anuncio)}
          </time>

          <div className="mt-3 bg-card border border-border rounded-lg p-5 md:p-6 shadow-sm hover:shadow-md hover:border-primary/30 transition-all duration-200">
            <div className="mb-3">
              <h3 className="text-lg md:text-xl font-semibold text-foreground leading-tight">
                {empresa}
              </h3>
            </div>

            <div className="flex flex-wrap gap-2 mb-4">
              <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold tracking-wide ${estadoInfo.className}`}>
                {estadoInfo.label}
              </span>
              
              {ubicacion && (
                <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold tracking-wide bg-secondary text-secondary-foreground">
                  {ubicacion}
                </span>
              )}

              {empleos !== null && (
                <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold tracking-wide bg-secondary text-secondary-foreground">
                  {empleos} empleos
                </span>
              )}
            </div>

            {monto_usd !== null && (
              <p className="text-2xl md:text-3xl font-bold tracking-tight text-foreground mb-3">
                {formatCurrency(monto_usd)}
              </p>
            )}

            <p className="text-muted-foreground leading-relaxed text-sm md:text-base">
              {descripcion}
            </p>
          </div>
        </div>
      </div>
    </motion.article>
  );
}
