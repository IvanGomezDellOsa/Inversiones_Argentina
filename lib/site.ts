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

export const PRODUCTION_URL = "https://inversionesargentina.com.ar";

/**
 * URL canónica del sitio.
 *
 * A propósito NO usa VERCEL_URL. Esa variable apunta al deployment que se está
 * construyendo, que todavía no sirve tráfico: el fetch del servidor fallaría
 * durante el build y la página quedaría prerenderizada vacía, justo lo que este
 * cambio viene a arreglar. Además, como canonical y como og:url hay que
 * publicar siempre el dominio de producción, nunca una URL de preview.
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
