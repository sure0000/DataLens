"use client";

import DomainFiveLayerBrowse from "./DomainFiveLayerBrowse";

type Props = {
  domainId: number;
};

export default function DomainOntologyWorkspace({ domainId }: Props) {
  return <DomainFiveLayerBrowse domainId={domainId} />;
}
