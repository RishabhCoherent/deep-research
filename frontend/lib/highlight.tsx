import React from "react";

/**
 * Highlight data points (numbers, percentages, currency, years) in text.
 * Returns a React fragment with styled spans for matched patterns.
 */
export function highlightDataPoints(text: string): React.ReactNode {
  // Patterns to highlight — order matters (more specific first)
  const patterns = [
    // Currency amounts: $4.2B, $108/kWh, USD 150 billion, etc.
    {
      regex: /(?:USD?\s*|€|£|\$)\s*[\d,.]+\s*(?:billion|million|trillion|B|M|T|bn|mn)?(?:\s*(?:per|\/)\s*\w+)?/gi,
      className: "evidence-highlight-currency",
    },
    // Percentages: 18%, 28.72%, -8%
    {
      regex: /[-+]?\d+(?:\.\d+)?%/g,
      className: "evidence-highlight-percent",
    },
    // Years: 2023, 2024, 2025, 2026, Q1 2025
    {
      regex: /(?:Q[1-4]\s+)?20[2-3]\d/g,
      className: "evidence-highlight-year",
    },
  ];

  // Build a combined regex with named groups
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;

  while (remaining.length > 0) {
    let earliest: { index: number; match: string; className: string } | null = null;

    for (const { regex, className } of patterns) {
      // Reset regex lastIndex
      const re = new RegExp(regex.source, regex.flags);
      const m = re.exec(remaining);
      if (m && (earliest === null || m.index < earliest.index)) {
        earliest = { index: m.index, match: m[0], className };
      }
    }

    if (!earliest) {
      parts.push(remaining);
      break;
    }

    // Text before the match
    if (earliest.index > 0) {
      parts.push(remaining.slice(0, earliest.index));
    }

    // The highlighted match
    parts.push(
      <span key={key++} className={earliest.className}>
        {earliest.match}
      </span>
    );

    remaining = remaining.slice(earliest.index + earliest.match.length);
  }

  return <>{parts}</>;
}
