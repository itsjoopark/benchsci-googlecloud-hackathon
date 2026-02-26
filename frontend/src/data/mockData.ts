import type { Entity, GraphEdge, EvidenceItem } from "../types";

export const MOCK_ENTITIES: Entity[] = [
  {
    id: "gene-brca1",
    name: "BRCA1",
    type: "gene",
    primaryId: "NCBI:672",
    metadata: {
      fullName: "BRCA1 DNA repair associated",
      organism: "Homo sapiens",
      uniprotId: "P38398",
      summary:
        "This gene encodes a nuclear phosphoprotein that plays a role in maintaining genomic stability. It also acts as a tumor suppressor.",
    },
  },
  {
    id: "pathway-hr",
    name: "Homologous recombination",
    type: "pathway",
    primaryId: "R-HSA-5693532",
    metadata: {
      species: "Homo sapiens",
      parentPathway: "DNA Repair",
      geneCount: 44,
    },
  },
  {
    id: "pathway-dna-repair",
    name: "DNA Repair",
    type: "pathway",
    primaryId: "R-HSA-73894",
    metadata: {
      species: "Homo sapiens",
      parentPathway: "DNA maintenance",
      geneCount: 180,
    },
  },
  {
    id: "disease-breast-cancer",
    name: "Breast cancer",
    type: "disease",
    primaryId: "UMLS:C0006142",
    metadata: {
      diseaseClass: "Neoplasm",
      associatedGeneCount: 1245,
    },
  },
  {
    id: "disease-ovarian-cancer",
    name: "Ovarian cancer",
    type: "disease",
    primaryId: "UMLS:C0029925",
    metadata: {
      diseaseClass: "Neoplasm",
      associatedGeneCount: 834,
    },
  },
  {
    id: "drug-olaparib",
    name: "Olaparib",
    type: "drug",
    primaryId: "CHEMBL521686",
    metadata: {
      mechanismOfAction: "PARP inhibitor",
      maxClinicalPhase: 4,
      molecularTarget: "PARP1, PARP2",
    },
  },
  {
    id: "protein-brca1",
    name: "BRCA1 protein",
    type: "protein",
    primaryId: "P38398",
    metadata: {
      function:
        "E3 ubiquitin-protein ligase that plays a central role in DNA repair by facilitating cellular response to DNA damage.",
      subcellularLocation: "Nucleus",
    },
  },
  {
    id: "gene-brca2",
    name: "BRCA2",
    type: "gene",
    primaryId: "NCBI:675",
    metadata: {
      fullName: "BRCA2 DNA repair associated",
      organism: "Homo sapiens",
      uniprotId: "P51587",
      summary:
        "Involved in the repair of chromosomal damage with an important role in the error-free repair of DNA double strand breaks.",
    },
  },
  {
    id: "protein-rad51",
    name: "RAD51",
    type: "protein",
    primaryId: "Q06609",
    metadata: {
      function:
        "Plays an important role in homologous strand exchange, a key step in DNA repair through homologous recombination.",
      subcellularLocation: "Nucleus",
    },
  },
];

