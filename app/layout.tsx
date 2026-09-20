import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { MailPopover } from '@/components/mail-popover'
import { SITE_DESCRIPTION, SITE_NAME, getSiteUrl } from '@/lib/site'
import './globals.css'

// Las fuentes se exponen como variables CSS y se enganchan en <html>. Antes se
// instanciaban y no se aplicaban a nada: se descargaban en cada visita sin
// llegar a usarse nunca.
const geist = Geist({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-geist-sans',
})
const geistMono = Geist_Mono({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-geist-mono',
})

const siteUrl = getSiteUrl()

export const metadata: Metadata = {
  // metadataBase hace que las URLs relativas de OpenGraph se resuelvan solas.
  metadataBase: new URL(siteUrl),
  title: {
    default: `${SITE_NAME} — Agregador de inversiones privadas`,
    template: `%s | ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  authors: [{ name: "Iván Gómez Dell'Osa", url: 'https://www.linkedin.com/in/ivangomezdellosa/' }],
  creator: "Iván Gómez Dell'Osa",
  keywords: [
    'inversiones Argentina', 'inversión privada', 'RIGI', 'Vaca Muerta',
    'minería Argentina', 'litio', 'anuncios de inversión', 'proyectos aprobados',
  ],
  alternates: {
    canonical: '/',
  },
  openGraph: {
    type: 'website',
    locale: 'es_AR',
    url: siteUrl,
    siteName: SITE_NAME,
    title: `${SITE_NAME} — Agregador de inversiones privadas`,
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: 'summary_large_image',
    title: `${SITE_NAME} — Agregador de inversiones privadas`,
    description: SITE_DESCRIPTION,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, 'max-image-preview': 'large', 'max-snippet': -1 },
  },
  icons: {
    icon: '/favicon.ico',
    apple: '/apple-icon.png',
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="es" className={`${geist.variable} ${geistMono.variable}`}>
      <body className="font-sans antialiased">
        {children}
        <MailPopover />
        <Analytics />
      </body>
    </html>
  )
}
