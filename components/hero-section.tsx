"use client";

import { motion } from "framer-motion";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.05,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.5,
      ease: [0.25, 0.46, 0.45, 0.94],
    },
  },
};

interface HeroSectionProps {
  videoSrc?: string;
}

export function HeroSection({ videoSrc }: HeroSectionProps) {
  return (
    <motion.header
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="relative pt-8 pb-10 md:pt-12 md:pb-14"
    >
      <div 
        className="absolute inset-0 -z-10 overflow-hidden"
        aria-hidden="true"
      >
        <div className="absolute -top-1/2 -right-1/4 w-[600px] h-[600px] rounded-full bg-[#74ACDF]/8 blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/4 w-[400px] h-[400px] rounded-full bg-[#74ACDF]/5 blur-3xl" />
      </div>

      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-8">
        <div className="flex flex-col gap-5 lg:max-w-xl text-[0.889em]">
          <motion.h1
            variants={itemVariants}
            className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-foreground text-balance leading-tight"
          >
            Inversiones en{" "}
            <span className="bg-gradient-to-r from-[#74ACDF] to-[#4A90C2] bg-clip-text text-transparent">
              Argentina
            </span>
          </motion.h1>

          <motion.p
            variants={itemVariants}
            className="text-lg md:text-xl text-muted-foreground leading-relaxed"
          >
            Seguimiento cronológico de inversiones privadas en el país.
          </motion.p>

          <motion.div
            variants={itemVariants}
            className="flex items-center gap-3 text-sm text-muted-foreground"
          >
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-secondary border border-border text-[12px] md:text-[14px]">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#74ACDF] opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[#74ACDF]"></span>
              </span>
              Actualizaciones semanales
            </span>
          </motion.div>
        </div>

        <motion.div
          variants={itemVariants}
          className="relative w-full lg:w-80 h-48 lg:h-52 rounded-lg overflow-hidden border border-border shadow-sm bg-gradient-to-br from-[#74ACDF] via-white to-[#74ACDF]"
        >
          {videoSrc ? (
            <video
              src={videoSrc}
              autoPlay
              loop
              muted
              playsInline
              className="w-full h-full object-cover"
              aria-label="Bandera argentina flameando"
            />
          ) : (
            <div className="w-full h-full flex flex-col" aria-label="Bandera de Argentina">
              {/* Representación visual de bandera (fallback) */}
              <div className="flex-1 bg-[#74ACDF]" />
              <div className="flex-1 bg-white flex items-center justify-center">
                <svg 
                  viewBox="0 0 64 64" 
                  className="w-12 h-12 text-[#F6B40E]"
                  aria-hidden="true"
                >
                  <circle cx="32" cy="32" r="10" fill="currentColor" />
                  {[...Array(16)].map((_, i) => (
                    <line
                      key={i}
                      x1="32"
                      y1="32"
                      x2={32 + 20 * Math.cos((i * Math.PI * 2) / 16)}
                      y2={32 + 20 * Math.sin((i * Math.PI * 2) / 16)}
                      stroke="currentColor"
                      strokeWidth={i % 2 === 0 ? "2" : "1"}
                      strokeLinecap="round"
                    />
                  ))}
                </svg>
              </div>
              <div className="flex-1 bg-[#74ACDF]" />
            </div>
          )}
          
          <div className="absolute inset-0 bg-gradient-to-t from-background/20 to-transparent pointer-events-none" />
        </motion.div>
      </div>

      <div className="mt-10 h-px bg-gradient-to-r from-transparent via-border to-transparent" />
    </motion.header>
  );
}
 