export const MOCK_EDGES: GraphEdge[] = [
  {
    id: "edge-brca1-hr",
    source: "gene-brca1",
    target: "pathway-hr",
    predicate: "participates_in",
    score: 0.99,
    provenance: "curated",
    sourceDb: "reactome",
  },
  {
    id: "edge-brca1-dna-repair",
    source: "gene-brca1",
    target: "pathway-dna-repair",
    predicate: "participates_in",
    score: 0.95,
    provenance: "curated",
    sourceDb: "reactome",
  },
  {
    id: "edge-brca1-breast-cancer",
    source: "gene-brca1",
    target: "disease-breast-cancer",
    predicate: "gene_associated_with_condition",
    score: 0.95,
    provenance: "curated",
    sourceDb: "disgenet",
  },
  {
    id: "edge-brca1-ovarian-cancer",
    source: "gene-brca1",
    target: "disease-ovarian-cancer",
    predicate: "gene_associated_with_condition",
    score: 0.91,
    provenance: "literature",
    sourceDb: "disgenet",
  },
  {
    id: "edge-olaparib-breast-cancer",
    source: "drug-olaparib",
    target: "disease-breast-cancer",
    predicate: "treats",
    score: 0.88,
    provenance: "curated",
    sourceDb: "chembl",
  },
  {
    id: "edge-olaparib-brca1",
    source: "drug-olaparib",
    target: "gene-brca1",
    predicate: "has_target",
    score: 0.72,
    provenance: "literature",
    sourceDb: "chembl",
  },
  {
    id: "edge-brca1-protein",
    source: "gene-brca1",
    target: "protein-brca1",
    predicate: "encodes",
    provenance: "curated",
    sourceDb: "uniprot",
  },
  {
    id: "edge-brca1-brca2",
    source: "gene-brca1",
    target: "gene-brca2",
    predicate: "functionally_interacts_with",
    score: 0.97,
    provenance: "curated",
    sourceDb: "reactome",
  },
  {
    id: "edge-brca2-hr",
    source: "gene-brca2",
    target: "pathway-hr",
    predicate: "participates_in",
    score: 0.99,
    provenance: "curated",
    sourceDb: "reactome",
  },
  {
    id: "edge-protein-rad51",
    source: "protein-brca1",
    target: "protein-rad51",
    predicate: "interacts_with",
    score: 0.94,
    provenance: "curated",
    sourceDb: "reactome",
  },
  {
    id: "edge-hr-dna-repair",
    source: "pathway-hr",
    target: "pathway-dna-repair",
    predicate: "subclass_of",
    provenance: "curated",
    sourceDb: "reactome",
  },
];

export const MOCK_EVIDENCE: Record<string, EvidenceItem[]> = {
  "edge-brca1-breast-cancer": [
    {
      id: "ev-1",
      pmid: "20301425",
      title:
        "Average risks of breast and ovarian cancer associated with BRCA1 or BRCA2 mutations detected in case series unselected for family history",
      year: 2003,
      snippet:
        "BRCA1 mutation carriers had a 65% cumulative risk of breast cancer by age 70. These findings confirm that BRCA1 mutations are associated with a substantially elevated risk.",
      source: "PubMed",
      sourceDb: "disgenet",
    },
    {
      id: "ev-2",
      pmid: "17416853",
      title:
        "BRCA1 and BRCA2 mutations in breast cancer patients from Saudi Arabia",
      year: 2007,
      snippet:
        "Both BRCA1 and BRCA2 are tumor-suppressor genes involved in DNA repair. Mutations lead to defective homologous recombination and increased breast cancer susceptibility.",
      source: "PubMed",
      sourceDb: "disgenet",
    },
    {
      id: "ev-3",
      pmid: "29446767",
      title:
        "Associations between BRCA1 mutations and breast cancer risk: a meta-analysis",
      year: 2018,
      snippet:
        "The DisGeNET curated score for BRCA1-breast cancer association is 0.95, based on 487 supporting publications and multiple curated databases.",
      source: "DisGeNET",
      sourceDb: "disgenet",
    },
  ],
  "edge-brca1-hr": [
    {
      id: "ev-4",
      pmid: "21145460",
      title:
        "BRCA1 promotes homologous recombination by stimulating RAD51 nucleoprotein filament formation",
      year: 2010,
      snippet:
        "BRCA1 directly participates in homologous recombination repair by facilitating RAD51 loading onto single-stranded DNA at sites of DNA double-strand breaks.",
      source: "Reactome",
      sourceDb: "reactome",
    },
  ],
  "edge-olaparib-breast-cancer": [
    {
      id: "ev-5",
      pmid: "28578601",
      title:
        "Olaparib for metastatic breast cancer in patients with a germline BRCA mutation (OlympiAD trial)",
      year: 2017,
      snippet:
        "Olaparib monotherapy provided a significant benefit over standard therapy in patients with HER2-negative metastatic breast cancer and a germline BRCA mutation.",
      source: "PubMed",
      sourceDb: "chembl",
    },
    {
      id: "ev-6",
      pmid: "29863451",
      title: "Olaparib tablets as maintenance therapy in patients with platinum-sensitive, relapsed ovarian cancer and a BRCA1/2 mutation (SOLO2 trial)",
      year: 2018,
      snippet:
        "PARP inhibition with olaparib exploits the synthetic lethal interaction between PARP inhibition and BRCA deficiency in tumor cells.",
      source: "PubMed",
      sourceDb: "chembl",
    },
  ],
  "edge-olaparib-brca1": [
    {
      id: "ev-7",
      pmid: "16912185",
      title: "Targeting the DNA repair defect in BRCA mutant cells as a therapeutic strategy",
      year: 2005,
      snippet:
        "PARP inhibitors, including olaparib, exploit the concept of synthetic lethality — BRCA1-deficient cells cannot repair DNA damage when PARP activity is also blocked.",
      source: "PubMed",
      sourceDb: "chembl",
    },
  ],
  "edge-brca1-brca2": [
    {
      id: "ev-8",
      pmid: "24145185",
      title: "BRCA1 and BRCA2 as molecular targets for phytochemicals in breast and ovarian cancers",
      year: 2013,
      snippet:
        "BRCA1 and BRCA2 interact as part of the BRCA1-PALB2-BRCA2 complex, which is essential for homologous recombination repair of DNA double-strand breaks.",
      source: "Reactome",
      sourceDb: "reactome",
    },
  ],
};

