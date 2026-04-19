"use client";

import { motion } from "framer-motion";
import Image from "next/image";

const ctaVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.5,
      ease: [0.25, 0.46, 0.45, 0.94],
    },
  },
};

export function TelegramCta() {
  return (
    <motion.section
      variants={ctaVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-50px" }}
      aria-label="Unirse al canal de Telegram"
      className="my-6"
    >
      <a
        id="telegram-cta"
        href="https://t.me/inversiones_en_argentina"
        target="_blank"
        rel="noopener noreferrer"
        className="group flex items-center gap-3 p-3 md:p-4 rounded-md border border-border bg-card/60 hover:bg-card hover:border-[#74ACDF]/30 transition-all duration-300"
      >
        {/* Icon */}
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-[#2AABEE] to-[#229ED9] flex items-center justify-center">
          <Image
            src="/telegram-icon.png"
            alt=""
            width={18}
            height={18}
            className="rounded-full"
            aria-hidden="true"
          />
        </div>

        {/* Text */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground leading-tight">
            Unite al canal de Telegram
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Recibí cada nueva inversión al instante
          </p>
        </div>

        {/* Arrow */}
        <div className="flex-shrink-0" aria-hidden="true">
          <svg
            className="w-4 h-4 text-muted-foreground group-hover:text-[#2AABEE] group-hover:translate-x-0.5 transition-all duration-300"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3"
            />
          </svg>
        </div>
      </a>
    </motion.section>
  );
}
