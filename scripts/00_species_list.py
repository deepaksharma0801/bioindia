"""
SCRIPT 00 — Master Species List
================================
This script does NOT call any API.
It builds the master species reference table from known data —
all Indian extinct (EX/EW) and threatened (CR/EN/VU) species,
both flora and fauna, that you will use as your research dataset.

Run this FIRST before any other script.
Output: data/species_list.csv

No tokens needed for this script.
"""

import pandas as pd
import os

os.makedirs("data", exist_ok=True)

# ============================================================
# COMPLETE SPECIES LIST
# Indian Extinct (EX), Extinct in Wild (EW),
# Critically Endangered (CR), Endangered (EN),
# Vulnerable (VU) — Flora + Fauna
# Sources: IUCN Red List, ZSI, BSI, WII records
# ============================================================

species = [

    # ─────────────────────────────────────────────
    # EXTINCT (EX) — Fauna
    # ─────────────────────────────────────────────
    {
        "species_id": "SP001", "common_name": "Cheetah (Asiatic)",
        "scientific_name": "Acinonyx jubatus venaticus",
        "taxonomic_group": "mammal", "iucn_category": "EX_India",
        "population_trend": "extinct", "eoo_km2": 0, "aoo_km2": 0,
        "generation_length_yrs": 6.0, "threat_count": 5, "habitat_count": 2,
        "emoji": "🐆", "iucn_status_code": "ex",
        "description": "Declared locally extinct in India by 1952. Last confirmed sightings in Chhattisgarh. Hunted to extinction and lost to habitat loss. Reintroduction program launched at Kuno NP in 2022 using African Cheetahs."
    },
    {
        "species_id": "SP002", "common_name": "Indian Aurochs (Gaur ancestor)",
        "scientific_name": "Bos primigenius namadicus",
        "taxonomic_group": "mammal", "iucn_category": "EX",
        "population_trend": "extinct", "eoo_km2": 0, "aoo_km2": 0,
        "generation_length_yrs": 10.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🐂", "iucn_status_code": "ex",
        "description": "Prehistoric wild ancestor of domestic cattle in India. Extinct for millennia, documented from subfossil records across the Indian subcontinent."
    },
    {
        "species_id": "SP003", "common_name": "Pink-headed Duck",
        "scientific_name": "Rhodonessa caryophyllacea",
        "taxonomic_group": "bird", "iucn_category": "CR(PE)",
        "population_trend": "decreasing", "eoo_km2": 0, "aoo_km2": 0,
        "generation_length_yrs": 5.0, "threat_count": 4, "habitat_count": 2,
        "emoji": "🦆", "iucn_status_code": "cr",
        "description": "Possibly extinct — last confirmed sighting in 1949 in Bihar. Inhabited tall grass wetlands and jheels of the Gangetic plains. Hunted extensively during the colonial era."
    },
    {
        "species_id": "SP004", "common_name": "Himalayan Quail",
        "scientific_name": "Ophrysia superciliosa",
        "taxonomic_group": "bird", "iucn_category": "CR(PE)",
        "population_trend": "decreasing", "eoo_km2": 50, "aoo_km2": 10,
        "generation_length_yrs": 2.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🐦", "iucn_status_code": "cr",
        "description": "Last confirmed sighting in 1876 near Mussoorie, Uttarakhand. Only 2 specimens in museum collections. Known from a tiny area of steep grass-covered hillsides. Presumed extinct, actively searched for with no results."
    },
    {
        "species_id": "SP005", "common_name": "Forest Spotted Owlet",
        "scientific_name": "Athene blewitti",
        "taxonomic_group": "bird", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 180, "aoo_km2": 40,
        "generation_length_yrs": 4.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🦉", "iucn_status_code": "cr",
        "description": "Rediscovered in 1997 in Maharashtra after 113 years. Known from only 2-3 forest patches. Critically threatened by logging of deciduous forest in central India."
    },
    {
        "species_id": "SP006", "common_name": "Namdapha Flying Squirrel",
        "scientific_name": "Biswamoyopterus biswasi",
        "taxonomic_group": "mammal", "iucn_category": "CR",
        "population_trend": "unknown", "eoo_km2": 50, "aoo_km2": 10,
        "generation_length_yrs": 3.0, "threat_count": 2, "habitat_count": 1,
        "emoji": "🐿️", "iucn_status_code": "cr",
        "description": "Known from a single specimen collected in 1981 in Namdapha Tiger Reserve, Arunachal Pradesh. Has never been reliably observed since. One of the world's rarest mammals."
    },
    {
        "species_id": "SP007", "common_name": "Kondana Rat",
        "scientific_name": "Millardia kondana",
        "taxonomic_group": "mammal", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 25, "aoo_km2": 5,
        "generation_length_yrs": 1.5, "threat_count": 3, "habitat_count": 1,
        "emoji": "🐀", "iucn_status_code": "cr",
        "description": "Known only from Sinhagarh plateau near Pune, Maharashtra. Threatened by agricultural expansion and invasive grass. Population estimated at <250 mature individuals."
    },

    # ─────────────────────────────────────────────
    # CRITICALLY ENDANGERED (CR) — Mammals
    # ─────────────────────────────────────────────
    {
        "species_id": "SP008", "common_name": "Malabar Large-spotted Civet",
        "scientific_name": "Viverra civettina",
        "taxonomic_group": "mammal", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 3000, "aoo_km2": 500,
        "generation_length_yrs": 4.0, "threat_count": 4, "habitat_count": 2,
        "emoji": "🐾", "iucn_status_code": "cr",
        "description": "Endemic to the Western Ghats. Once widespread in Kerala and Karnataka lowlands, now possibly fewer than 250 individuals. Threatened by palm oil plantations replacing natural forest."
    },
    {
        "species_id": "SP009", "common_name": "Andaman White-toothed Shrew",
        "scientific_name": "Crocidura andamanensis",
        "taxonomic_group": "mammal", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 200, "aoo_km2": 40,
        "generation_length_yrs": 1.5, "threat_count": 3, "habitat_count": 2,
        "emoji": "🐭", "iucn_status_code": "cr",
        "description": "Endemic to South Andaman Island. Threatened by habitat conversion for tourism and human settlement. Very poorly studied."
    },
    {
        "species_id": "SP010", "common_name": "Ganges River Dolphin",
        "scientific_name": "Platanista gangetica gangetica",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 18000, "aoo_km2": 3000,
        "generation_length_yrs": 18.0, "threat_count": 6, "habitat_count": 1,
        "emoji": "🐬", "iucn_status_code": "en",
        "description": "India's national aquatic animal. Population estimated at ~3,500, down from tens of thousands. Threatened by dam construction blocking migration, bycatch, sand mining, and river pollution."
    },
    {
        "species_id": "SP011", "common_name": "Snow Leopard",
        "scientific_name": "Panthera uncia",
        "taxonomic_group": "mammal", "iucn_category": "VU",
        "population_trend": "decreasing", "eoo_km2": 120000, "aoo_km2": 30000,
        "generation_length_yrs": 8.0, "threat_count": 5, "habitat_count": 2,
        "emoji": "🐆", "iucn_status_code": "vu",
        "description": "India hosts ~400-700 snow leopards across Ladakh, Himachal Pradesh, Uttarakhand, Sikkim, and Arunachal Pradesh. Climate change is shrinking alpine prey habitat."
    },
    {
        "species_id": "SP012", "common_name": "Bengal Tiger",
        "scientific_name": "Panthera tigris tigris",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "increasing", "eoo_km2": 400000, "aoo_km2": 90000,
        "generation_length_yrs": 7.5, "threat_count": 4, "habitat_count": 4,
        "emoji": "🐯", "iucn_status_code": "en",
        "description": "India's national animal. Population recovered from ~1,800 in 1970 to ~3,700 today through Project Tiger. Fragmented corridors and human-wildlife conflict remain major threats."
    },
    {
        "species_id": "SP013", "common_name": "Asian Elephant",
        "scientific_name": "Elephas maximus",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 700000, "aoo_km2": 100000,
        "generation_length_yrs": 22.0, "threat_count": 5, "habitat_count": 3,
        "emoji": "🐘", "iucn_status_code": "en",
        "description": "India hosts 60% of wild Asian elephants (~27,000). Human-elephant conflict kills ~400 people and ~100 elephants annually. Corridor fragmentation by railways and highways is the primary threat."
    },
    {
        "species_id": "SP014", "common_name": "Indian One-horned Rhinoceros",
        "scientific_name": "Rhinoceros unicornis",
        "taxonomic_group": "mammal", "iucn_category": "VU",
        "population_trend": "increasing", "eoo_km2": 25000, "aoo_km2": 4000,
        "generation_length_yrs": 15.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🦏", "iucn_status_code": "vu",
        "description": "Kaziranga NP holds 2/3 of the world's population (~2,800 in India). Recovered from ~200 in 1908. Poaching for horn and flood-driven habitat loss remain key risks."
    },
    {
        "species_id": "SP015", "common_name": "Lion (Asiatic)",
        "scientific_name": "Panthera leo persica",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "increasing", "eoo_km2": 1800, "aoo_km2": 350,
        "generation_length_yrs": 7.0, "threat_count": 4, "habitat_count": 2,
        "emoji": "🦁", "iucn_status_code": "en",
        "description": "Survives only in Gir National Park, Gujarat — ~674 individuals. The world's only wild population outside Africa. Canine distemper virus and human encroachment are key threats."
    },
    {
        "species_id": "SP016", "common_name": "Sloth Bear",
        "scientific_name": "Melursus ursinus",
        "taxonomic_group": "mammal", "iucn_category": "VU",
        "population_trend": "decreasing", "eoo_km2": 280000, "aoo_km2": 50000,
        "generation_length_yrs": 12.0, "threat_count": 4, "habitat_count": 3,
        "emoji": "🐻", "iucn_status_code": "vu",
        "description": "India's only bear species outside the Himalayas. Threatened by habitat loss and human conflict. The dancing bear trade, though banned, persists in parts of central India."
    },
    {
        "species_id": "SP017", "common_name": "Dhole (Indian Wild Dog)",
        "scientific_name": "Cuon alpinus",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 500000, "aoo_km2": 80000,
        "generation_length_yrs": 4.5, "threat_count": 5, "habitat_count": 4,
        "emoji": "🐕", "iucn_status_code": "en",
        "description": "India holds the world's largest remaining dhole population (~2,500). Threats include prey depletion, habitat fragmentation, and persecution as a livestock predator."
    },
    {
        "species_id": "SP018", "common_name": "Wild Water Buffalo",
        "scientific_name": "Bubalus arnee",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 5000, "aoo_km2": 800,
        "generation_length_yrs": 10.0, "threat_count": 4, "habitat_count": 2,
        "emoji": "🐃", "iucn_status_code": "en",
        "description": "Pure wild water buffalo number fewer than 4,000 globally; India's population (~3,000) is concentrated in Assam and Chhattisgarh. Hybridization with domestic buffalo is a key genetic threat."
    },
    {
        "species_id": "SP019", "common_name": "Nilgiri Tahr",
        "scientific_name": "Nilgiritragus hylocrius",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "stable", "eoo_km2": 4000, "aoo_km2": 800,
        "generation_length_yrs": 8.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🐏", "iucn_status_code": "en",
        "description": "Endemic to the Nilgiri Hills of Tamil Nadu and Kerala. Population ~2,500, restricted to shola-grassland mosaic above 1,200m. Climate change pushing their habitat upslope."
    },
    {
        "species_id": "SP020", "common_name": "Kashmir Red Stag (Hangul)",
        "scientific_name": "Cervus hanglu hanglu",
        "taxonomic_group": "mammal", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 1400, "aoo_km2": 250,
        "generation_length_yrs": 9.0, "threat_count": 5, "habitat_count": 2,
        "emoji": "🦌", "iucn_status_code": "cr",
        "description": "Fewer than 300 individuals remain in Dachigam National Park, J&K. State animal of J&K. Threatened by habitat degradation, livestock overgrazing, and conflict-related disturbance."
    },

    # ─────────────────────────────────────────────
    # CRITICALLY ENDANGERED / ENDANGERED — Birds
    # ─────────────────────────────────────────────
    {
        "species_id": "SP021", "common_name": "Great Indian Bustard",
        "scientific_name": "Ardeotis nigriceps",
        "taxonomic_group": "bird", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 50000, "aoo_km2": 3000,
        "generation_length_yrs": 10.0, "threat_count": 5, "habitat_count": 1,
        "emoji": "🦅", "iucn_status_code": "cr",
        "description": "Fewer than 150 individuals remain — India's most endangered bird. Grassland specialist found in Rajasthan and Gujarat. Power line collisions and grassland conversion are the primary threats. Under Supreme Court review for power line burial."
    },
    {
        "species_id": "SP022", "common_name": "Bengal Florican",
        "scientific_name": "Houbaropsis bengalensis",
        "taxonomic_group": "bird", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 8000, "aoo_km2": 600,
        "generation_length_yrs": 7.0, "threat_count": 4, "habitat_count": 1,
        "emoji": "🐦", "iucn_status_code": "cr",
        "description": "Fewer than 1,000 individuals. Tall grassland specialist of the Terai and Brahmaputra floodplains. Threatened by conversion of grasslands to agriculture and sugarcane farming."
    },
    {
        "species_id": "SP023", "common_name": "Jerdon's Courser",
        "scientific_name": "Rhinoptilus bitorquatus",
        "taxonomic_group": "bird", "iucn_category": "CR",
        "population_trend": "unknown", "eoo_km2": 700, "aoo_km2": 50,
        "generation_length_yrs": 5.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🐦", "iucn_status_code": "cr",
        "description": "Rediscovered in 1986 after 86 years in the Nallamala Hills, Andhra Pradesh. Nocturnal, rocky-scrub specialist. The Srisailam reservoir has inundated part of its only known range."
    },
    {
        "species_id": "SP024", "common_name": "Indian Vulture",
        "scientific_name": "Gyps indicus",
        "taxonomic_group": "bird", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 850000, "aoo_km2": 150000,
        "generation_length_yrs": 20.0, "threat_count": 3, "habitat_count": 3,
        "emoji": "🦅", "iucn_status_code": "cr",
        "description": "Population crashed by >97% due to diclofenac (veterinary NSAID) poisoning from cattle carcasses. India banned diclofenac in 2006 but recovery is extremely slow due to low reproductive rate."
    },
    {
        "species_id": "SP025", "common_name": "White-rumped Vulture",
        "scientific_name": "Gyps bengalensis",
        "taxonomic_group": "bird", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 2200000, "aoo_km2": 400000,
        "generation_length_yrs": 20.0, "threat_count": 3, "habitat_count": 3,
        "emoji": "🦅", "iucn_status_code": "cr",
        "description": "Once one of the world's most abundant large raptors, declined by 99.9% since the 1980s. Diclofenac poisoning is the primary cause. Vital ecosystem role as carcass disposers."
    },
    {
        "species_id": "SP026", "common_name": "Red-headed Vulture",
        "scientific_name": "Sarcogyps calvus",
        "taxonomic_group": "bird", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 1500000, "aoo_km2": 200000,
        "generation_length_yrs": 20.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🦅", "iucn_status_code": "cr",
        "description": "Population declined by 91% since 1990. Also affected by diclofenac. Nests in large trees in open forest across northern and central India."
    },
    {
        "species_id": "SP027", "common_name": "Siberian Crane (India wintering)",
        "scientific_name": "Leucogeranus leucogeranus",
        "taxonomic_group": "bird", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 5000, "aoo_km2": 500,
        "generation_length_yrs": 15.0, "threat_count": 4, "habitat_count": 1,
        "emoji": "🦢", "iucn_status_code": "cr",
        "description": "Once wintered in thousands at Keoladeo Ghana NP, Rajasthan. No confirmed wintering birds in India since 2002. Globally CR with fewer than 3,500 individuals."
    },
    {
        "species_id": "SP028", "common_name": "Sociable Lapwing (India passage)",
        "scientific_name": "Vanellus gregarius",
        "taxonomic_group": "bird", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 40000, "aoo_km2": 5000,
        "generation_length_yrs": 5.0, "threat_count": 4, "habitat_count": 1,
        "emoji": "🐦", "iucn_status_code": "cr",
        "description": "Passes through northwestern India on migration. Population estimated at ~11,000. Habitat loss on migration routes and wintering grounds in South Asia drives decline."
    },
    {
        "species_id": "SP029", "common_name": "Masked Finfoot",
        "scientific_name": "Heliopais personatus",
        "taxonomic_group": "bird", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 50000, "aoo_km2": 2000,
        "generation_length_yrs": 5.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🐦", "iucn_status_code": "en",
        "description": "Extremely rare in India — recorded mainly in Northeast India's mangrove-edge and riverine forest. Very few confirmed Indian sightings."
    },
    {
        "species_id": "SP030", "common_name": "Spoon-billed Sandpiper (India wintering)",
        "scientific_name": "Calidris pygmaea",
        "taxonomic_group": "bird", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 20000, "aoo_km2": 1000,
        "generation_length_yrs": 5.0, "threat_count": 4, "habitat_count": 1,
        "emoji": "🐦", "iucn_status_code": "cr",
        "description": "Fewer than 240 individuals. Winters on mudflats along India's coasts. Distinguished by its spatula-shaped bill. Trapping in Myanmar is a major threat."
    },

    # ─────────────────────────────────────────────
    # CRITICALLY ENDANGERED / ENDANGERED — Reptiles
    # ─────────────────────────────────────────────
    {
        "species_id": "SP031", "common_name": "Gharial",
        "scientific_name": "Gavialis gangeticus",
        "taxonomic_group": "reptile", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 15000, "aoo_km2": 1500,
        "generation_length_yrs": 18.0, "threat_count": 5, "habitat_count": 1,
        "emoji": "🐊", "iucn_status_code": "cr",
        "description": "Fewer than 650 mature individuals remain in the wild, restricted to the Chambal, Girwa, and Ramganga rivers. Sand mining, fishing nets, and dam construction are primary threats."
    },
    {
        "species_id": "SP032", "common_name": "Mugger Crocodile",
        "scientific_name": "Crocodylus palustris",
        "taxonomic_group": "reptile", "iucn_category": "VU",
        "population_trend": "stable", "eoo_km2": 800000, "aoo_km2": 100000,
        "generation_length_yrs": 15.0, "threat_count": 4, "habitat_count": 3,
        "emoji": "🐊", "iucn_status_code": "vu",
        "description": "Freshwater crocodilian found in rivers, lakes, and marshes across India. Sacred at many temples. Threatened by river damming, sand mining, and pollution. Captive breeding has helped recovery."
    },
    {
        "species_id": "SP033", "common_name": "Olive Ridley Sea Turtle",
        "scientific_name": "Lepidochelys olivacea",
        "taxonomic_group": "reptile", "iucn_category": "VU",
        "population_trend": "decreasing", "eoo_km2": 5000000, "aoo_km2": 500000,
        "generation_length_yrs": 25.0, "threat_count": 5, "habitat_count": 2,
        "emoji": "🐢", "iucn_status_code": "vu",
        "description": "Odisha's Gahirmatha Beach hosts the world's largest mass nesting (arribada) with ~600,000 turtles. Trawler bycatch, beach lighting, and coastal development are key threats."
    },
    {
        "species_id": "SP034", "common_name": "Leatherback Sea Turtle",
        "scientific_name": "Dermochelys coriacea",
        "taxonomic_group": "reptile", "iucn_category": "VU",
        "population_trend": "decreasing", "eoo_km2": 8000000, "aoo_km2": 100000,
        "generation_length_yrs": 25.0, "threat_count": 5, "habitat_count": 2,
        "emoji": "🐢", "iucn_status_code": "vu",
        "description": "World's largest turtle, nesting on Andaman & Nicobar Islands. Population crashed by >70% globally over three generations. Bycatch and plastic ingestion are primary threats."
    },
    {
        "species_id": "SP035", "common_name": "Indian Star Tortoise",
        "scientific_name": "Geochelone elegans",
        "taxonomic_group": "reptile", "iucn_category": "VU",
        "population_trend": "decreasing", "eoo_km2": 700000, "aoo_km2": 100000,
        "generation_length_yrs": 20.0, "threat_count": 3, "habitat_count": 3,
        "emoji": "🐢", "iucn_status_code": "vu",
        "description": "Endemic to India and Sri Lanka. Among the world's most trafficked tortoises — thousands seized in illegal pet trade shipments annually. Found in scrub and dry forest across peninsular India."
    },
    {
        "species_id": "SP036", "common_name": "King Cobra",
        "scientific_name": "Ophiophagus hannah",
        "taxonomic_group": "reptile", "iucn_category": "VU",
        "population_trend": "decreasing", "eoo_km2": 1500000, "aoo_km2": 200000,
        "generation_length_yrs": 12.0, "threat_count": 4, "habitat_count": 4,
        "emoji": "🐍", "iucn_status_code": "vu",
        "description": "World's longest venomous snake, found across the Western Ghats and Northeast India. Threatened by habitat loss, road kills, and collection for snake charming and traditional medicine."
    },

    # ─────────────────────────────────────────────
    # CRITICALLY ENDANGERED / ENDANGERED — Amphibians
    # ─────────────────────────────────────────────
    {
        "species_id": "SP037", "common_name": "Purple Frog (Indian Purple Frog)",
        "scientific_name": "Nasikabatrachus sahyadrensis",
        "taxonomic_group": "amphibian", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 5000, "aoo_km2": 500,
        "generation_length_yrs": 8.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🐸", "iucn_status_code": "en",
        "description": "Described as new to science only in 2003. A living fossil — only known relative is in the Seychelles, diverged ~130 million years ago. Found in Western Ghats. Spends most of its life underground."
    },
    {
        "species_id": "SP038", "common_name": "Anamalai Flying Frog",
        "scientific_name": "Rhacophorus pseudomalabaricus",
        "taxonomic_group": "amphibian", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 500, "aoo_km2": 100,
        "generation_length_yrs": 4.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🐸", "iucn_status_code": "cr",
        "description": "Known only from a small area of the Anamalai Hills, Tamil Nadu. Critically threatened by cardamom and tea plantation expansion replacing its montane forest habitat."
    },
    {
        "species_id": "SP039", "common_name": "Resplendent Shrub Frog",
        "scientific_name": "Raorchestes resplendens",
        "taxonomic_group": "amphibian", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 200, "aoo_km2": 40,
        "generation_length_yrs": 3.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🐸", "iucn_status_code": "cr",
        "description": "Found only on Ponmudi Hill summit in Kerala. Extremely restricted range makes any habitat disturbance existentially threatening. Described in 2011."
    },

    # ─────────────────────────────────────────────
    # CRITICALLY ENDANGERED / ENDANGERED — Fish
    # ─────────────────────────────────────────────
    {
        "species_id": "SP040", "common_name": "Pondicherry Shark",
        "scientific_name": "Carcharhinus hemiodon",
        "taxonomic_group": "fish", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 200000, "aoo_km2": 10000,
        "generation_length_yrs": 10.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🦈", "iucn_status_code": "cr",
        "description": "One of the world's rarest sharks — no confirmed sighting since 1979. Historically in Indian estuaries and coastal waters. Likely critically threatened or possibly extinct due to intensive fishing pressure."
    },
    {
        "species_id": "SP041", "common_name": "Ganges Shark",
        "scientific_name": "Glyphis gangeticus",
        "taxonomic_group": "fish", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 50000, "aoo_km2": 5000,
        "generation_length_yrs": 12.0, "threat_count": 4, "habitat_count": 1,
        "emoji": "🦈", "iucn_status_code": "cr",
        "description": "True freshwater shark of the Ganges and Hooghly rivers. Extremely rare — only 5 confirmed specimens in modern times. River pollution, overfishing, and dam construction have severely reduced habitat."
    },
    {
        "species_id": "SP042", "common_name": "Golden Mahseer",
        "scientific_name": "Tor putitora",
        "taxonomic_group": "fish", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 200000, "aoo_km2": 30000,
        "generation_length_yrs": 8.0, "threat_count": 5, "habitat_count": 2,
        "emoji": "🐟", "iucn_status_code": "en",
        "description": "India's iconic large riverine fish, called 'the tiger of the river'. Found in Himalayan foothills rivers. Threatened by hydropower dams, sand extraction, and overfishing. Once abundant in the Ganga system."
    },

    # ─────────────────────────────────────────────
    # CRITICALLY ENDANGERED / ENDANGERED — Plants (Flora)
    # ─────────────────────────────────────────────
    {
        "species_id": "SP043", "common_name": "Malabar Cycad",
        "scientific_name": "Cycas circinalis",
        "taxonomic_group": "plant", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 8000, "aoo_km2": 1000,
        "generation_length_yrs": 50.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🌴", "iucn_status_code": "en",
        "description": "A living fossil — cycads have existed for 280 million years. Endemic to the Western Ghats. Threatened by conversion of coastal forests and illegal collection for ornamental use."
    },
    {
        "species_id": "SP044", "common_name": "Red Vanda (Fox-tail Orchid)",
        "scientific_name": "Renanthera imschootiana",
        "taxonomic_group": "plant", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 3000, "aoo_km2": 300,
        "generation_length_yrs": 20.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🌺", "iucn_status_code": "en",
        "description": "Rare orchid found in Nagaland, Manipur, and Arunachal Pradesh. Protected under CITES Appendix I. Heavily collected for horticultural trade. Population very small and fragmented."
    },
    {
        "species_id": "SP045", "common_name": "Blue Vanda (Blue Orchid)",
        "scientific_name": "Vanda coerulea",
        "taxonomic_group": "plant", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 5000, "aoo_km2": 600,
        "generation_length_yrs": 20.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🌸", "iucn_status_code": "en",
        "description": "One of the most beautiful orchids in the world. Found in oak forests of Arunachal Pradesh and Manipur at 1000-1800m. Mass collection for horticulture nearly wiped out wild populations."
    },
    {
        "species_id": "SP046", "common_name": "Pitcher Plant (Nepenthes)",
        "scientific_name": "Nepenthes khasiana",
        "taxonomic_group": "plant", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 1500, "aoo_km2": 150,
        "generation_length_yrs": 15.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🪴", "iucn_status_code": "en",
        "description": "India's only native pitcher plant. Found only in the Khasi Hills of Meghalaya. Carnivorous plant of boggy grasslands. Threatened by jhum cultivation and illegal collection."
    },
    {
        "species_id": "SP047", "common_name": "Coscinium fenestratum (Tree Turmeric)",
        "scientific_name": "Coscinium fenestratum",
        "taxonomic_group": "plant", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 20000, "aoo_km2": 2000,
        "generation_length_yrs": 30.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🌿", "iucn_status_code": "en",
        "description": "Large woody climber of the Western Ghats. Known as 'tree turmeric' for its yellow berberine-rich wood. Used extensively in traditional Ayurvedic medicine. Severely overexploited, now rare throughout its range."
    },
    {
        "species_id": "SP048", "common_name": "Sarpagandha (Indian Snakeroot)",
        "scientific_name": "Rauvolfia serpentina",
        "taxonomic_group": "plant", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 500000, "aoo_km2": 50000,
        "generation_length_yrs": 10.0, "threat_count": 3, "habitat_count": 3,
        "emoji": "🌿", "iucn_status_code": "en",
        "description": "Source of reserpine, used in antihypertensive drugs. Massively overcollected across India for pharmaceutical and traditional medicine use. Now rare in its original forest habitat."
    },
    {
        "species_id": "SP049", "common_name": "Agarwood Tree (Oud)",
        "scientific_name": "Aquilaria malaccensis",
        "taxonomic_group": "plant", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 30000, "aoo_km2": 3000,
        "generation_length_yrs": 40.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🌲", "iucn_status_code": "cr",
        "description": "Produces the world's most valuable timber — agarwood (oud). Found in Northeast India's tropical forests. Intense poaching for agarwood resin (worth more than gold by weight) has devastated populations."
    },
    {
        "species_id": "SP050", "common_name": "Assam Catkin Yew",
        "scientific_name": "Amentotaxus assamica",
        "taxonomic_group": "plant", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 200, "aoo_km2": 30,
        "generation_length_yrs": 60.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🌲", "iucn_status_code": "cr",
        "description": "Known from fewer than 50 mature trees in Arunachal Pradesh. One of the world's rarest gymnosperms. Threatened by jhum cultivation and timber extraction."
    },
    {
        "species_id": "SP051", "common_name": "Malabar Kino Tree",
        "scientific_name": "Pterocarpus marsupium",
        "taxonomic_group": "plant", "iucn_category": "VU",
        "population_trend": "decreasing", "eoo_km2": 200000, "aoo_km2": 30000,
        "generation_length_yrs": 35.0, "threat_count": 3, "habitat_count": 3,
        "emoji": "🌳", "iucn_status_code": "vu",
        "description": "Large deciduous tree of peninsular India. Prized for its blood-red kino resin used in Ayurvedic medicine for diabetes. Heavily logged for timber and medicinal resin. Kerala's state tree."
    },
    {
        "species_id": "SP052", "common_name": "Teri Orchid",
        "scientific_name": "Eulophia cullenii",
        "taxonomic_group": "plant", "iucn_category": "CR",
        "population_trend": "decreasing", "eoo_km2": 800, "aoo_km2": 80,
        "generation_length_yrs": 15.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🌸", "iucn_status_code": "cr",
        "description": "Rare terrestrial orchid found in sandy coastal scrub of Tamil Nadu and Andhra Pradesh. Threatened by beach sand mining and coastal development. One of India's most threatened orchid species."
    },

    # ─────────────────────────────────────────────
    # VULNERABLE — Additional Fauna
    # ─────────────────────────────────────────────
    {
        "species_id": "SP053", "common_name": "Indian Pangolin",
        "scientific_name": "Manis crassicaudata",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 600000, "aoo_km2": 100000,
        "generation_length_yrs": 5.0, "threat_count": 3, "habitat_count": 3,
        "emoji": "🦔", "iucn_status_code": "en",
        "description": "World's most trafficked mammal. Scales used in traditional Chinese medicine despite no proven efficacy. Hunted extensively across India. Population declined by >50% over last decade."
    },
    {
        "species_id": "SP054", "common_name": "Dugong",
        "scientific_name": "Dugong dugon",
        "taxonomic_group": "mammal", "iucn_category": "VU",
        "population_trend": "decreasing", "eoo_km2": 500000, "aoo_km2": 50000,
        "generation_length_yrs": 25.0, "threat_count": 4, "habitat_count": 1,
        "emoji": "🐋", "iucn_status_code": "vu",
        "description": "India's only sirenian (sea cow). Found in Gulf of Mannar and Andaman waters. Fewer than 200 in Indian waters. Bycatch in fishing nets and seagrass loss are primary threats."
    },
    {
        "species_id": "SP055", "common_name": "Indian Wild Ass",
        "scientific_name": "Equus hemionus khur",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "increasing", "eoo_km2": 5000, "aoo_km2": 2000,
        "generation_length_yrs": 8.0, "threat_count": 3, "habitat_count": 1,
        "emoji": "🐴", "iucn_status_code": "en",
        "description": "Restricted to the Little Rann of Kutch, Gujarat — India's only wild equid. Population recovered from ~700 in 1969 to ~6,000 today. Disease transmission from domestic donkeys is a key threat."
    },
    {
        "species_id": "SP056", "common_name": "Blackbuck",
        "scientific_name": "Antilope cervicapra",
        "taxonomic_group": "mammal", "iucn_category": "LC",
        "population_trend": "increasing", "eoo_km2": 700000, "aoo_km2": 80000,
        "generation_length_yrs": 6.0, "threat_count": 3, "habitat_count": 2,
        "emoji": "🦌", "iucn_status_code": "lc",
        "description": "India's national antelope. Population recovered from ~8,000 in 1947 to over 50,000 today due to protection. Still threatened by habitat fragmentation and poaching. India's only LC species in this dataset."
    },
    {
        "species_id": "SP057", "common_name": "Indian Skimmer",
        "scientific_name": "Rynchops albicollis",
        "taxonomic_group": "bird", "iucn_category": "VU",
        "population_trend": "decreasing", "eoo_km2": 500000, "aoo_km2": 30000,
        "generation_length_yrs": 8.0, "threat_count": 4, "habitat_count": 1,
        "emoji": "🐦", "iucn_status_code": "vu",
        "description": "Nests on exposed sand bars of major Indian rivers. Population estimated at 5,000–6,000. Threatened by sand mining destroying nesting sites and dam-induced reduction of monsoon floods that create sandbars."
    },
    {
        "species_id": "SP058", "common_name": "Red Panda",
        "scientific_name": "Ailurus fulgens",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 80000, "aoo_km2": 15000,
        "generation_length_yrs": 8.0, "threat_count": 4, "habitat_count": 1,
        "emoji": "🦊", "iucn_status_code": "en",
        "description": "Found in temperate forests of Sikkim, Arunachal Pradesh, and West Bengal. Bamboo-specialist threatened by bamboo flowering/die-off cycles and habitat loss. State animal of Sikkim."
    },
    {
        "species_id": "SP059", "common_name": "Clouded Leopard",
        "scientific_name": "Neofelis nebulosa",
        "taxonomic_group": "mammal", "iucn_category": "VU",
        "population_trend": "decreasing", "eoo_km2": 100000, "aoo_km2": 20000,
        "generation_length_yrs": 6.0, "threat_count": 4, "habitat_count": 2,
        "emoji": "🐆", "iucn_status_code": "vu",
        "description": "Found in Northeast India's forests. Elusive and poorly studied. Hunted for its beautiful coat and bones for traditional medicine. Forest logging in Assam and Arunachal Pradesh threatens its habitat."
    },
    {
        "species_id": "SP060", "common_name": "Irrawaddy Dolphin",
        "scientific_name": "Orcaella brevirostris",
        "taxonomic_group": "mammal", "iucn_category": "EN",
        "population_trend": "decreasing", "eoo_km2": 20000, "aoo_km2": 2000,
        "generation_length_yrs": 20.0, "threat_count": 4, "habitat_count": 2,
        "emoji": "🐬", "iucn_status_code": "en",
        "description": "Found in Chilika Lake (Odisha) and Mahakam River. Chilika population (approximately 120-150) is the only confirmed marine population in India. Bycatch in fishing nets is the primary threat."
    },
]

# ── Build DataFrame ──────────────────────────────────────────
df = pd.DataFrame(species)

# Add numeric columns for pipeline use
category_map = {"EX": 7, "EW": 6, "EX_India": 7, "CR(PE)": 6.5,
                "CR": 6, "EN": 5, "VU": 4, "NT": 3, "LC": 2, "DD": 1}
trend_map = {"decreasing": 1, "stable": 0, "increasing": -1, "unknown": None, "extinct": None}

df["iucn_category_num"] = df["iucn_category"].map(category_map)
df["population_trend_num"] = df["population_trend"].map(trend_map)

# Save
df.to_csv("data/species_list.csv", index=False)
print(f"✅ Saved {len(df)} species to data/species_list.csv")
print(f"\nBreakdown by taxonomic group:")
print(df["taxonomic_group"].value_counts().to_string())
print(f"\nBreakdown by IUCN category:")
print(df["iucn_category"].value_counts().to_string())
