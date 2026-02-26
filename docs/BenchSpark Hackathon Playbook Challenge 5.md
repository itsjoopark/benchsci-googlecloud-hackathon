### **Challenge 5**

## **From Wandering to Wisdom: Create a rich navigation experience for multi-hop scientific discovery that captures how humans actually explore complex knowledge**

**Challenge Statement**  
Build an interactive graph exploration system that lets scientists manually traverse multi-hop connections in biomedical knowledge graphs to discover, visualize, and validate complex relationships between biological entities (genes, diseases, drugs, pathways, proteins).

**The Problem**  
Scientists have access to millions of interconnected biomedical facts, but current tools function as "black boxes"—they return lists of papers or entities without showing how things connect. When a researcher asks "How does Gene X relate to Disease Y?", they need to see the reasoning path (Gene X → Protein A → Pathway B → Disease Y), not just a list of results. Without transparent, verifiable traversal paths, scientists cannot validate findings or build trust in AI-generated insights. This manual exploration is essential groundwork for future explainable AI systems.

**Your Task**  
Create a knowledge graph traversal interface that:  
✅ Lets users search for biomedical entities (genes, diseases, drugs, pathways)  
✅ Displays interactive graph visualizations showing immediate connections (1-hop neighbors)  
✅ Enables click-to-expand exploration allowing users to navigate 2-3 hops deep through the graph  
✅ Shows evidence for each connection including source papers, citations, and relevant text snippets  
✅ Tracks and displays the exploration path so users can see the full reasoning chain

**Suggested Datasets**  
*Primary*  
✅ PubMed Knowledge Graph (PKG)

*Secondary*  
✅Semantic Scholar (S2ORC)  
✅Open Research KG (ORKG)

---

**Suggested Acceptance Criteria**  
*Teams should define their own acceptance criteria and provide a rationale. Here is guidance:*

**Core Test Scenario**  
Your system should enable a scientist to complete this walkthrough:  
1\. Start with "BRCA1" (a gene)  
2\. See it connects to "Breast Cancer" (disease)  
3\. Explore further to see connected drugs and pathways  
4\. View the papers supporting each connection  
5\. Verify the biological logic of the complete path

*If a user can't complete this journey in your interface, revisit your approach.*

**Minimum Bar**

* Search for biomedical entities (genes, diseases, drugs, pathways) by name  
* Display immediate connections (1-hop neighbors) as an interactive graph visualization  
* Click-to-expand navigation allowing ≥2 hops deep  
* Each connection shows supporting evidence (source paper, citation, or text snippet)  
* The exploration path is tracked so users can see and retrace their reasoning chain  
* Complete the BRCA1 test scenario end-to-end

**Competitive (Pick ≥2)**

* Support multiple entity types in one view (e.g., gene → pathway → drug → disease in a single graph)  
* Filter or rank connections by evidence strength or recency  
* Handle a second test scenario beyond BRCA1 (e.g., start from a drug like "Imatinib" or a disease like "Alzheimer's")  
* Provide a summary view of the full path (e.g., "BRCA1 → DNA repair pathway → Breast Cancer → PARP inhibitors" with aggregated evidence)

**Stretch**

* Let users compare two exploration paths side-by-side (e.g., two different genes linked to the same disease)  
* Surface unexpected or non-obvious connections that a simple database lookup wouldn't reveal  
* Export the exploration path as a shareable, reproducible reasoning chain with citations


LLM usage is fine — document your approach. If using LLMs to generate connection summaries, validate that cited papers actually support the stated relationship.