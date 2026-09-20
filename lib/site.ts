/**
 * Configuración del sitio y carga de datos del lado del servidor.
 *
 * La página se renderizaba entera en el cliente: el HTML que recibía Google no
 * contenía ni una inversión. Para un agregador cuyo valor es ser encontrado,
 * eso significaba ser invisible. Acá vive el fetch que corre en el servidor
 * para que la primera pantalla venga con contenido en el HTML.
 */

import type { Inversion } from "@/components/inversion-card";

export const SITE_NAME = "Inversiones en Argentina";
export const SITE_DESCRIPTION =
  "Seguimiento cronológico de las inversiones privadas anunciadas y confirmadas en Argentina. " +
  "Datos de fuentes oficiales, medios especializados y el registro RIGI, actualizados automáticamente.";

/** URL canónica del sitio. En preview usa la que asigna Vercel. */
export function getSiteUrl(): string {
  const explicita = process.env.NEXT_PUBLIC_SITE_URL;
  if (explicita) return explicita.replace(/\/$/, "");
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return "https://inversionesargentina.com.ar";
}

export const PAGE_SIZE = 10;

export interface RespuestaInversiones {
  data: Inversion[];
  total: number;
  hasMore: boolean;
}

/**
 * Trae la primera página en el servidor. Si la API no responde devuelve null y
 * el cliente hace el fetch como antes: la página nunca queda rota por esto.
 */
export async function getInversionesIniciales(): Promise<RespuestaInversiones | null> {
  try {
    const res = await fetch(
      `${getSiteUrl()}/api/inversiones?limit=${PAGE_SIZE}&offset=0`,
      // Se revalida cada hora: la ingesta corre cada 3 días, así que no hace
      // falta más frecuencia, y así las visitas pegan contra una página estática.
      { next: { revalidate: 3600 } }
    );
    if (!res.ok) return null;
    return (await res.json()) as RespuestaInversiones;
  } catch {
    return null;
  }
}
