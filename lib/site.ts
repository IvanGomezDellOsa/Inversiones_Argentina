/**
 * Configuración del sitio y carga de datos del lado del servidor.
 *
 * La página se renderizaba entera en el cliente, así que el HTML que recibía
 * Google no contenía ni una inversión. Acá vive el fetch del servidor.
 */

import type { Inversion } from "@/components/inversion-card";

export const SITE_NAME = "Inversiones en Argentina";
export const SITE_DESCRIPTION =
  "Seguimiento cronológico de las inversiones privadas anunciadas y confirmadas en Argentina. " +
  "Datos de fuentes oficiales, medios especializados y el registro RIGI, actualizados automáticamente.";

export const PRODUCTION_URL = "https://inversionesargentina.com.ar";

/**
 * URL canónica. A propósito no usa VERCEL_URL: apunta al deployment que se está
 * construyendo y todavía no sirve tráfico, así que el fetch fallaría durante el
 * build. Además el canonical debe ser siempre el dominio de producción.
 */
export function getSiteUrl(): string {
  const explicita = process.env.NEXT_PUBLIC_SITE_URL;
  if (explicita) return explicita.replace(/\/$/, "");
  return PRODUCTION_URL;
}

export const PAGE_SIZE = 10;

export interface RespuestaInversiones {
  data: Inversion[];
  total: number;
  hasMore: boolean;
}

/** Primera página desde el servidor. Si la API no responde, el cliente reintenta. */
export async function getInversionesIniciales(): Promise<RespuestaInversiones | null> {
  try {
    const res = await fetch(
      `${getSiteUrl()}/api/inversiones?limit=${PAGE_SIZE}&offset=0`,
      // La ingesta corre cada 3 días: revalidar por hora sobra.
      { next: { revalidate: 3600 } }
    );
    if (!res.ok) return null;
    return (await res.json()) as RespuestaInversiones;
  } catch {
    return null;
  }
}
