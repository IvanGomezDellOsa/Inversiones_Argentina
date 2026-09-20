import type { MetadataRoute } from 'next'
import { getSiteUrl } from '@/lib/site'

// El sitio no tenía robots.txt: /robots.txt devolvía 404.
export default function robots(): MetadataRoute.Robots {
  const siteUrl = getSiteUrl()
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        // La API es para el frontend; que no se indexe el JSON crudo.
        disallow: ['/api/'],
      },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
  }
}
