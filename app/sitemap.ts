import type { MetadataRoute } from 'next'
import { getSiteUrl } from '@/lib/site'

// El sitio no tenía sitemap: /sitemap.xml devolvía 404.
// Es una sola página (la cronología), así que el sitemap es corto, pero sirve
// para que Google conozca la URL canónica y la frecuencia de actualización.
export default function sitemap(): MetadataRoute.Sitemap {
  const siteUrl = getSiteUrl()
  return [
    {
      url: siteUrl,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 1,
    },
  ]
}
