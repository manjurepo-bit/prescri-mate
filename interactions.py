import networkx as nx

def build_interaction_graph():
    """Build a NetworkX graph containing common drug-drug interactions."""
    G = nx.Graph()
    
    # Define drug nodes (Generic names)
    drugs = [
        "paracetamol", "ibuprofen", "aspirin", "warfarin", "metformin",
        "contrast dye", "lisinopril", "spironolactone", "atorvastatin",
        "clarithromycin", "sildenafil", "nitroglycerin", "amoxicillin",
        "methotrexate", "digoxin", "furosemide", "ciprofloxacin",
        "calcium", "clopidogrel", "omeprazole", "levothyroxine",
        "iron supplements", "alcohol", "potassium supplements"
    ]
    
    for drug in drugs:
        G.add_node(drug)
        
    # Add interaction edges with metadata (severity and explanation)
    interactions = [
        ("paracetamol", "alcohol", {
            "severity": "Major",
            "description": "Combining Paracetamol with alcohol increases the risk of severe liver toxicity/damage."
        }),
        ("ibuprofen", "aspirin", {
            "severity": "Moderate",
            "description": "Ibuprofen can reduce the blood-thinning effect of low-dose Aspirin, and the combination increases stomach irritation and bleeding risk."
        }),
        ("warfarin", "aspirin", {
            "severity": "Major",
            "description": "Both are blood thinners. Using them together significantly increases the risk of internal bleeding."
        }),
        ("metformin", "contrast dye", {
            "severity": "Major",
            "description": "Iodine contrast dyes used in medical scans can temporarily impair kidney function, increasing metformin build-up and causing dangerous lactic acidosis."
        }),
        ("lisinopril", "spironolactone", {
            "severity": "Moderate",
            "description": "Both medications conserve potassium. Combining them can raise blood potassium levels to dangerous levels (hyperkalemia)."
        }),
        ("lisinopril", "potassium supplements", {
            "severity": "Major",
            "description": "Lisinopril increases potassium levels. Taking potassium supplements with it can lead to severe hyperkalemia, affecting heart rhythm."
        }),
        ("atorvastatin", "clarithromycin", {
            "severity": "Major",
            "description": "Clarithromycin blocks the breakdown of Atorvastatin, significantly increasing its blood concentration and raising the risk of severe muscle damage (rhabdomyolysis)."
        }),
        ("sildenafil", "nitroglycerin", {
            "severity": "Major",
            "description": "Nitroglycerin combined with Sildenafil can cause a severe, sudden, and life-threatening drop in blood pressure."
        }),
        ("amoxicillin", "methotrexate", {
            "severity": "Moderate",
            "description": "Amoxicillin reduces the kidney's excretion of methotrexate, potentially raising methotrexate levels and leading to dangerous toxicity."
        }),
        ("digoxin", "furosemide", {
            "severity": "Moderate",
            "description": "Furosemide is a diuretic that can cause low potassium. Low potassium increases the risk of Digoxin toxicity, causing heart arrhythmias."
        }),
        ("ciprofloxacin", "calcium", {
            "severity": "Moderate",
            "description": "Calcium (in dairy or antacids) binds to Ciprofloxacin, reducing its absorption and effectiveness. Take Ciprofloxacin 2 hours before or 6 hours after calcium products."
        }),
        ("clopidogrel", "omeprazole", {
            "severity": "Moderate",
            "description": "Omeprazole inhibits the enzyme that activates Clopidogrel, making Clopidogrel less effective and increasing the risk of blood clots."
        }),
        ("levothyroxine", "iron supplements", {
            "severity": "Moderate",
            "description": "Iron supplements bind to Levothyroxine in the stomach, reducing its absorption. Space them out by at least 4 hours."
        }),
        ("spironolactone", "potassium supplements", {
            "severity": "Major",
            "description": "Spironolactone prevents potassium loss. Taking potassium supplements alongside it can result in dangerously high blood potassium levels."
        }),
        ("ibuprofen", "lisinopril", {
            "severity": "Moderate",
            "description": "Ibuprofen can decrease the blood-pressure lowering effectiveness of Lisinopril and increase the risk of kidney damage, especially in elderly or dehydrated patients."
        })
    ]
    
    for u, v, data in interactions:
        if G.has_node(u) and G.has_node(v):
            G.add_edge(u, v, **data)
            
    return G

# Initialize the network graph
interaction_graph = build_interaction_graph()

def find_matched_generic_node(extracted_name):
    """Normalize extracted drug name and find matching node in the graph."""
    if not extracted_name:
        return None
    name_clean = extracted_name.strip().lower()
    
    # Direct match check
    if name_clean in interaction_graph.nodes:
        return name_clean
        
    # Partial token match check
    for node in interaction_graph.nodes:
        if node in name_clean or name_clean in node:
            return node
            
    # Common mappings
    mappings = {
        "crocin": "paracetamol",
        "dolo": "paracetamol",
        "calpol": "paracetamol",
        "combiflam": "ibuprofen", # Contains ibuprofen + paracetamol
        "ecosprin": "aspirin",
        "glycomet": "metformin",
        "lasix": "furosemide",
        "viagra": "sildenafil",
        "penegra": "sildenafil",
        "sorbitrate": "nitroglycerin",
        "mox": "amoxicillin",
        "ciplox": "ciprofloxacin",
        "omez": "omeprazole",
        "thyronorm": "levothyroxine"
    }
    
    for brand, generic in mappings.items():
        if brand in name_clean:
            return generic
            
    return None

def check_drug_interactions(medicines_list):
    """
    Checks for drug interactions among a list of extracted medicine names.
    Returns a list of detected interactions with severity and description.
    """
    detected_interactions = []
    
    # 1. Map extracted medicines to nodes
    mapped_meds = {}
    for med in medicines_list:
        node = find_matched_generic_node(med)
        if node:
            mapped_meds[node] = med # map graph node to original extracted text
            
    nodes_found = list(mapped_meds.keys())
    
    # 2. Check pairs for edges in the interaction graph
    checked_pairs = set()
    for i in range(len(nodes_found)):
        for j in range(i + 1, len(nodes_found)):
            node_a = nodes_found[i]
            node_b = nodes_found[j]
            
            pair = tuple(sorted([node_a, node_b]))
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)
            
            if interaction_graph.has_edge(node_a, node_b):
                edge_data = interaction_graph[node_a][node_b]
                detected_interactions.append({
                    "drug_a": mapped_meds[node_a],
                    "drug_b": mapped_meds[node_b],
                    "generic_a": node_a.capitalize(),
                    "generic_b": node_b.capitalize(),
                    "severity": edge_data["severity"],
                    "description": edge_data["description"]
                })
                
    return detected_interactions