export const MOCK_EXPANDED_NEIGHBORS: Record<string, { entities: Entity[]; edges: GraphEdge[] }> = {
  "disease-breast-cancer": {
    entities: [
      {
        id: "drug-trastuzumab",
        name: "Trastuzumab",
        type: "drug",
        primaryId: "CHEMBL1201585",
        metadata: {
          mechanismOfAction: "HER2 inhibitor",
          maxClinicalPhase: 4,
          molecularTarget: "ERBB2",
        },
      },
      {
        id: "gene-tp53",
        name: "TP53",
        type: "gene",
        primaryId: "NCBI:7157",
        metadata: {
          fullName: "Tumor protein p53",
          organism: "Homo sapiens",
          summary: "Acts as a tumor suppressor in many tumor types.",
        },
      },
    ],
    edges: [
      {
        id: "edge-trastuzumab-breast",
        source: "drug-trastuzumab",
        target: "disease-breast-cancer",
        predicate: "treats",
        score: 0.92,
        provenance: "curated",
        sourceDb: "chembl",
      },
      {
        id: "edge-tp53-breast",
        source: "gene-tp53",
        target: "disease-breast-cancer",
        predicate: "gene_associated_with_condition",
        score: 0.89,
        provenance: "curated",
        sourceDb: "disgenet",
      },
    ],
  },
  "pathway-hr": {
    entities: [
      {
        id: "gene-palb2",
        name: "PALB2",
        type: "gene",
        primaryId: "NCBI:79728",
        metadata: {
          fullName: "Partner and localizer of BRCA2",
          organism: "Homo sapiens",
          summary: "Encodes a protein that functions in genome maintenance, specifically in the homologous recombination pathway.",
        },
      },
    ],
    edges: [
      {
        id: "edge-palb2-hr",
        source: "gene-palb2",
        target: "pathway-hr",
        predicate: "participates_in",
        score: 0.96,
        provenance: "curated",
        sourceDb: "reactome",
      },
    ],
  },
};

export function getEntityById(id: string): Entity | undefined {
  const all = [
    ...MOCK_ENTITIES,
    ...Object.values(MOCK_EXPANDED_NEIGHBORS).flatMap((n) => n.entities),
  ];
  return all.find((e) => e.id === id);
}
