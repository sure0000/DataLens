const KNOWN_PREFIXES: Record<string, string> = {
  "https://datalens.local/ontology/": "dl:",
  "https://datalens.local/data/": "data:",
  "https://datalens.local/graph/": "graph:",
  "http://www.w3.org/2004/02/skos/core#": "skos:",
  "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
  "https://schema.org/": "schema:",
  "http://www.w3.org/2002/07/owl#": "owl:",
};

/** Full IRI → shortened prefix form (e.g. "https://datalens.local/ontology/BusinessTerm" → "dl:BusinessTerm") */
export function shortenIri(iri: string): string {
  if (!iri) return "—";
  for (const [ns, prefix] of Object.entries(KNOWN_PREFIXES)) {
    if (iri.startsWith(ns)) return iri.replace(ns, prefix);
    if (iri.startsWith(`<${ns}`)) return `<${iri.slice(1).replace(ns, prefix)}`;
  }
  if (iri.length > 72) return `${iri.slice(0, 36)}…${iri.slice(-24)}`;
  return iri;
}

/**
 * Shortened IRI → human-readable label.
 * Falls back to shortenIri() if no label mapping exists.
 * Accepts both full IRIs and already-shortened forms.
 */
export function labelForIri(iri: string, labelMap: Record<string, string>): string {
  const short = shortenIri(iri);
  // strip angle brackets for lookup
  const clean = short.startsWith("<") ? short.slice(1, -1) : short;
  return labelMap[clean] || labelMap[iri] || short;
}

/**
 * Given a shortened predicate IRI (e.g. "dl:dependsOn"), return the
 * human-readable Chinese label if known, otherwise the local name.
 */
export function humanPredicateLabel(predicateIri: string): string {
  const short = shortenIri(predicateIri);
  const localName = short.includes(":") ? short.split(":").pop() || short : short;
  return localName;
}
