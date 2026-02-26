import type { Entity } from "../types";
import { ENTITY_COLORS } from "../types";
import "./EntityCard.css";

interface Props {
  entity: Entity;
}

function MetaRow({
  label,
  value,
}: {
  label: string;
  value?: string | number | string[];
}) {
  if (value === undefined || value === "") return null;
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    return (
      <div className="meta-row">
        <span className="meta-label">{label}</span>
        <span className="meta-value meta-aliases">
          {value.join(", ")}
        </span>
      </div>
    );
  }
  return (
    <div className="meta-row">
      <span className="meta-label">{label}</span>
      <span className="meta-value">{String(value)}</span>
    </div>
  );
}

function GeneCard({ entity }: { entity: Entity }) {
  const m = entity.metadata;
  return (
    <>
      <MetaRow label="Symbol" value={(m.symbol as string) ?? entity.name} />
      <MetaRow label="Full name" value={m.full_name as string} />
      <MetaRow label="NCBI Gene ID" value={(m.ncbi_gene_id as string) ?? entity.primaryId} />
      <MetaRow label="HGNC ID" value={m.hgnc_id as string} />
      <MetaRow label="Chromosome" value={m.chromosome as string} />
      <MetaRow label="Aliases" value={m.aliases as string[]} />
    </>
  );
}

function DiseaseCard({ entity }: { entity: Entity }) {
  const m = entity.metadata;
  return (
    <>
      <MetaRow label="Name" value={entity.name} />
      <MetaRow label="MONDO ID" value={(m.mondo_id as string) ?? entity.primaryId} />
      <MetaRow label="UMLS CUI" value={m.umls_cui as string} />
      <MetaRow label="ICD-10" value={m.icd10 as string} />
      <MetaRow label="Prevalence" value={m.prevalence as string} />
    </>
  );
}

function DrugCard({ entity }: { entity: Entity }) {
  const m = entity.metadata;
  return (
    <>
      <MetaRow label="Name" value={entity.name} />
      <MetaRow label="ChEMBL ID" value={(m.chembl_id as string) ?? entity.primaryId} />
      <MetaRow label="DrugBank ID" value={m.drugbank_id as string} />
      <MetaRow label="Mechanism" value={m.mechanism as string} />
      <MetaRow label="Approval status" value={m.approval_status as string} />
      <MetaRow label="Indication" value={m.indication as string} />
    </>
  );
}

function PathwayCard({ entity }: { entity: Entity }) {
  const m = entity.metadata;
  return (
    <>
      <MetaRow label="Name" value={entity.name} />
      <MetaRow label="Reactome ID" value={(m.reactome_id as string) ?? entity.primaryId} />
      <MetaRow label="Parent pathway" value={m.parent_pathway_name as string} />
      <MetaRow label="Species" value={m.species as string} />
      <MetaRow label="Reaction count" value={m.reaction_count as number} />
    </>
  );
}

function ProteinCard({ entity }: { entity: Entity }) {
  const m = entity.metadata;
  return (
    <>
      <MetaRow label="Name" value={entity.name} />
      <MetaRow label="UniProt ID" value={entity.primaryId} />
      <MetaRow label="Location" value={m.subcellularLocation as string} />
      {m.function && <p className="entity-summary">{String(m.function)}</p>}
    </>
  );
}

const CARD_MAP: Record<string, React.FC<{ entity: Entity }>> = {
  gene: GeneCard,
  disease: DiseaseCard,
  drug: DrugCard,
  pathway: PathwayCard,
  protein: ProteinCard,
};

export default function EntityCard({ entity }: Props) {
  const CardContent = CARD_MAP[entity.type] || GeneCard;
  const badgeColor = entity.color ?? ENTITY_COLORS[entity.type];

  return (
    <div className="entity-card">
      <div className="entity-card-header">
        <span
          className="entity-type-badge"
          style={{ background: badgeColor }}
        >
          {entity.type}
        </span>
        <h2 className="entity-card-name">{entity.name}</h2>
      </div>
      <div className="entity-card-body">
        <CardContent entity={entity} />
      </div>
    </div>
  );
}
