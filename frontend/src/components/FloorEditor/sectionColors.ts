/**
 * Presentation-only section color system.
 *
 * Colors are assigned deterministically by section id/number using a fixed
 * 7-color palette (palette[id % palette.length]).  Users may override a specific
 * section's color via localStorage, keyed as "sectionColor:<sectionId>".
 *
 * Stored colors must be one of the palette entries to keep the palette
 * consistent.  The helper returns a hex string.
 */

const PALETTE: readonly string[] = [
  '#ff6b1f', // orange (primary accent)
  '#f5b400', // yellow
  '#34c759', // green
  '#3b82f6', // blue
  '#a855f7', // purple
  '#ec4899', // pink
  '#9ca3af', // grey
];

export { PALETTE as SECTION_COLOR_PALETTE };

const STORAGE_KEY_PREFIX = 'sectionColor:';

/**
 * Returns the display color for a section.
 *
 * @param fallbackIndex  Index into the palette used when no localStorage override exists.
 *                       Typically the section's position in the list (idx).
 * @param sectionId  Numeric section id (from SectionDraft.id) — used as localStorage key.
 *                   Pass 0 / undefined if the section is a draft without a saved id.
 */
export function getSectionColor(fallbackIndex: number, sectionId?: number): string {
  if (sectionId !== undefined && sectionId > 0) {
    const stored = localStorage.getItem(`${STORAGE_KEY_PREFIX}${sectionId}`);
    if (stored && PALETTE.includes(stored)) {
      return stored;
    }
  }
  return PALETTE[Math.abs(fallbackIndex) % PALETTE.length];
}

/**
 * Persist a user-chosen color for a section.
 */
export function setSectionColor(sectionId: number, color: string): void {
  if (PALETTE.includes(color)) {
    localStorage.setItem(`${STORAGE_KEY_PREFIX}${sectionId}`, color);
  }
}

/**
 * Remove any override — section will revert to deterministic color.
 */
export function clearSectionColor(sectionId: number): void {
  localStorage.removeItem(`${STORAGE_KEY_PREFIX}${sectionId}`);
}
