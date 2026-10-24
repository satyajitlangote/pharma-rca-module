/**
 * Client-side mirror of the backend evidence rule (utils/evidence.py):
 * a quote counts as "Supported" only if it exists (normalized) in the source
 * document text. Used when the USER edits an evidence quote.
 */
export function quoteInSource(quote, source) {
  if (!quote || !source) return false;
  const norm = (t) =>
    String(t)
      .toLowerCase()
      .replace(/[\u2018\u2019]/g, "'")
      .replace(/[\u201c\u201d]/g, '"')
      .replace(/[\u2013\u2014]/g, "-")
      .replace(/\s+/g, " ")
      .replace(/[.,;:!?"']+$/g, "")
      .trim();
  return norm(source).includes(norm(quote));
}
