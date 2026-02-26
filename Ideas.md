- Use a model that's very good for agentic stuff. Give it tools to do a bunch of things for multi-hop reasoning
# Graph
- What should each node connect to?
- If a node is:
	- a gene: 
		- nucleotide sequence
		- location on chromosome
		- structure
		- transcript variants
		- gene variants (any known mutations, SNPs)
		- modulation effect (is increasing or decreasing it known to do anything in animals)
		- is it known to be druggable
		- any off-target effects from knocking/overexpressing it
		- does its protein have have defined druggable pockets or binding sites for small molecules?
		- gene expression (where is it in healthy vs diseased tissue)
		- which cell types in an organ express the gene
		- whether it is protein coding or not
		- list of proteins it encodes
		- drugs that are known to knock it out
		- drugs that are known to overexpress it
		- which datasets it's part of
		- which pathways does it participate in?
		- what other genes is it known to interact with?
		- whether cell painting data is avlbl for perturbations to it
	- a disease:
		- 
		- known drugs
	- a drug:
		- target
		- mechanism of action
		- type: NAMs, PAMs (benzos), etc.
		- efficacy
		- toxicity
		- known off-target toxicity
		- dose-response information
		- clinical trials information
		- known repurposes
		- combination therapies
		- business info (pharma company, etc.)
	- some of the above info can come from datasets, some may need to be pulled in real-time using a Search+RAG combo
- For each node:
	- provide grounding in the form of:
		- reference to data from public dataset
		- reference to paper from which information is lifted
- For each connection:
	- **MODEL AS A BIOLINK PREDICATE?**
	- show evidence via:
		- source papers, citations, and relevant text snippets
	- provide natural language description of exploration path ("could it be that the gene is in a different location in healthy vs diseased tissues? let me check if datasets, literature address that by doing an agentic/rag search")

# Interaction Model
- User searches for one of the following:
	- a specific gene (say BRCA1)
	- a specific disease (say Breast Cancer)
	- a specific drug (say Insulin)
	- a specific pathway (say Insulin Signaling)
- OR User enters natural language query?
- Show 1-hop deep connected nodes (just the basic information)
- user can click on any sister node to traverse deeper down that path (upto 3 hops deep)
- user can click on any connection to see natural language description (as above)
# UI
- "*For example, in creating figures for papers, biologists reporting on the interactions of particular proteins may be better off showing a focused neighbourhood around those specific proteins rather than providing a hairball. Similarly, if the users were experimenters, they would choose their corpora, design their tasks and pick layout methods based on these well-defined limits.*"
- score each connection strength / relevance (i.e. strength of reasoning or åvlbll evidence via thickness of edges)
	- scoring on the bassis of:
		- how many independent (non-inter-referencing) articles suport the claim or result
		- recency (maybe older is better since more vetted?)
		- citations? higher is better?
# Data
ORKG
S2ORC
PKG
Open Targets (evidence scoring)
DisGENET (for gene-disease associations)
Reactome (for pathways)
UniProt (protein infor)
# EDGES
- train agentic model to operate in entities, which could be:
	- 
- and predicates which would be biolink predicates such as:
	- [Biolink Model Documentation](https://biolink.github.io/biolink-model/#predicates-visualization)
	- [Understanding the Biolink Model - Biolink Model Documentation](https://biolink.github.io/biolink-model/understanding-the-model/)
# GRAPH types
- RDF graph
- Neo4j
- Cytoscape.js for frontend interactive canvas 
![[Pasted image 20260226001640.png]]
# Neo4j
