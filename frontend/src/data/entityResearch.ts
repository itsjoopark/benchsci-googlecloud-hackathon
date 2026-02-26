export interface EntityResearch {
  overview: string;
  clinicalRelevance: string[];
}

const ENTITY_RESEARCH: Record<string, EntityResearch> = {
  "672": {
    overview:
      "BRCA1 plays a role in DNA repair, genomic stability, cell cycle checkpoint control, and chromatin remodeling. It acts as a 'caretaker' of the genome, forming a complex with BARD1. Mutations in BRCA1 lead to loss of repair capacity and increased risk of malignant transformation.",
    clinicalRelevance: [
      "Enhanced screening — more frequent mammograms, MRIs",
      "Prophylactic surgeries — mastectomy, oophorectomy",
      "Targeted therapies — PARP inhibitors, drugs that exploit the DNA repair deficiency in BRCA1-mutant cancer cells, effectively using the tumor's own weakness against it",
    ],
  },
  "675": {
    overview:
      "BRCA2 is involved in the repair of chromosomal damage with an important role in the error-free repair of DNA double-strand breaks via homologous recombination. It forms a complex with BRCA1 and PALB2, essential for RAD51-mediated strand invasion.",
    clinicalRelevance: [
      "Testing for BRCA2 mutations is standard for individuals with strong family histories of breast or ovarian cancer",
      "PARP inhibitors (e.g., olaparib) show efficacy in BRCA2-mutant tumors via synthetic lethality",
      "Prophylactic measures similar to BRCA1 carriers",
    ],
  },
  "MONDO:0007254": {
    overview:
      "Breast cancer is one of the most common malignancies worldwide. It is a heterogeneous disease with multiple molecular subtypes. Strong genetic risk factors include BRCA1 and BRCA2 mutations.",
    clinicalRelevance: [
      "Screening recommendations vary by risk level and genetic status",
      "Treatment options include surgery, chemotherapy, radiation, and targeted therapies",
      "PARP inhibitors approved for BRCA-mutated metastatic breast cancer",
    ],
  },
  "CHEMBL:4297": {
    overview:
      "Olaparib is a PARP inhibitor that exploits synthetic lethality in BRCA-deficient cells. It blocks PARP-mediated DNA repair, and in cells lacking homologous recombination (e.g., BRCA1/2 mutant), this leads to cell death.",
    clinicalRelevance: [
      "FDA approved for BRCA-mutated ovarian, breast, and prostate cancer",
      "Maintenance therapy in platinum-sensitive recurrent ovarian cancer",
      "First-line maintenance in germline BRCA-mutated advanced ovarian cancer",
    ],
  },
  "R-HSA-5693538": {
    overview:
      "Homologous DNA repair is a pathway that repairs double-strand DNA breaks using a homologous template. BRCA1, BRCA2, and RAD51 are key players. Defects in this pathway increase cancer susceptibility.",
    clinicalRelevance: [
      "BRCA1/2 mutations impair homologous recombination",
      "PARP inhibitors target the backup repair pathway, causing synthetic lethality in HR-deficient cells",
    ],
  },
  "5888": {
    overview:
      "RAD51 is a recombinase that catalyzes strand invasion during homologous recombination. It is recruited to DNA damage sites by BRCA1 and BRCA2. RAD51 foci formation is a hallmark of functional HR repair.",
    clinicalRelevance: [
      "RAD51 foci assays can indicate HR proficiency",
      "RAD51 inhibitors are under investigation for cancer therapy",
    ],
  },
};

export function getEntityResearch(entityId: string): EntityResearch | null {
  return ENTITY_RESEARCH[entityId] ?? null;
}
