"""Registry of external graph sources (benchmarks + real-world datasets).

Every named source has a ``Source`` entry so staging, promotion, and
the auto-generated README all read from the same place. To add a new
benchmark or real-world corpus: append an entry here, then (for
archive-based sources) ``scripts/stage_benchmark.py`` picks it up
automatically; (for code-based sources) write a small
``scripts/stage_<name>.py`` that writes graphml into
``staging/<name>/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Source:
    # Unique key. Must match the staging/promotion subfolder name.
    name: str
    # Cohort the promoted graphs live in. Determines the category
    # column in the manifest and the top-level folder under graphs/
    # (or graphs-with-drawings/ for the layout-carrying cohort).
    category: str  # "benchmark" | "real_world" | "graphs_with_drawings"
    # Human-readable description (what this corpus is, typical n, typical
    # structural regime). Goes into the per-source README.
    description: str
    # Canonical citation for the corpus. Empty string if no formal
    # citation exists (e.g. community-curated test sets).
    citation: str
    # Optional — archive-based sources provide these three so
    # stage_benchmark.py can download + extract. Code-based sources
    # (nx built-ins, etc.) leave them as None and ship their own
    # stage_*.py.
    url: Optional[str] = None
    archive_name: Optional[str] = None
    strip_prefix: Optional[str] = None
    # Path (relative to $out/) where staged .graphml files live.
    # Defaults: ``staging/<name>/`` for real_world/benchmark;
    # ``staging-graphs-with-drawings/<name>/`` for graphs_with_drawings.
    # Set explicitly when staging sits under a domain subfolder like
    # ``staging/chemistry_extras/<name>/`` or
    # ``staging/transport/<name>/``.
    staging_path: Optional[str] = None


SOURCES: dict[str, Source] = {
    # ---- benchmarks (graph-drawing community standards) ----
    "rome": Source(
        name="rome",
        category="benchmark",
        description=(
            "11,534 undirected graphs with 10–100 nodes, originally "
            "assembled to evaluate four graph-drawing algorithms at the "
            "University of Rome. Sparse (density median ~0.07), mostly "
            "non-planar for larger n. Ships as yFiles GraphML from the "
            "University of Perugia's mirror of graphdrawing.org."
        ),
        citation=(
            "Di Battista, G., Garg, A., Liotta, G., Tamassia, R., "
            "Tassinari, E., & Vargiu, F. (1997). An experimental "
            "comparison of four graph drawing algorithms. Computational "
            "Geometry, 7(5–6), 303–325."
        ),
        url="https://graphdrawing.unipg.it/data/rome-graphml.tgz",
        archive_name="rome-graphml.tgz",
        strip_prefix="rome/",
    ),
    "north": Source(
        name="north",
        category="benchmark",
        description=(
            "1,277 directed acyclic graphs — the 'AT&T / North' DAG "
            "corpus. Raw graphs were collected by Stephen North at "
            "AT&T Bell Labs via his public `DrawDAG` email-based "
            "graph-drawing service (ca. 1990s), making these "
            "observational DAGs from real software-engineering "
            "artefacts (compiler IRs, call graphs, build-system "
            "dependency graphs). Directed in origin; we coerce to "
            "undirected at promotion time since our readability "
            "metrics assume undirected drawings."
        ),
        citation=(
            "Di Battista, G., Garg, A., Liotta, G., Parise, A., "
            "Tamassia, R., Tassinari, E., Vargiu, F., & Vismara, L. "
            "(2000). Drawing directed acyclic graphs: An experimental "
            "study. International Journal of Computational Geometry "
            "& Applications 10(6), 623–648. "
            "https://doi.org/10.1142/S0218195900000358. Earlier "
            "conference version: Di Battista et al. (1997), "
            "Drawing directed acyclic graphs: An experimental study. "
            "In S. North (Ed.), Graph Drawing (GD'96), LNCS 1190, "
            "76–91. Springer. Raw graphs collected by Stephen North "
            "at AT&T Bell Labs (`DrawDAG` service; originally "
            "distributed via ftp://ftp.research.att.com/dist/drawdag/)."
        ),
        url="https://graphdrawing.unipg.it/data/north-graphml.tgz",
        archive_name="north-graphml.tgz",
        strip_prefix="north/",
    ),
    "random-dag": Source(
        name="random-dag",
        category="benchmark",
        description=(
            "Pregenerated random DAGs in GraphML, companion benchmark "
            "to the AT&T / North DAG set. Directed in origin — coerced "
            "to undirected at promotion time."
        ),
        citation=(
            "Graph Drawing Datasets, University of Perugia. "
            "https://graphdrawing.unipg.it/data.html"
        ),
        url="https://graphdrawing.unipg.it/data/random-dag-graphml.tgz",
        archive_name="random-dag-graphml.tgz",
        strip_prefix="random-dag/",
    ),
    # dagmar intentionally dropped 2026-04-23 — see CORPUS.md §15 and
    # potential-graph-sources.md. The DAGmar corpus is a synthetic
    # level-graph generator (Bachmaier, Gleißner & Hofmeier 2012,
    # University of Passau MIP-1202), designed for hierarchical /
    # Sugiyama layout evaluation. Its distinguishing structural feature
    # — the intentional DAG level structure — is erased when we coerce
    # directed → undirected at promotion, and after coercion it is
    # indistinguishable from random-dag or from our `generated/`
    # synthetic cohort. Retention under our filters was also only 12%
    # (240/1960, almost all rejected for n > 75). Not worth including
    # for this corpus; leave this comment as the audit trail.

    # ---- real-world (observed networks, not synthetic benchmarks) ----
    # `classic` (Zachary karate / Davis southern women / Padgett Florentine
    # families / Krackhardt kite) was 4 hand-curated NetworkX-built-in
    # graphs. Removed 2026-04-24: these structural patterns are already
    # exhaustively covered by the larger TUDataset social and bioinformatics
    # cohorts; keeping them as a separate source added curation overhead
    # for ~0% corpus enrichment. See RESEARCH_LOG.md §10.18.
    # TUDataset (Morris et al. 2020) - graph-kernel benchmark collection
    # from TU Dortmund. Each Source name encodes the parent collection
    # via slash routing: TUDataset/<NAME> uppercased to match TUDataset's
    # own naming convention (MUTAG, AIDS, PTC_MR, etc.). Source files
    # land at graphs/real_world/TUDataset/<NAME>/.
    # Renamed from `tudo_*` on 2026-04-24 to give the parent collection
    # a visible umbrella, mirroring the netzschleuder pattern. See
    # RESEARCH_LOG.md §10.13.
    "TUDataset/MUTAG": Source(
        name="TUDataset/MUTAG",
        category="real_world",
        description=(
            "188 aromatic + heteroaromatic nitro compounds (chemistry). "
            "Each graph is a molecule: atoms as nodes, bonds as edges. "
            "Classification target is mutagenicity against Salmonella "
            "typhimurium. Average 17.93 nodes, 19.79 edges — fits our "
            "n ≤ 75 cap almost entirely."
        ),
        citation=(
            "Debnath, A.K., Lopez de Compadre, R.L., Debnath, G., "
            "Shusterman, A.J., & Hansch, C. (1991). Structure-activity "
            "relationship of mutagenic aromatic and heteroaromatic "
            "nitro compounds. Correlation with molecular orbital "
            "energies and hydrophobicity. Journal of Medicinal "
            "Chemistry 34(2), 786–797."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/MUTAG.zip",
        archive_name="MUTAG.zip",
        staging_path="staging/TUDataset/MUTAG",
    ),
    "TUDataset/AIDS": Source(
        name="TUDataset/AIDS",
        category="real_world",
        description=(
            "2,000 molecular graphs from the NCI/NIH AIDS antiviral "
            "screen (subset). Each graph is a chemical compound; "
            "classification is active vs. inactive against HIV. Average "
            "15.69 nodes, 16.20 edges — well within our n ≤ 75 cap."
        ),
        citation=(
            "Riesen, K. & Bunke, H. (2008). IAM graph database "
            "repository for graph based pattern recognition and "
            "machine learning. In Proc. SSSPR 2008 (LNCS 5342), "
            "287–297. Underlying data: National Cancer Institute / NIH "
            "AIDS Antiviral Screen."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/AIDS.zip",
        archive_name="AIDS.zip",
        staging_path="staging/TUDataset/AIDS",
    ),
    "TUDataset/ENZYMES": Source(
        name="TUDataset/ENZYMES",
        category="real_world",
        description=(
            "600 protein tertiary-structure graphs drawn from the "
            "BRENDA enzyme database. Nodes are secondary structure "
            "elements (helices, sheets, turns), edges encode spatial "
            "proximity. Classification is EC top-level enzyme class "
            "(6 classes). Average 32.63 nodes, 62.14 edges — mostly "
            "within our n ≤ 75 cap, a small tail will filter out."
        ),
        citation=(
            "Borgwardt, K.M., Ong, C.S., Schönauer, S., "
            "Vishwanathan, S.V.N., Smola, A.J., & Kriegel, H.-P. "
            "(2005). Protein function prediction via graph kernels. "
            "Bioinformatics 21(Suppl 1), i47–i56."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/ENZYMES.zip",
        archive_name="ENZYMES.zip",
        staging_path="staging/TUDataset/ENZYMES",
    ),
    "TUDataset/PTC_MR": Source(
        name="TUDataset/PTC_MR",
        category="real_world",
        description=(
            "344 chemical-compound graphs from the Predictive Toxicology "
            "Challenge (male rats). Atoms are nodes, bonds are edges. "
            "Average ~14 nodes — small molecules. Four PTC variants "
            "(MR/FR/MM/FM) differ in the rat strain / sex used for the "
            "toxicology assay."
        ),
        citation=(
            "Helma, C., King, R.D., Kramer, S., & Srinivasan, A. "
            "(2001). The Predictive Toxicology Challenge 2000–2001. "
            "Bioinformatics 17(1), 107–108."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/PTC_MR.zip",
        archive_name="PTC_MR.zip",
        staging_path="staging/TUDataset/PTC_MR",
    ),
    "TUDataset/PTC_FR": Source(
        name="TUDataset/PTC_FR",
        category="real_world",
        description=(
            "344 chemical-compound graphs, Predictive Toxicology "
            "Challenge female rats variant. Same provenance as PTC_MR."
        ),
        citation=(
            "Helma, C., King, R.D., Kramer, S., & Srinivasan, A. "
            "(2001). The Predictive Toxicology Challenge 2000–2001. "
            "Bioinformatics 17(1), 107–108."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/PTC_FR.zip",
        archive_name="PTC_FR.zip",
        staging_path="staging/TUDataset/PTC_FR",
    ),
    "TUDataset/PTC_MM": Source(
        name="TUDataset/PTC_MM",
        category="real_world",
        description=(
            "344 chemical-compound graphs, Predictive Toxicology "
            "Challenge male mice variant. Same provenance as PTC_MR."
        ),
        citation=(
            "Helma, C., King, R.D., Kramer, S., & Srinivasan, A. "
            "(2001). The Predictive Toxicology Challenge 2000–2001. "
            "Bioinformatics 17(1), 107–108."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/PTC_MM.zip",
        archive_name="PTC_MM.zip",
        staging_path="staging/TUDataset/PTC_MM",
    ),
    "TUDataset/PTC_FM": Source(
        name="TUDataset/PTC_FM",
        category="real_world",
        description=(
            "344 chemical-compound graphs, Predictive Toxicology "
            "Challenge female mice variant. Same provenance as PTC_MR."
        ),
        citation=(
            "Helma, C., King, R.D., Kramer, S., & Srinivasan, A. "
            "(2001). The Predictive Toxicology Challenge 2000–2001. "
            "Bioinformatics 17(1), 107–108."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/PTC_FM.zip",
        archive_name="PTC_FM.zip",
        staging_path="staging/TUDataset/PTC_FM",
    ),
    "TUDataset/DHFR": Source(
        name="TUDataset/DHFR",
        category="real_world",
        description=(
            "756 graphs of dihydrofolate-reductase (DHFR) inhibitors. "
            "Classification: active / inactive. Average ~42 nodes — "
            "larger than MUTAG/PTC but well within our n ≤ 75 cap."
        ),
        citation=(
            "Sutherland, J.J., O'Brien, L.A., & Weaver, D.F. (2003). "
            "Spline-fitting with a genetic algorithm: A method for "
            "developing classification structure-activity relationships. "
            "Journal of Chemical Information and Computer Sciences "
            "43(6), 1906–1915."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/DHFR.zip",
        archive_name="DHFR.zip",
        staging_path="staging/TUDataset/DHFR",
    ),
    "TUDataset/COX2": Source(
        name="TUDataset/COX2",
        category="real_world",
        description=(
            "467 graphs of cyclooxygenase-2 (COX-2) inhibitors. "
            "Classification: active / inactive. Average ~41 nodes."
        ),
        citation=(
            "Sutherland, J.J., O'Brien, L.A., & Weaver, D.F. (2003). "
            "Spline-fitting with a genetic algorithm: A method for "
            "developing classification structure-activity relationships. "
            "Journal of Chemical Information and Computer Sciences "
            "43(6), 1906–1915."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/COX2.zip",
        archive_name="COX2.zip",
        staging_path="staging/TUDataset/COX2",
    ),
    "TUDataset/BZR": Source(
        name="TUDataset/BZR",
        category="real_world",
        description=(
            "405 graphs of benzodiazepine-receptor ligands. "
            "Classification: active / inactive. Average ~36 nodes."
        ),
        citation=(
            "Sutherland, J.J., O'Brien, L.A., & Weaver, D.F. (2003). "
            "Spline-fitting with a genetic algorithm: A method for "
            "developing classification structure-activity relationships. "
            "Journal of Chemical Information and Computer Sciences "
            "43(6), 1906–1915."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/BZR.zip",
        archive_name="BZR.zip",
        staging_path="staging/TUDataset/BZR",
    ),

    # --- TUDataset additions 2026-04-24 (Phase A: structurally diverse ---
    # --- single-instance sets, see RESEARCH_LOG.md §10.14)             ---

    "TUDataset/PROTEINS": Source(
        name="TUDataset/PROTEINS",
        category="real_world",
        description=(
            "1,113 protein tertiary-structure graphs (different curation "
            "from `ENZYMES`). Nodes = secondary-structure elements "
            "(helices / sheets / turns); edges = spatial proximity in 3D. "
            "Classification: enzyme vs. non-enzyme. Average 39.06 nodes, "
            "72.82 edges."
        ),
        citation=(
            "Borgwardt, K.M., Ong, C.S., Schönauer, S., "
            "Vishwanathan, S.V.N., Smola, A.J., & Kriegel, H.-P. "
            "(2005). Protein function prediction via graph kernels. "
            "Bioinformatics 21(Suppl 1), i47–i56. Also: Dobson, P.D. & "
            "Doig, A.J. (2003). Distinguishing enzyme structures from "
            "non-enzymes without alignments. Journal of Molecular "
            "Biology 330(4), 771–783."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/PROTEINS.zip",
        archive_name="PROTEINS.zip",
        staging_path="staging/TUDataset/PROTEINS",
    ),
    "TUDataset/KKI": Source(
        name="TUDataset/KKI",
        category="real_world",
        description=(
            "~190 brain functional-connectivity graphs from the Kennedy "
            "Krieger Institute fMRI cohort (subset of the ADHD-200 "
            "consortium release). Nodes = brain regions, edges = "
            "above-threshold cross-correlation of resting-state fMRI "
            "time series. Average 26.96 nodes, 48.42 edges. "
            "Classification: ADHD vs. typically-developing controls."
        ),
        citation=(
            "Pan, S., Wu, J., Zhu, X., Long, G., & Zhang, C. (2017). "
            "Task Sensitive Feature Exploration and Learning for "
            "Multitask Graph Classification. IEEE Trans. Cybernetics "
            "47(3), 744–758. Underlying data: ADHD-200 Sample "
            "Initiative (https://fcon_1000.projects.nitrc.org/indi/adhd200/), "
            "Kennedy Krieger Institute site (Mostofsky, S. et al.)."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/KKI.zip",
        archive_name="KKI.zip",
        staging_path="staging/TUDataset/KKI",
    ),
    "TUDataset/Peking_1": Source(
        name="TUDataset/Peking_1",
        category="real_world",
        description=(
            "~85 brain functional-connectivity graphs from the Peking "
            "University site of the ADHD-200 consortium. Same "
            "construction as `KKI`. Average 39.31 nodes, 77.35 edges. "
            "Classification: ADHD vs. typically-developing controls."
        ),
        citation=(
            "Pan, S., Wu, J., Zhu, X., Long, G., & Zhang, C. (2017). "
            "Task Sensitive Feature Exploration and Learning for "
            "Multitask Graph Classification. IEEE Trans. Cybernetics "
            "47(3), 744–758. Underlying data: ADHD-200 Sample "
            "Initiative (https://fcon_1000.projects.nitrc.org/indi/adhd200/), "
            "Peking University site."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Peking_1.zip",
        archive_name="Peking_1.zip",
        staging_path="staging/TUDataset/Peking_1",
    ),
    "TUDataset/Cuneiform": Source(
        name="TUDataset/Cuneiform",
        category="real_world",
        description=(
            "267 graphs of Hittite cuneiform-tablet sign skeletons "
            "extracted from 3D-scanned tablets. Nodes = wedge-stroke "
            "skeleton vertices; edges = adjacency along the stroke. "
            "Classification: 30 sign classes (Old Hittite script). "
            "Average 21.27 nodes, 44.80 edges."
        ),
        citation=(
            "Kriege, N.M., Fey, M., Fisseler, D., Mutzel, P., & "
            "Weichert, F. (2018). Recognizing Cuneiform Signs Using "
            "Graph Based Methods. International Workshop on Cost-"
            "Sensitive Learning (COST), SDM 2018."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Cuneiform.zip",
        archive_name="Cuneiform.zip",
        staging_path="staging/TUDataset/Cuneiform",
    ),
    "TUDataset/MSRC_9": Source(
        name="TUDataset/MSRC_9",
        category="real_world",
        description=(
            "221 region-adjacency graphs from the Microsoft Research "
            "Cambridge image-segmentation dataset, 9-class variant. "
            "Nodes = image segments (super-pixels); edges = spatial "
            "adjacency between segments. Average 40.58 nodes, 97.94 "
            "edges. Used as a graph-kernel benchmark for image "
            "classification."
        ),
        citation=(
            "Winn, J., Criminisi, A., & Minka, T. (2005). Object "
            "categorization by learned universal visual dictionary. "
            "Proc. ICCV 2005, 1800–1807. Graph extraction: Neumann, M., "
            "Garnett, R., Bauckhage, C., & Kersting, K. (2016). "
            "Propagation kernels: efficient graph kernels from "
            "propagated information. Machine Learning 102(2), 209–245."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/MSRC_9.zip",
        archive_name="MSRC_9.zip",
        staging_path="staging/TUDataset/MSRC_9",
    ),
    "TUDataset/MSRC_21C": Source(
        name="TUDataset/MSRC_21C",
        category="real_world",
        description=(
            "209 region-adjacency graphs from the Microsoft Research "
            "Cambridge image-segmentation dataset, 21-class cleaned "
            "variant. Same construction as `MSRC_9` but a finer label "
            "set. Average 40.28 nodes, 96.60 edges."
        ),
        citation=(
            "Winn, J., Criminisi, A., & Minka, T. (2005). Object "
            "categorization by learned universal visual dictionary. "
            "Proc. ICCV 2005, 1800–1807. Graph extraction: Neumann, M., "
            "Garnett, R., Bauckhage, C., & Kersting, K. (2016). "
            "Propagation kernels: efficient graph kernels from "
            "propagated information. Machine Learning 102(2), 209–245."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/MSRC_21C.zip",
        archive_name="MSRC_21C.zip",
        staging_path="staging/TUDataset/MSRC_21C",
    ),
    "TUDataset/IMDB-BINARY": Source(
        name="TUDataset/IMDB-BINARY",
        category="real_world",
        description=(
            "1,000 actor-collaboration ego graphs derived from IMDb. "
            "Each graph is one movie's actor-actor co-appearance "
            "network (edges between actors who appeared in the same "
            "film). Two genres: Action / Romance. Average 19.77 nodes, "
            "96.53 edges — relatively dense for its size."
        ),
        citation=(
            "Yanardag, P. & Vishwanathan, S.V.N. (2015). Deep Graph "
            "Kernels. Proc. 21st ACM SIGKDD, 1365–1374. "
            "https://doi.org/10.1145/2783258.2783417."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/IMDB-BINARY.zip",
        archive_name="IMDB-BINARY.zip",
        staging_path="staging/TUDataset/IMDB-BINARY",
    ),
    "TUDataset/infectious_ct1": Source(
        name="TUDataset/infectious_ct1",
        category="real_world",
        description=(
            "200 continuous-time face-to-face contact graphs from the "
            "SocioPatterns 'Infectious' deployment at the Science "
            "Gallery (Dublin, 2009). Each graph is one temporal slice "
            "of contact dyads recorded at 20-second resolution. Average "
            "50 nodes — sensor-collected so dense in raw form (459.7 "
            "edges); will compress under multi-edge collapse."
        ),
        citation=(
            "Isella, L., Stehlé, J., Barrat, A., Cattuto, C., Pinton, "
            "J.-F., & Van den Broeck, W. (2011). What's in a crowd? "
            "Analysis of face-to-face behavioral networks. Journal of "
            "Theoretical Biology 271(1), 166–180. Graph-classification "
            "split: Oettershagen, L., Kriege, N.M., Morris, C., & "
            "Mutzel, P. (2020). Temporal Graph Kernels for "
            "Classifying Dissemination Processes. Proc. SDM 2020."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/infectious_ct1.zip",
        archive_name="infectious_ct1.zip",
        staging_path="staging/TUDataset/infectious_ct1",
    ),
    "TUDataset/tumblr_ct1": Source(
        name="TUDataset/tumblr_ct1",
        category="real_world",
        description=(
            "~373 reblog cascade graphs derived from Tumblr posts. "
            "Each graph is one post's tree of reblogs / interactions "
            "rendered as a continuous-time graph; average 53.11 nodes, "
            "71.63 edges (relatively sparse)."
        ),
        citation=(
            "Oettershagen, L., Kriege, N.M., Morris, C., & Mutzel, P. "
            "(2020). Temporal Graph Kernels for Classifying "
            "Dissemination Processes. Proc. SIAM SDM 2020. Underlying "
            "Tumblr cascades collected via the platform's API; see "
            "the paper for the data-collection protocol."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/tumblr_ct1.zip",
        archive_name="tumblr_ct1.zip",
        staging_path="staging/TUDataset/tumblr_ct1",
    ),
    "TUDataset/dblp_ct1": Source(
        name="TUDataset/dblp_ct1",
        category="real_world",
        description=(
            "~755 ego-collaboration graphs from the DBLP computer-"
            "science bibliography. Each graph is one researcher's "
            "co-authorship neighbourhood as a continuous-time graph. "
            "Average 52.87 nodes, 99.78 edges."
        ),
        citation=(
            "Oettershagen, L., Kriege, N.M., Morris, C., & Mutzel, P. "
            "(2020). Temporal Graph Kernels for Classifying "
            "Dissemination Processes. Proc. SIAM SDM 2020. Underlying "
            "DBLP collaboration data: dblp.org / Ley (2002)."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/dblp_ct1.zip",
        archive_name="dblp_ct1.zip",
        staging_path="staging/TUDataset/dblp_ct1",
    ),
    "suitesparse_small": Source(
        name="suitesparse_small",
        category="real_world",
        description=(
            "Small symmetric matrices (≤ 75 rows, nsym=1.0) from the "
            "SuiteSparse Matrix Collection, interpreted as adjacency "
            "matrices of undirected graphs. Drawn from real scientific-"
            "computing applications: structural FEM, power-grid "
            "analysis, quantum chemistry, network analysis. Staged via "
            "ssgetpy; symmetric filter retains matrices whose "
            "non-zero pattern is genuinely undirected-graph-like."
        ),
        citation=(
            "Davis, T.A. & Hu, Y. (2011). The University of Florida "
            "Sparse Matrix Collection. ACM Transactions on Mathematical "
            "Software 38(1), 1:1–1:25. https://sparse.tamu.edu/"
        ),
    ),

    # ---- real_world: domain-grouped sources added 2026-04 ----
    "food_webs": Source(
        name="food_webs",
        category="real_world",
        description=(
            "Small ecological predator-prey networks from three mirrors "
            "(Netzschleuder, KONECT, and networkrepository). Each graph "
            "is one ecosystem's observed trophic web; predator-prey "
            "direction is coerced undirected since our readability "
            "metrics assume undirected drawings. Most graphs staged "
            "here exceed our n ≤ 75 cap and will be filtered at "
            "promotion; the small handful that fit are valuable for "
            "covering the 'ecological network' structural regime."
        ),
        citation=(
            "Per-ecosystem citations in PER_GRAPH_CITATIONS.md. "
            "Key references: Martinez (1991), Little Rock Lake; "
            "Ulanowicz et al. (1998), South Florida ecosystems."
        ),
        staging_path="staging/biology/food_webs",
    ),
    # social_observational was a curated SNA-classics slice of Netzschleuder
    # (4 hand-picked entries). Folded into `netzschleuder` on 2026-04-24
    # because it was strict-subset duplication once `netzschleuder` started
    # pulling every single-net catalog entry. The 3 graphs that passed
    # promotion (taro/galaskiewicz/padgett-business; krackhardt was always
    # density-rejected) now live in graphs/real_world/netzschleuder/. See
    # RESEARCH_LOG.md §10.10 for the audit trail.

    # Netzschleuder multi-net catalogs. Each entry on Netzschleuder whose
    # `analyses` dict is keyed by sub-net name (rather than flat) is an
    # aggregation catalog of separate networks — we ingest the passing
    # sub-nets of each as its own source, grouped under the
    # `graphs/real_world/netzschleuder/<slug>/` parent folder. Source name
    # uses a '/' so `io.graphs_dir` routes correctly; filenames slash-
    # substitute to stay flat (see `promote_benchmark._target_graph_id`).
    # The set-level citation appears in the per-catalog README; no
    # per-sub-net PER_GRAPH_CITATIONS.md sidecar (per-study citations
    # live in the source publications themselves).

    "netzschleuder/dom": Source(
        name="netzschleuder/dom",
        category="real_world",
        description=(
            "DomArchive: a century of peer-reviewed animal-dominance "
            "interaction datasets (Strauss et al. 2022). Each sub-net is "
            "one observational dominance hierarchy — typically a small "
            "group of primates, birds, cattle, fish, or insects with "
            "dyadic aggressive encounters recorded over weeks or months. "
            "A directed edge (i, j) records antagonism with i as winner, "
            "j as loser; we coerce to undirected at promotion. The "
            "archive covers ~435 studies from 1922–2019, broadly "
            "spanning behavioural ecology."
        ),
        citation=(
            "Strauss, E.D., DeCasien, A.R., Galindo, G., Hobson, E.A., "
            "Shizuka, D., & Curley, J.P. (2022). DomArchive: a century "
            "of published dominance data. Philosophical Transactions of "
            "the Royal Society B 377, 20200436. "
            "https://doi.org/10.1098/rstb.2020.0436. Distribution: "
            "Tiago P. Peixoto, \"The Netzschleuder network catalogue "
            "and repository\", https://networks.skewed.de/ (2020). "
            "DOI https://doi.org/10.5281/zenodo.7839981."
        ),
        staging_path="staging/netzschleuder/dom",
    ),
    "netzschleuder/moreno_sociograms": Source(
        name="netzschleuder/moreno_sociograms",
        category="real_world",
        description=(
            "Eight grade-level classroom sociograms from Jacob Moreno's "
            "1934 *Who Shall Survive?* — the foundational work of "
            "sociometry and, by most accounts, the origin of social-"
            "network analysis. Each sub-net is one grade's 'who do you "
            "want to sit next to?' directed friendship graph, with "
            "children limited to two nominations each."
        ),
        citation=(
            "Moreno, J.L. (1934). Who Shall Survive? A New Approach to "
            "the Problem of Human Interrelations. Nervous and Mental "
            "Disease Publishing Co., Washington DC. Digital edition by "
            "Martin Grandjean (2018), https://github.com/grandjeanmartin/"
            "sociograms. Distribution: Tiago P. Peixoto, "
            "\"The Netzschleuder network catalogue and repository\", "
            "https://networks.skewed.de/ (2020). "
            "DOI https://doi.org/10.5281/zenodo.7839981."
        ),
        staging_path="staging/netzschleuder/moreno_sociograms",
    ),
    "netzschleuder/dutch_school": Source(
        name="netzschleuder/dutch_school",
        category="real_world",
        description=(
            "Longitudinal snapshots of friendship ties among Dutch "
            "secondary-school freshmen, 2003–2004. Friendships were "
            "surveyed four times at three-month intervals; edges "
            "indicate student i naming student j as a friend. Same "
            "26-student population tracked across the school year — "
            "useful for studying structural stability of a fixed "
            "population over short-term dynamics."
        ),
        citation=(
            "Snijders, T.A.B., van de Bunt, G.G., & Steglich, C.E.G. "
            "(2010). Introduction to stochastic actor-based models for "
            "network dynamics. Social Networks 32(1), 44–60. "
            "https://doi.org/10.1016/j.socnet.2009.02.004. Data: "
            "http://www.stats.ox.ac.uk/~snijders/siena/tutorial2010_data.htm. "
            "Distribution: Tiago P. Peixoto, \"The Netzschleuder network "
            "catalogue and repository\", https://networks.skewed.de/ "
            "(2020). DOI https://doi.org/10.5281/zenodo.7839981."
        ),
        staging_path="staging/netzschleuder/dutch_school",
    ),
    "netzschleuder/internet_top_pop": Source(
        name="netzschleuder/internet_top_pop",
        category="real_world",
        description=(
            "Point-of-Presence (PoP)-level Internet topology snapshots "
            "from the Internet Topology Zoo — an aggregation of network-"
            "map surveys of academic, research, and commercial "
            "Internet Service Providers worldwide. Each sub-net is one "
            "ISP or research network's PoP-level graph (between IP and "
            "AS granularity), with snapshots spanning ARPANET (1969–72) "
            "through modern-era commercial ISPs (2012). Distinct "
            "structural regime: mostly sparse, near-planar, "
            "geographically-constrained infrastructure graphs."
        ),
        citation=(
            "Knight, S., Nguyen, H.X., Falkner, N., Bowden, R., & "
            "Roughan, M. (2011). The Internet Topology Zoo. IEEE "
            "Journal on Selected Areas in Communications 29(9), "
            "1765–1775. https://doi.org/10.1109/JSAC.2011.111002. "
            "Data: http://www.topology-zoo.org/dataset.html. "
            "Distribution: Tiago P. Peixoto, \"The Netzschleuder "
            "network catalogue and repository\", "
            "https://networks.skewed.de/ (2020). "
            "DOI https://doi.org/10.5281/zenodo.7839981."
        ),
        staging_path="staging/netzschleuder/internet_top_pop",
    ),
    "netzschleuder/moviegalaxies": Source(
        name="netzschleuder/moviegalaxies",
        category="real_world",
        description=(
            "Character co-appearance networks for ~770 movies, "
            "automatically extracted from movie scripts by the "
            "moviegalaxies.com project. Each sub-net is one movie's "
            "social graph: nodes are characters, edges are same-scene "
            "appearances. Thematically overlaps with the existing "
            "`harry_potter` and `star_wars` cooccurrence sources but "
            "covers a much broader corpus of titles, so kept separate "
            "under the netzschleuder/ umbrella."
        ),
        citation=(
            "Kaminski, J., Schober, M., Albaladejo, R., Zastupailo, O., "
            "& Hidalgo, C. (2018). Moviegalaxies: Social Networks in "
            "Movies. Harvard Dataverse V3. "
            "https://doi.org/10.7910/DVN/T4HBA3. "
            "Distribution: Tiago P. Peixoto, \"The Netzschleuder "
            "network catalogue and repository\", "
            "https://networks.skewed.de/ (2020). "
            "DOI https://doi.org/10.5281/zenodo.7839981."
        ),
        staging_path="staging/netzschleuder/moviegalaxies",
    ),

    "netzschleuder": Source(
        name="netzschleuder",
        category="real_world",
        description=(
            "Single-graph catalog entries from the Netzschleuder "
            "network repository that fit our structural filter "
            "(2 ≤ n ≤ 75, connected, undirected-simple density ≤ "
            "density_cap(n)). Broader than `social_observational` — "
            "covers whatever domain (social, biological, neural, "
            "geographical, etc.) happens to ship a small enough single "
            "graph: e.g. the 9-11 terrorist network, the bottlenose "
            "dolphin social network, the macaque cortical connectivity "
            "network, the Blumenau drug-interaction database, the "
            "Illinois high school friendships, Barnes-Burkett elite "
            "affiliations, the contiguous-US state adjacency. "
            "Multi-graph catalog entries (mass collections like "
            "openstreetmap's 91k city road networks, human_brains' "
            "66k individual connectomes, moviegalaxies' ~800 movie "
            "character co-occurrence networks, the Strauss 2022 "
            "animal-dominance archive's ~435 studies) are deliberately "
            "NOT decomposed into their sub-nets here — those are "
            "aggregation catalogs in their own right and belong in "
            "their own dedicated sources if they are to be included "
            "at all. Pre-filter at staging is based on Netzschleuder's "
            "published analyses (num_vertices, num_edges, is_directed, "
            "edge_reciprocity, largest_component_fraction); the "
            "definitive filter applies at promotion time."
        ),
        citation=(
            "Per-network citations in PER_GRAPH_CITATIONS.md. "
            "Repository citation: Tiago P. Peixoto, \"The Netzschleuder "
            "network catalogue and repository\", "
            "https://networks.skewed.de/ (2020). "
            "DOI https://doi.org/10.5281/zenodo.7839981."
        ),
        staging_path="staging/netzschleuder",
    ),
    # `harry_potter` (1 graph) and `star_wars` (5 episodes) were removed
    # 2026-04-24. Standalone cooccurrence-network sources didn't earn
    # their keep once the corpus had IMDB-BINARY (782 actor co-appearance
    # ego-nets) and netzschleuder/moviegalaxies (754 movie-character
    # cooccurrence networks) — both cover the same structural regime at
    # much higher volume. See RESEARCH_LOG.md §10.16. Manifest backup at
    # `output/manifest.csv.pre-cooccurrence-removal-bak`.
    "ieee_pes": Source(
        name="ieee_pes",
        category="real_world",
        description=(
            "Power-grid test systems from the MATPOWER distribution — "
            "every case from `github.com/MATPOWER/matpower/data/` "
            "whose bus count fits our n ≤ 75 cap (around 30 distinct "
            "topologies). Nodes are buses, edges are transmission "
            "lines. Spans classical IEEE test systems (14, 24 RTS, "
            "30, 57 — decades-old community benchmarks), the New "
            "England 39-bus (Pai 1989), two-area Kundur stability "
            "cases, and distribution-network test cases "
            "(Baran-Wu 33 / 69 and relatives). Topology only — no "
            "geographic coordinates in MATPOWER `.m` files; "
            "electrical columns (resistance, reactance, line limits) "
            "are read past to extract the transmission-line edge "
            "list."
        ),
        citation=(
            "Distribution: Zimmerman, R.D., Murillo-Sánchez, C.E., & "
            "Thomas, R.J. (2011). MATPOWER: Steady-State Operations, "
            "Planning, and Analysis Tools for Power Systems Research "
            "and Education. IEEE Transactions on Power Systems 26(1), "
            "12-19. **Each test case has its own origin paper**, "
            "extracted from the `.m` file header comment and listed "
            "in PER_GRAPH_CITATIONS.md — examples: Alsac & Stott 1974 "
            "(case30), Baran & Wu 1989 (case33bw, case69), Bills et "
            "al. 1970 / Pai 1989 (case39, New England), IEEE RTS "
            "Task Force 1979+1999 (case24), Wood & Wollenberg 1996 "
            "(case6ww), Kundur 1994 (case11), Chow 1982 / Schulz et "
            "al. 1974 (case9), Grainger & Stevenson 1994 (case4gs), "
            "Li & Bo 2010 (case5), Das / Das-Kothari-Kalam / Das-"
            "Nagi-Kothari (case12da / 15da / 16am / 28da / 70da), "
            "Baghzouz & Ertem 1990 (case10ba), Civanlar et al. 1988 "
            "(case16ci), Mendoza et al. 2007 (case17me), Grady et "
            "al. 1992 (case18), Battu et al. 2016 (case15nbr / "
            "18nbr), Raju et al. 2012 (case22), Kashem et al. 2000 "
            "(case33mg), Salama & Chikhani 1993 (case34sa), Singh & "
            "Misra 2007 (case38si), Gampa & Das 2015 (case51ga), "
            "Hengsritawat et al. 2012 (case51he), CIGRE Task Force "
            "38.02.08 / Van Cutsem (case60nordic), IEEE-PES-TR18 "
            "(case59 Australian 14-gen), Myint & Naing 2015 "
            "(case74ds), Das 2006 (case70da). Only `case14`, "
            "`case57`, and `case4_dist` have no specific paper in "
            "the .m header — they are IEEE PES community test "
            "cases from the U. Washington Power Systems Test Case "
            "Archive (https://labs.ece.uw.edu/pstca/)."
        ),
        staging_path="staging/transport/power_grid_ieee",
    ),
    "openflights_airports": Source(
        name="openflights_airports",
        category="real_world",
        description=(
            "Per-country airport route networks derived from the "
            "OpenFlights community database. Nodes are airports in "
            "one country, edges are undirected intra-country flight "
            "routes collapsed across airlines. Geographic coordinates "
            "are stripped at staging time to stay topology-only for "
            "the real_world cohort (a geo-positioned variant for "
            "graphs_with_drawings is possible as a later re-stage)."
        ),
        citation=(
            "OpenFlights community database — https://openflights.org "
            "(data files at https://github.com/jpatokal/openflights, "
            "accessed 2026). No academic publication; attribution is "
            "required by licence but there is no associated paper. "
            "Licence: Open Database License (ODbL) 1.0 for database "
            "structure and Database Contents License (DbCL) 1.0 for "
            "contents. Upstream airport data derives from "
            "OurAirports and DAFIF (public domain); route data "
            "derives from Airline Route Mapper (http://arm.64hosts.com/)."
        ),
        staging_path="staging/transport/airports_openflights",
    ),

    # ---- graphs_with_drawings: layout-bearing cohort ----
    "pajek": Source(
        name="pajek",
        category="graphs_with_drawings",
        description=(
            "Classical networks from Vladimir Batagelj's GitHub mirror "
            "of the Pajek sample collection (github.com/bavla/Nets). "
            "Only `.net` files whose `*Vertices` block carries "
            "coordinates for every vertex are staged — topology-only "
            "Pajek files are rejected (no drawing to study). Spans "
            "genealogies, economic networks, social, and citation "
            "networks — whatever the creators chose to hand-lay."
        ),
        citation=(
            "Per-graph citations in PER_GRAPH_CITATIONS.md. The "
            "original Pajek project: Batagelj, V. & Mrvar, A. (1998), "
            "Pajek — Program for Large Network Analysis. Connections "
            "21, 47-57."
        ),
        staging_path="staging-graphs-with-drawings/pajek",
    ),
    "wikipathways": Source(
        name="wikipathways",
        category="graphs_with_drawings",
        description=(
            "Biological pathway diagrams curated by the WikiPathways "
            "community in PathVisio. Each pathway is drawn by hand; "
            "`<Graphics CenterX CenterY Width Height FillColor Color "
            "ShapeType>` attributes on every DataNode encode the "
            "curator's authored layout AND visual styling. Covers "
            "metabolism, signalling, regulatory pathways across eight "
            "species (human, mouse, rat, yeast, C. elegans, "
            "Drosophila, zebrafish, Arabidopsis)."
        ),
        citation=(
            "Kutmon, M. et al. (2016), WikiPathways: capturing the "
            "full diversity of pathway knowledge. Nucleic Acids "
            "Research 44(D1), D488-D494. Licence: CC0."
        ),
        staging_path="staging-graphs-with-drawings/wikipathways",
    ),
    "ndex": Source(
        name="ndex",
        category="graphs_with_drawings",
        description=(
            "Biomedical and biological networks from the NDEx Network "
            "Data Exchange (UCSD / Ideker Lab). Only networks flagged "
            "`hasLayout=true` AND within our n ≤ 75 cap are staged. "
            "Author-submitted layouts — styles vary widely across "
            "submitters. CX1 cartesianLayout aspect and CX2 inline "
            "x/y both supported."
        ),
        citation=(
            "Pratt, D. et al. (2015), NDEx, the Network Data Exchange. "
            "Cell Systems 1(4), 302-305. Per-network rights "
            "recorded in PER_GRAPH_CITATIONS.md."
        ),
        staging_path="staging-graphs-with-drawings/ndex",
    ),
    "gd_collection_v1": Source(
        name="gd_collection_v1",
        category="graphs_with_drawings",
        description=(
            "Drawings submitted to Graph Drawing conference "
            "proceedings (GD98, GD99, and GD00 through GD24). "
            "Author-curated hand-tuned drawings accompanying academic "
            "papers — every layout reflects the authors' intent for "
            "how their algorithm's output should look. Fetched from "
            "https://github.com/hegetim/gd-collection (the `geg/` "
            "subtree), staged in native `.geg` format; promotion "
            "converts to GraphML via geg.read_geg so the cohort has "
            "a uniform reader interface."
        ),
        citation=(
            "Per-drawing citations trace back to the GD proceedings "
            "for each year (Springer LNCS). See "
            "graphdrawing.org/proceedings."
        ),
        url="https://github.com/hegetim/gd-collection",
        staging_path="staging-graphs-with-drawings/gd-collection-v1",
    ),
    "houseofgraphs": Source(
        name="houseofgraphs",
        category="real_world",
        description=(
            "Curated database of \"interesting graphs\" from Ghent "
            "University (https://houseofgraphs.org/). 28,558 graphs "
            "at 2026-04-24, indexed by /meta-directory into 24 named "
            "graph classes (cubic, planar, snarks, fullerenes, "
            "hypohamiltonian, trees, perihamiltonian, nut, cages, "
            "block, cograph, k-path, maximal-triangle-free, "
            "minimal-Cayley/Ramsey, platypus, quartic, …). Topology-"
            "only ingest: the API ships a 2-D `embedding` field on "
            "every graph but it is auto-generated client-side by "
            "cytoscape (cose/spring) at upload time and saved as "
            "userId=0 — not curator-authored — so it is dropped at "
            "staging. Sample-distribution: median n=29, n=16-30 "
            "contains 61%, n=31-75 contains 26%, n>75 effectively "
            "absent. Net value to the corpus: pure-structural "
            "specimens from named graph-theory classes that the "
            "chemistry/social cohorts (TUDataset, Netzschleuder) do "
            "not exercise."
        ),
        citation=(
            "Coolsaet, K., D'hondt, S., & Goedgebeur, J. (2023). "
            "House of Graphs 2.0: A database of interesting graphs "
            "and more. Discrete Applied Mathematics 325, 97-107. "
            "Original release: Brinkmann, G., Coolsaet, K., "
            "Goedgebeur, J., & Melot, H. (2013). House of Graphs: A "
            "database of interesting graphs. Discrete Applied "
            "Mathematics 161(1-2), 311-314."
        ),
        url="https://houseofgraphs.org/api/graphs",
        staging_path="staging/houseofgraphs",
    ),

    "TUDataset/BZR_MD": Source(
        name="TUDataset/BZR_MD",
        category="real_world",
        description=(
            "TUDataset entry `BZR_MD` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Sutherland, J.J., O'Brien, L.A., & Weaver, D.F. (2003). "
        "Spline-fitting with a genetic algorithm: A method for developing "
        "classification structure-activity relationships. Journal of "
        "Chemical Information and Computer Sciences 43(6), 1906-1915. _MD "
        "variant constructed by: Kriege, N. & Mutzel, P. (2012). Subgraph "
        "matching kernels for attributed graphs. In Proc. ICML 2012."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/BZR_MD.zip",
        archive_name="BZR_MD.zip",
        staging_path="staging/TUDataset/BZR_MD",
    ),
    "TUDataset/COLLAB": Source(
        name="TUDataset/COLLAB",
        category="real_world",
        description=(
            "TUDataset entry `COLLAB` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Yanardag, P. & Vishwanathan, S.V.N. (2015). Deep graph kernels. "
        "In Proceedings of the 21st ACM SIGKDD International Conference "
        "on Knowledge Discovery and Data Mining (KDD '15), 1365-1374."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/COLLAB.zip",
        archive_name="COLLAB.zip",
        staging_path="staging/TUDataset/COLLAB",
    ),
    "TUDataset/COLORS-3": Source(
        name="TUDataset/COLORS-3",
        category="real_world",
        description=(
            "TUDataset entry `COLORS-3` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Knyazev, B., Taylor, G.W., & Amer, M.R. (2019). Understanding "
        "attention and generalization in graph neural networks. In "
        "Advances in Neural Information Processing Systems 32 (NeurIPS "
        "2019), 4204-4214."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/COLORS-3.zip",
        archive_name="COLORS-3.zip",
        staging_path="staging/TUDataset/COLORS-3",
    ),
    "TUDataset/DD": Source(
        name="TUDataset/DD",
        category="real_world",
        description=(
            "TUDataset entry `DD` (topology only). Staged via the bulk "
            "pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Dobson, P.D. & Doig, A.J. (2003). Distinguishing enzyme "
        "structures from non-enzymes without alignments. Journal of "
        "Molecular Biology 330(4), 771-783. Graph-kernel benchmark form: "
        "Shervashidze, N., Schweitzer, P., van Leeuwen, E.J., Mehlhorn, "
        "K., & Borgwardt, K.M. (2011). Weisfeiler-Lehman graph kernels. "
        "Journal of Machine Learning Research 12, 2539-2561."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/DD.zip",
        archive_name="DD.zip",
        staging_path="staging/TUDataset/DD",
    ),
    "TUDataset/deezer_ego_nets": Source(
        name="TUDataset/deezer_ego_nets",
        category="real_world",
        description=(
            "TUDataset entry `deezer_ego_nets` (topology only). Staged "
            "via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Rozemberczki, B. & Sarkar, R. (2020). Characteristic functions "
        "on graphs: Birds of a feather, from statistical descriptors to "
        "parametric models. In Proceedings of the 29th ACM International "
        "Conference on Information and Knowledge Management (CIKM '20), "
        "1325-1334. Distributed via Karateclub: Rozemberczki, B., Kiss, "
        "O., & Sarkar, R. (2020). Karate Club: An API oriented "
        "open-source Python framework for unsupervised learning on "
        "graphs. CIKM '20, 3125-3132."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/deezer_ego_nets.zip",
        archive_name="deezer_ego_nets.zip",
        staging_path="staging/TUDataset/deezer_ego_nets",
    ),
    "TUDataset/ER_MD": Source(
        name="TUDataset/ER_MD",
        category="real_world",
        description=(
            "TUDataset entry `ER_MD` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Sutherland, J.J., O'Brien, L.A., & Weaver, D.F. (2003). "
        "Spline-fitting with a genetic algorithm: A method for developing "
        "classification structure-activity relationships. Journal of "
        "Chemical Information and Computer Sciences 43(6), 1906-1915. _MD "
        "variant constructed by: Kriege, N. & Mutzel, P. (2012). Subgraph "
        "matching kernels for attributed graphs. In Proc. ICML 2012."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/ER_MD.zip",
        archive_name="ER_MD.zip",
        staging_path="staging/TUDataset/ER_MD",
    ),
    "TUDataset/facebook_ct1": Source(
        name="TUDataset/facebook_ct1",
        category="real_world",
        description=(
            "TUDataset entry `facebook_ct1` (topology only). Staged via "
            "the bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Oettershagen, L., Kriege, N.M., Morris, C., & Mutzel, P. (2020). "
        "Temporal graph kernels for classifying dissemination processes. "
        "In Proc. SIAM SDM 2020. Underlying Facebook wall-post network: "
        "Viswanath, B., Mislove, A., Cha, M., & Gummadi, K.P. (2009). On "
        "the evolution of user interaction in Facebook. In Proc. 2nd ACM "
        "Workshop on Online Social Networks (WOSN '09), 37-42."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/facebook_ct1.zip",
        archive_name="facebook_ct1.zip",
        staging_path="staging/TUDataset/facebook_ct1",
    ),
    "TUDataset/FRANKENSTEIN": Source(
        name="TUDataset/FRANKENSTEIN",
        category="real_world",
        description=(
            "TUDataset entry `FRANKENSTEIN` (topology only). Staged via "
            "the bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Orsini, F., Frasconi, P., & De Raedt, L. (2015). Graph invariant "
        "kernels. In Proceedings of the 24th International Joint "
        "Conference on Artificial Intelligence (IJCAI '15), 3756-3762. "
        "Constructed by grafting MNIST digit pixel-attributes onto BURSI "
        "mutagenicity scaffolds (Kazius, J., McGuire, R., & Bursi, R. "
        "(2005). J. Med. Chem. 48(1), 312-320)."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/FRANKENSTEIN.zip",
        archive_name="FRANKENSTEIN.zip",
        staging_path="staging/TUDataset/FRANKENSTEIN",
    ),
    "TUDataset/GITHUB_STARGAZERS": Source(
        name="TUDataset/GITHUB_STARGAZERS",
        category="real_world",
        description=(
            "TUDataset entry `GITHUB_STARGAZERS` (topology only). Staged "
            "via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Rozemberczki, B. & Sarkar, R. (2020). Characteristic functions "
        "on graphs: Birds of a feather, from statistical descriptors to "
        "parametric models. In Proceedings of the 29th ACM International "
        "Conference on Information and Knowledge Management (CIKM '20), "
        "1325-1334. Distributed via Karateclub: Rozemberczki, B., Kiss, "
        "O., & Sarkar, R. (2020). Karate Club: An API oriented "
        "open-source Python framework for unsupervised learning on "
        "graphs. CIKM '20, 3125-3132."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/GITHUB_STARGAZERS.zip",
        archive_name="GITHUB_STARGAZERS.zip",
        staging_path="staging/TUDataset/GITHUB_STARGAZERS",
    ),
    "TUDataset/highschool_ct1": Source(
        name="TUDataset/highschool_ct1",
        category="real_world",
        description=(
            "TUDataset entry `highschool_ct1` (topology only). Staged "
            "via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Oettershagen, L., Kriege, N.M., Morris, C., & Mutzel, P. (2020). "
        "Temporal graph kernels for classifying dissemination processes. "
        "In Proc. SIAM SDM 2020. Underlying SocioPatterns high-school "
        "contact data: Mastrandrea, R., Fournet, J., & Barrat, A. (2015). "
        "Contact patterns in a high school: A comparison between data "
        "collected using wearable sensors, contact diaries and friendship "
        "surveys. PLOS ONE 10(9), e0136497."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/highschool_ct1.zip",
        archive_name="highschool_ct1.zip",
        staging_path="staging/TUDataset/highschool_ct1",
    ),
    "TUDataset/IMDB-MULTI": Source(
        name="TUDataset/IMDB-MULTI",
        category="real_world",
        description=(
            "TUDataset entry `IMDB-MULTI` (topology only). Staged via "
            "the bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Yanardag, P. & Vishwanathan, S.V.N. (2015). Deep graph kernels. "
        "In Proceedings of the 21st ACM SIGKDD International Conference "
        "on Knowledge Discovery and Data Mining (KDD '15), 1365-1374."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/IMDB-MULTI.zip",
        archive_name="IMDB-MULTI.zip",
        staging_path="staging/TUDataset/IMDB-MULTI",
    ),
    "TUDataset/mit_ct1": Source(
        name="TUDataset/mit_ct1",
        category="real_world",
        description=(
            "TUDataset entry `mit_ct1` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Oettershagen, L., Kriege, N.M., Morris, C., & Mutzel, P. (2020). "
        "Temporal graph kernels for classifying dissemination processes. "
        "In Proc. SIAM SDM 2020. Underlying MIT Reality Mining Bluetooth "
        "proximity data: Eagle, N. & Pentland, A. (2006). Reality Mining: "
        "Sensing complex social systems. Personal and Ubiquitous "
        "Computing 10(4), 255-268."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/mit_ct1.zip",
        archive_name="mit_ct1.zip",
        staging_path="staging/TUDataset/mit_ct1",
    ),
    "TUDataset/MSRC_21": Source(
        name="TUDataset/MSRC_21",
        category="real_world",
        description=(
            "TUDataset entry `MSRC_21` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Neumann, M., Garnett, R., Bauckhage, C., & Kersting, K. (2016). "
        "Propagation kernels: Efficient graph kernels from propagated "
        "information. Machine Learning 102(2), 209-245. Underlying "
        "image-segmentation data: MSRC v2 21-class semantic-segmentation "
        "benchmark (Microsoft Research Cambridge)."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/MSRC_21.zip",
        archive_name="MSRC_21.zip",
        staging_path="staging/TUDataset/MSRC_21",
    ),
    "TUDataset/Mutagenicity": Source(
        name="TUDataset/Mutagenicity",
        category="real_world",
        description=(
            "TUDataset entry `Mutagenicity` (topology only). Staged via "
            "the bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Kazius, J., McGuire, R., & Bursi, R. (2005). Derivation and "
        "validation of toxicophores for mutagenicity prediction. Journal "
        "of Medicinal Chemistry 48(1), 312-320. Graph-form benchmark via: "
        "Riesen, K. & Bunke, H. (2008). IAM Graph Database Repository for "
        "graph based pattern recognition and machine learning. In Proc. "
        "SSPR & SPR 2008 (LNCS 5342), 287-297."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Mutagenicity.zip",
        archive_name="Mutagenicity.zip",
        staging_path="staging/TUDataset/Mutagenicity",
    ),
    "TUDataset/NCI-H23": Source(
        name="TUDataset/NCI-H23",
        category="real_world",
        description=(
            "TUDataset entry `NCI-H23` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Yan, X., Cheng, H., Han, J., & Yu, P.S. (2008). Mining "
        "significant graph patterns by leap search. In Proc. ACM SIGMOD "
        "2008, 433-444. Underlying screen: NCI/DTP Developmental "
        "Therapeutics Program - non-small cell lung cancer cell line "
        "NCI-H23 anti-cancer screen (PubChem BioAssay)."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/NCI-H23.zip",
        archive_name="NCI-H23.zip",
        staging_path="staging/TUDataset/NCI-H23",
    ),
    "TUDataset/NCI1": Source(
        name="TUDataset/NCI1",
        category="real_world",
        description=(
            "TUDataset entry `NCI1` (topology only). Staged via the bulk "
            "pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Wale, N. & Karypis, G. (2006). Comparison of descriptor spaces "
        "for chemical compound retrieval and classification. In Proc. "
        "IEEE ICDM 2006, 678-689. Underlying screen: PubChem BioAssay AID "
        "83 (NCI human lung tumor cell-line growth-inhibition screen). "
        "Graph-kernel benchmark popularised by: Shervashidze, N., "
        "Schweitzer, P., van Leeuwen, E.J., Mehlhorn, K., & Borgwardt, "
        "K.M. (2011). Weisfeiler-Lehman graph kernels. JMLR 12, "
        "2539-2561."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/NCI1.zip",
        archive_name="NCI1.zip",
        staging_path="staging/TUDataset/NCI1",
    ),
    "TUDataset/NCI109": Source(
        name="TUDataset/NCI109",
        category="real_world",
        description=(
            "TUDataset entry `NCI109` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Wale, N. & Karypis, G. (2006). Comparison of descriptor spaces "
        "for chemical compound retrieval and classification. In Proc. "
        "IEEE ICDM 2006, 678-689. Underlying screen: PubChem BioAssay AID "
        "109 (NCI human ovarian tumor cell-line growth-inhibition "
        "screen). Graph-kernel benchmark popularised by: Shervashidze, "
        "N., Schweitzer, P., van Leeuwen, E.J., Mehlhorn, K., & "
        "Borgwardt, K.M. (2011). Weisfeiler-Lehman graph kernels. JMLR "
        "12, 2539-2561."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/NCI109.zip",
        archive_name="NCI109.zip",
        staging_path="staging/TUDataset/NCI109",
    ),
    "TUDataset/OHSU": Source(
        name="TUDataset/OHSU",
        category="real_world",
        description=(
            "TUDataset entry `OHSU` (topology only). Staged via the bulk "
            "pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Pan, S., Wu, J., Zhu, X., Long, G., & Zhang, C. (2017). Task "
        "sensitive feature exploration and learning for multitask graph "
        "classification. IEEE Transactions on Cybernetics 47(3), 744-758. "
        "Underlying data: ADHD-200 Sample Initiative "
        "(https://fcon_1000.projects.nitrc.org/indi/adhd200/), Oregon "
        "Health & Science University site."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/OHSU.zip",
        archive_name="OHSU.zip",
        staging_path="staging/TUDataset/OHSU",
    ),
    "TUDataset/QM9": Source(
        name="TUDataset/QM9",
        category="real_world",
        description=(
            "TUDataset entry `QM9` (topology only). Staged via the bulk "
            "pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Ramakrishnan, R., Dral, P.O., Rupp, M., & von Lilienfeld, O.A. "
        "(2014). Quantum chemistry structures and properties of 134 kilo "
        "molecules. Scientific Data 1, 140022. Benchmark wrapper for "
        "graph learning: Wu, Z., Ramsundar, B., Feinberg, E.N., et al. "
        "(2018). MoleculeNet: A benchmark for molecular machine learning. "
        "Chemical Science 9(2), 513-530."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/QM9.zip",
        archive_name="QM9.zip",
        staging_path="staging/TUDataset/QM9",
    ),
    "TUDataset/REDDIT-BINARY": Source(
        name="TUDataset/REDDIT-BINARY",
        category="real_world",
        description=(
            "TUDataset entry `REDDIT-BINARY` (topology only). Staged via "
            "the bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Yanardag, P. & Vishwanathan, S.V.N. (2015). Deep graph kernels. "
        "In Proceedings of the 21st ACM SIGKDD International Conference "
        "on Knowledge Discovery and Data Mining (KDD '15), 1365-1374."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/REDDIT-BINARY.zip",
        archive_name="REDDIT-BINARY.zip",
        staging_path="staging/TUDataset/REDDIT-BINARY",
    ),
    "TUDataset/REDDIT-MULTI-12K": Source(
        name="TUDataset/REDDIT-MULTI-12K",
        category="real_world",
        description=(
            "TUDataset entry `REDDIT-MULTI-12K` (topology only). Staged "
            "via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Yanardag, P. & Vishwanathan, S.V.N. (2015). Deep graph kernels. "
        "In Proceedings of the 21st ACM SIGKDD International Conference "
        "on Knowledge Discovery and Data Mining (KDD '15), 1365-1374."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/REDDIT-MULTI-12K.zip",
        archive_name="REDDIT-MULTI-12K.zip",
        staging_path="staging/TUDataset/REDDIT-MULTI-12K",
    ),
    "TUDataset/REDDIT-MULTI-5K": Source(
        name="TUDataset/REDDIT-MULTI-5K",
        category="real_world",
        description=(
            "TUDataset entry `REDDIT-MULTI-5K` (topology only). Staged "
            "via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Yanardag, P. & Vishwanathan, S.V.N. (2015). Deep graph kernels. "
        "In Proceedings of the 21st ACM SIGKDD International Conference "
        "on Knowledge Discovery and Data Mining (KDD '15), 1365-1374."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/REDDIT-MULTI-5K.zip",
        archive_name="REDDIT-MULTI-5K.zip",
        staging_path="staging/TUDataset/REDDIT-MULTI-5K",
    ),
    "TUDataset/Tox21_AhR_training": Source(
        name="TUDataset/Tox21_AhR_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_AhR_training` (topology only). "
            "Staged via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. Aryl "
        "hydrocarbon receptor (AhR) qHTS assay; see also: Huang, R., Xia, "
        "M., Sakamuru, S., et al. (2016). Modelling the Tox21 10K "
        "chemical profiles for in vivo toxicity prediction and mechanism "
        "characterization. Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_AhR_training.zip",
        archive_name="Tox21_AhR_training.zip",
        staging_path="staging/TUDataset/Tox21_AhR_training",
    ),
    "TUDataset/Tox21_AR-LBD_training": Source(
        name="TUDataset/Tox21_AR-LBD_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_AR-LBD_training` (topology only). "
            "Staged via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. Androgen "
        "receptor ligand-binding-domain (AR-LBD) qHTS assay; see also: "
        "Huang, R., Xia, M., Sakamuru, S., et al. (2016). Modelling the "
        "Tox21 10K chemical profiles for in vivo toxicity prediction and "
        "mechanism characterization. Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_AR-LBD_training.zip",
        archive_name="Tox21_AR-LBD_training.zip",
        staging_path="staging/TUDataset/Tox21_AR-LBD_training",
    ),
    "TUDataset/Tox21_AR_training": Source(
        name="TUDataset/Tox21_AR_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_AR_training` (topology only). Staged "
            "via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. Androgen "
        "receptor (AR) qHTS assay; see also: Huang, R., Xia, M., "
        "Sakamuru, S., et al. (2016). Modelling the Tox21 10K chemical "
        "profiles for in vivo toxicity prediction and mechanism "
        "characterization. Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_AR_training.zip",
        archive_name="Tox21_AR_training.zip",
        staging_path="staging/TUDataset/Tox21_AR_training",
    ),
    "TUDataset/Tox21_ARE_training": Source(
        name="TUDataset/Tox21_ARE_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_ARE_training` (topology only). "
            "Staged via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. "
        "Antioxidant response element (ARE) qHTS assay; see also: Huang, "
        "R., Xia, M., Sakamuru, S., et al. (2016). Modelling the Tox21 "
        "10K chemical profiles for in vivo toxicity prediction and "
        "mechanism characterization. Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_ARE_training.zip",
        archive_name="Tox21_ARE_training.zip",
        staging_path="staging/TUDataset/Tox21_ARE_training",
    ),
    "TUDataset/Tox21_aromatase_training": Source(
        name="TUDataset/Tox21_aromatase_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_aromatase_training` (topology only). "
            "Staged via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. Aromatase "
        "(CYP19A1) inhibition qHTS assay; see also: Huang, R., Xia, M., "
        "Sakamuru, S., et al. (2016). Modelling the Tox21 10K chemical "
        "profiles for in vivo toxicity prediction and mechanism "
        "characterization. Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_aromatase_training.zip",
        archive_name="Tox21_aromatase_training.zip",
        staging_path="staging/TUDataset/Tox21_aromatase_training",
    ),
    "TUDataset/Tox21_ATAD5_training": Source(
        name="TUDataset/Tox21_ATAD5_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_ATAD5_training` (topology only). "
            "Staged via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. ATAD5 "
        "genotoxicity qHTS assay; see also: Huang, R., Xia, M., Sakamuru, "
        "S., et al. (2016). Modelling the Tox21 10K chemical profiles for "
        "in vivo toxicity prediction and mechanism characterization. "
        "Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_ATAD5_training.zip",
        archive_name="Tox21_ATAD5_training.zip",
        staging_path="staging/TUDataset/Tox21_ATAD5_training",
    ),
    "TUDataset/Tox21_ER-LBD_training": Source(
        name="TUDataset/Tox21_ER-LBD_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_ER-LBD_training` (topology only). "
            "Staged via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. Estrogen "
        "receptor alpha ligand-binding-domain (ER-LBD) qHTS assay; see "
        "also: Huang, R., Xia, M., Sakamuru, S., et al. (2016). Modelling "
        "the Tox21 10K chemical profiles for in vivo toxicity prediction "
        "and mechanism characterization. Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_ER-LBD_training.zip",
        archive_name="Tox21_ER-LBD_training.zip",
        staging_path="staging/TUDataset/Tox21_ER-LBD_training",
    ),
    "TUDataset/Tox21_ER_training": Source(
        name="TUDataset/Tox21_ER_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_ER_training` (topology only). Staged "
            "via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. Estrogen "
        "receptor alpha (ER) qHTS assay; see also: Huang, R., Xia, M., "
        "Sakamuru, S., et al. (2016). Modelling the Tox21 10K chemical "
        "profiles for in vivo toxicity prediction and mechanism "
        "characterization. Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_ER_training.zip",
        archive_name="Tox21_ER_training.zip",
        staging_path="staging/TUDataset/Tox21_ER_training",
    ),
    "TUDataset/Tox21_HSE_training": Source(
        name="TUDataset/Tox21_HSE_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_HSE_training` (topology only). "
            "Staged via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. Heat-shock "
        "factor response element (HSE) qHTS assay; see also: Huang, R., "
        "Xia, M., Sakamuru, S., et al. (2016). Modelling the Tox21 10K "
        "chemical profiles for in vivo toxicity prediction and mechanism "
        "characterization. Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_HSE_training.zip",
        archive_name="Tox21_HSE_training.zip",
        staging_path="staging/TUDataset/Tox21_HSE_training",
    ),
    "TUDataset/Tox21_MMP_training": Source(
        name="TUDataset/Tox21_MMP_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_MMP_training` (topology only). "
            "Staged via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. "
        "Mitochondrial membrane potential (MMP) qHTS assay; see also: "
        "Huang, R., Xia, M., Sakamuru, S., et al. (2016). Modelling the "
        "Tox21 10K chemical profiles for in vivo toxicity prediction and "
        "mechanism characterization. Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_MMP_training.zip",
        archive_name="Tox21_MMP_training.zip",
        staging_path="staging/TUDataset/Tox21_MMP_training",
    ),
    "TUDataset/Tox21_p53_training": Source(
        name="TUDataset/Tox21_p53_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_p53_training` (topology only). "
            "Staged via the bulk pre-filter pipeline; promotion adds 24 "
            "structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. p53 "
        "stress-response (SFN) qHTS assay; see also: Huang, R., Xia, M., "
        "Sakamuru, S., et al. (2016). Modelling the Tox21 10K chemical "
        "profiles for in vivo toxicity prediction and mechanism "
        "characterization. Nature Communications 7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_p53_training.zip",
        archive_name="Tox21_p53_training.zip",
        staging_path="staging/TUDataset/Tox21_p53_training",
    ),
    "TUDataset/Tox21_PPAR-gamma_training": Source(
        name="TUDataset/Tox21_PPAR-gamma_training",
        category="real_world",
        description=(
            "TUDataset entry `Tox21_PPAR-gamma_training` (topology "
            "only). Staged via the bulk pre-filter pipeline; promotion "
            "adds 24 structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Tox21 Data Challenge 2014. NIH National Center for Advancing "
        "Translational Sciences (NCATS), Tox21 consortium. Database "
        "release; see https://tripod.nih.gov/tox21/challenge/. Peroxisome "
        "proliferator-activated receptor gamma (PPAR-gamma) qHTS assay; "
        "see also: Huang, R., Xia, M., Sakamuru, S., et al. (2016). "
        "Modelling the Tox21 10K chemical profiles for in vivo toxicity "
        "prediction and mechanism characterization. Nature Communications "
        "7, 10425."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Tox21_PPAR-gamma_training.zip",
        archive_name="Tox21_PPAR-gamma_training.zip",
        staging_path="staging/TUDataset/Tox21_PPAR-gamma_training",
    ),
    "TUDataset/TRIANGLES": Source(
        name="TUDataset/TRIANGLES",
        category="real_world",
        description=(
            "TUDataset entry `TRIANGLES` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Knyazev, B., Taylor, G.W., & Amer, M.R. (2019). Understanding "
        "attention and generalization in graph neural networks. In "
        "Advances in Neural Information Processing Systems 32 (NeurIPS "
        "2019), 4204-4214."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/TRIANGLES.zip",
        archive_name="TRIANGLES.zip",
        staging_path="staging/TUDataset/TRIANGLES",
    ),
    "TUDataset/TWITTER-Real-Graph-Partial": Source(
        name="TUDataset/TWITTER-Real-Graph-Partial",
        category="real_world",
        description=(
            "TUDataset entry `TWITTER-Real-Graph-Partial` (topology "
            "only). Staged via the bulk pre-filter pipeline; promotion "
            "adds 24 structural properties per graph for downstream "
            "property-informed sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "UNRESOLVED original-study citation - the TUDataset bibliography "
        "lists this set under the generic 'repository of benchmark graph "
        "datasets' reference with no underlying paper located. "
        "Distributed via the TUDataset collection: Morris, C., Kriege, "
        "N.M., Bause, F., Kersting, K., Mutzel, P., & Neumann, M. (2020). "
        "TUDataset: A collection of benchmark datasets for learning with "
        "graphs. ICML 2020 GRL+ Workshop."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/TWITTER-Real-Graph-Partial.zip",
        archive_name="TWITTER-Real-Graph-Partial.zip",
        staging_path="staging/TUDataset/TWITTER-Real-Graph-Partial",
    ),
    "TUDataset/Yeast": Source(
        name="TUDataset/Yeast",
        category="real_world",
        description=(
            "TUDataset entry `Yeast` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Yan, X., Cheng, H., Han, J., & Yu, P.S. (2008). Mining "
        "significant graph patterns by leap search. In Proc. ACM SIGMOD "
        "2008, 433-444. Underlying screen: NCI/DTP yeast anti-cancer "
        "screen (PubChem BioAssay)."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/Yeast.zip",
        archive_name="Yeast.zip",
        staging_path="staging/TUDataset/Yeast",
    ),
    "TUDataset/ZINC_full": Source(
        name="TUDataset/ZINC_full",
        category="real_world",
        description=(
            "TUDataset entry `ZINC_full` (topology only). Staged via the "
            "bulk pre-filter pipeline; promotion adds 24 structural "
            "properties per graph for downstream property-informed "
            "sampling. See the TUDataset catalog "
            "(https://chrsmrrs.github.io/datasets/) for domain context "
            "and the original-study citation."
        ),
        citation=(
        "Bresson, X. & Laurent, T. (2019). A two-step graph convolutional "
        "decoder for molecule generation. In Workshop on Machine Learning "
        "and the Physical Sciences, NeurIPS 2019. Underlying ZINC "
        "database: Sterling, T. & Irwin, J.J. (2015). ZINC 15 - Ligand "
        "discovery for everyone. Journal of Chemical Information and "
        "Modeling 55(11), 2324-2337."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/ZINC_full.zip",
        archive_name="ZINC_full.zip",
        staging_path="staging/TUDataset/ZINC_full",
    ),
    "TUDataset/COIL-DEL": Source(
        name="TUDataset/COIL-DEL",
        category="graphs_with_drawings",
        description=(
            "TUDataset entry `COIL-DEL` with curator/source-provided 2D "
            "node coordinates parsed from `COIL-DEL_node_attributes.txt` "
            "(cols 0-1) and stored as `x`/`y` node attrs. Routed to the "
            "`graphs_with_drawings` cohort. See the TUDataset catalog "
            "for domain context."
        ),
        citation=(
        "Nene, S.A., Nayar, S.K., & Murase, H. (1996). Columbia Object "
        "Image Library (COIL-100). Technical Report CUCS-006-96, "
        "Department of Computer Science, Columbia University. Graph "
        "extraction (Delaunay triangulation of image keypoints): Riesen, "
        "K. & Bunke, H. (2008). IAM Graph Database Repository for graph "
        "based pattern recognition and machine learning. In Proc. SSPR & "
        "SPR 2008 (LNCS 5342), 287-297."
        ),
        url="https://www.chrsmrrs.com/graphkerneldatasets/COIL-DEL.zip",
        archive_name="COIL-DEL.zip",
        staging_path="staging-graphs-with-drawings/TUDataset/COIL-DEL",
    ),
}


def get(name: str) -> Source:
    try:
        return SOURCES[name]
    except KeyError as e:
        raise KeyError(
            f"unknown source {name!r}. Registered: {sorted(SOURCES)}"
        ) from e


def by_category(category: str) -> list[Source]:
    return [s for s in SOURCES.values() if s.category == category]
