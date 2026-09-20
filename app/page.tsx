import { InversionesDashboard } from "@/components/inversiones-dashboard";
import {
  SITE_DESCRIPTION,
  SITE_NAME,
  getInversionesIniciales,
  getSiteUrl,
} from "@/lib/site";

// Página estática regenerada cada hora. La ingesta corre cada 3 días, así que
// no hace falta más: las visitas pegan contra HTML ya armado.
export const revalidate = 3600;

export default async function Home() {
  // Este fetch pasa en el servidor, así que las inversiones viajan dentro del
  // HTML. Antes todo se cargaba en el cliente y el crawler recibía una página
  // vacía: 143 inversiones publicadas y ninguna indexable.
  const inicial = await getInversionesIniciales();
  const siteUrl = getSiteUrl();

  // Datos estructurados: le dicen a Google que esto es un listado de proyectos
  // de inversión y no una página suelta.
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: siteUrl,
    description: SITE_DESCRIPTION,
    inLanguage: "es-AR",
    ...(inicial?.data?.length
      ? {
          mainEntity: {
            "@type": "ItemList",
            name: "Inversiones privadas en Argentina",
            numberOfItems: inicial.total,
            itemListElement: inicial.data.map((inv, i) => ({
              "@type": "ListItem",
              position: i + 1,
              item: {
                "@type": "Project",
                name: inv.empresa,
                description: inv.descripcion,
                ...(inv.ubicacion
                  ? { location: { "@type": "Place", name: inv.ubicacion } }
                  : {}),
              },
            })),
          },
        }
      : {}),
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <InversionesDashboard
        inversionesIniciales={inicial?.data ?? []}
        totalInicial={inicial?.total ?? 0}
        hasMoreInicial={inicial?.hasMore ?? false}
      />
    </>
  );
}
