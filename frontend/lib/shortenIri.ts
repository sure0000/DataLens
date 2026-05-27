const KNOWN_PREFIXES: Record<string, string> = {
  "https://datalens.local/ontology/": "dl:",
  "https://datalens.local/data/": "data:",
  "https://datalens.local/graph/": "graph:",
  "http://www.w3.org/2004/02/skos/core#": "skos:",
  "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
  "https://schema.org/": "schema:",
  "http://www.w3.org/2002/07/owl#": "owl:",
};

export function shortenIri(iri: string): string {
  if (!iri) return "—";
  for (const [ns, prefix] of Object.entries(KNOWN_PREFIXES)) {
    if (iri.startsWith(ns)) return iri.replace(ns, prefix);
    if (iri.startsWith(`<${ns}`)) return `<${iri.slice(1).replace(ns, prefix)}`;
  }
  if (iri.length > 72) return `${iri.slice(0, 36)}…${iri.slice(-24)}`;
  return iri;
}
