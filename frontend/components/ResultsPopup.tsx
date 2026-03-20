"use client";

import { useEffect, useCallback, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface ResultsPopupProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  accentColor?: string;
  children: React.ReactNode;
}

const easeOutExpo: [number, number, number, number] = [0.22, 1, 0.36, 1];

const overlayVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.3, ease: easeOutExpo },
  },
  exit: {
    opacity: 0,
    transition: { duration: 0.25, ease: easeOutExpo },
  },
};

const panelVariants = {
  hidden: {
    opacity: 0,
    scale: 0.94,
    y: 24,
    filter: "blur(8px)",
  },
  visible: {
    opacity: 1,
    scale: 1,
    y: 0,
    filter: "blur(0px)",
    transition: {
      duration: 0.4,
      ease: easeOutExpo,
      filter: { duration: 0.3 },
    },
  },
  exit: {
    opacity: 0,
    scale: 0.96,
    y: 12,
    filter: "blur(4px)",
    transition: {
      duration: 0.25,
      ease: easeOutExpo,
    },
  },
};

const headerVariants = {
  hidden: { opacity: 0, y: -12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: easeOutExpo, delay: 0.15 },
  },
};

export function ResultsPopup({
  isOpen,
  onClose,
  title,
  subtitle,
  accentColor = "rgba(124, 58, 237, 0.15)",
  children,
}: ResultsPopupProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      window.addEventListener("keydown", handleEscape);
      return () => window.removeEventListener("keydown", handleEscape);
    }
  }, [isOpen, handleEscape]);

  if (!mounted) return null;

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Overlay */}
          <motion.div
            key="popup-overlay"
            className="fixed inset-0 z-50"
            style={{ background: "rgba(0, 0, 0, 0.4)", backdropFilter: "blur(4px)" }}
            variants={overlayVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={onClose}
          />

          {/* Content panel */}
          <motion.div
            key="popup-panel"
            className="fixed inset-3 lg:inset-6 z-50 rounded-2xl overflow-hidden flex flex-col"
            variants={panelVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
          >
            {/* Background */}
            <div className="absolute inset-0 bg-background/97 backdrop-blur-xl border border-foreground/10 rounded-2xl" />

            {/* Decorative orb */}
            <motion.div
              className="absolute -top-20 -right-20 w-80 h-80 rounded-full blur-3xl pointer-events-none"
              style={{ background: accentColor }}
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 0.4, scale: 1, transition: { duration: 0.6, ease: easeOutExpo, delay: 0.2 } }}
            />

            {/* Noise overlay */}
            <div className="absolute inset-0 rounded-2xl noise-overlay pointer-events-none" />

            {/* Header */}
            <motion.div
              className="relative z-10 flex items-center justify-between px-6 lg:px-8 py-5 border-b border-foreground/5 shrink-0"
              variants={headerVariants}
              initial="hidden"
              animate="visible"
            >
              <div>
                <h2 className="text-xl lg:text-2xl font-display tracking-tight">{title}</h2>
                {subtitle && (
                  <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>
                )}
              </div>
              <motion.button
                onClick={onClose}
                className="p-2 rounded-full hover:bg-foreground/5 transition-colors text-muted-foreground hover:text-foreground"
                whileHover={{ scale: 1.1, rotate: 90 }}
                whileTap={{ scale: 0.9 }}
                transition={{ type: "spring", stiffness: 400, damping: 20 }}
              >
                <X className="h-5 w-5" />
              </motion.button>
            </motion.div>

            {/* Scroll content */}
            <div className="relative z-10 flex-1 overflow-y-auto px-6 lg:px-8 py-6">
              {children}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body
  );
}
