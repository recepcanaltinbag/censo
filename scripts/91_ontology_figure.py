#!/usr/bin/env python3
"""
Draw the vocabulary: what CENSO inherits, and what it adds.

WHY THE FIGURE IS GENERATED AND NOT DRAWN
-----------------------------------------
A hand-drawn ontology diagram is a claim about the ontology that nothing checks.
The 2018 project figure in attic/ outlived three axiom changes. So the layout
here is authored -- graphviz cannot lay out a semantic argument, and neither can
a force-directed algorithm -- but every EDGE is verified against
ontology/censo-core.ttl and ontology/censo-regulation.ttl before it is drawn,
and a spec edge with no triple behind it stops the build. The figure cannot
drift from the vocabulary; it can only fail to compile.

WHAT THE FIGURE HAS TO SHOW
---------------------------
Not "here are the classes". The reader's question is the one the related-work
section poses: SOSA/SSN already models observations, so what is left to add?
The answer is four commitments, and each is a place where an edge lands
somewhere the inherited model has no edge:

  1. the limit is carried onto the RESULT. This is a three-step story and the
     figure draws all three: ssn-system:DetectionLimit binds it to a SENSOR,
     CHMO binds it to the METHOD as a figure of merit of an assay, and neither
     can say that a particular measurement fell below it. Both are drawn greyed,
     as the positions being displaced;
  2. a result is an INTERVAL, and its lower bound is pinned to 0 by an axiom
     when the observation is censored;
  3. a threshold is a CONDITIONAL judgement -- it carries preconditions, and
     an unmet one yields no verdict rather than a default pass;
  4. compliance is THREE-valued, and the third value is subtyped by the reason
     it was reached.

Inputs  : ontology/censo-core.ttl, ontology/censo-regulation.ttl
Outputs : paper/figures/fig09_ontology_graph.{svg,pdf,png}
          eval/ontology_figure.md

Usage:  python scripts/91_ontology_figure.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from rdflib import Graph, RDF, RDFS, OWL, URIRef

ROOT = Path(__file__).resolve().parent.parent
ONTO = ROOT / "ontology"
FIGS = ROOT / "paper" / "figures"
EVAL = ROOT / "eval"
STEM = "fig09_ontology_graph"

NS = {
    "https://w3id.org/censo/reg/": "cereg:",
    "https://w3id.org/censo/": "censo:",
    "http://www.w3.org/ns/sosa/": "sosa:",
    "http://www.w3.org/ns/ssn/systems/": "ssn-system:",
    "http://www.w3.org/ns/ssn/": "ssn:",
    "http://www.w3.org/ns/prov#": "prov:",
    "http://qudt.org/schema/qudt/": "qudt:",
    "http://www.w3.org/2001/XMLSchema#": "xsd:",
    "http://www.w3.org/2004/02/skos/core#": "skos:",
}

# Print-safe palette: distinguishable in colour, and monotone in lightness so
# the figure still separates when a journal prints it in greyscale.
INHERITED = "#f4f4f4"   # SOSA/SSN/PROV/QUDT -- what was already there
NEW = "#dbe7f3"         # CENSO classes
EPISTEMIC = "#c9dcc9"   # the detection statuses: the epistemic core
OUTCOME = "#f6e3c8"     # the three compliance outcomes
DISPLACED = "#ffffff"   # ssn-system:DetectionLimit, drawn to be displaced

EDGE_SUB = "#555555"
EDGE_OBJ = "#1f4e79"
EDGE_AX = "#8a4b08"


def qname(u) -> str:
    u = str(u)
    for full, pre in NS.items():
        if u.startswith(full):
            return pre + u[len(full):]
    return u


def iri(q: str) -> URIRef:
    for full, pre in NS.items():
        if q.startswith(pre):
            return URIRef(full + q[len(pre):])
    raise SystemExit(f"unknown prefix in {q!r}")


# --------------------------------------------------------------- the spec --
# node id -> (label, fill, tooltip)
NODES = {
    # --- inherited ---------------------------------------------------------
    "sosa:Observation": ("sosa:Observation", INHERITED, ""),
    "sosa:ObservableProperty": ("sosa:ObservableProperty", INHERITED, ""),
    "sosa:Procedure": ("sosa:Procedure", INHERITED, ""),
    "sosa:FeatureOfInterest": ("sosa:FeatureOfInterest", INHERITED, ""),
    "sosa:Sample": ("sosa:Sample", INHERITED, ""),
    "prov:Activity": ("prov:Activity", INHERITED, ""),
    "prov:Entity": ("prov:Entity", INHERITED, ""),
    "qudt:Unit": ("qudt:Unit", INHERITED, ""),
    # --- 1. the limit belongs to the run ------------------------------------
    "censo:Analyte": ("censo:Analyte", NEW, ""),
    "censo:AnalyticalMethod": ("censo:AnalyticalMethod", NEW, ""),
    "censo:Campaign": ("censo:Campaign", NEW, ""),
    # --- 2. detection status ------------------------------------------------
    "censo:AssessedObservation": ("censo:AssessedObservation", EPISTEMIC, ""),
    "censo:CensoredObservation": ("censo:Censored\nObservation", EPISTEMIC, ""),
    "censo:EstimatedObservation": ("censo:Estimated\nObservation", EPISTEMIC, ""),
    "censo:QuantifiedObservation": ("censo:Quantified\nObservation", EPISTEMIC, ""),
    "censo:UnresolvedObservation": ("censo:Unresolved\nObservation", EPISTEMIC, ""),
    "censo:DetectedObservation": ("censo:DetectedObservation", EPISTEMIC, ""),
    # --- 3. thresholds as conditional judgements ----------------------------
    "censo:Threshold": ("censo:Threshold", NEW, ""),
    "censo:AnnualAverageThreshold": ("censo:AnnualAverage\nThreshold", NEW, ""),
    "censo:MaximumAllowableThreshold":
        ("censo:MaximumAllowable\nThreshold", NEW, ""),
    "cereg:GroupThreshold": ("cereg:GroupThreshold", NEW, ""),
    "censo:ApplicabilityCondition": ("censo:ApplicabilityCondition", NEW, ""),
    "censo:MatrixCondition": ("censo:Matrix\nCondition", NEW, ""),
    "censo:HardnessClassCondition": ("censo:HardnessClass\nCondition", NEW, ""),
    "censo:BioavailabilityCondition": ("censo:Bioavailability\nCondition", NEW, ""),
    "censo:Regulation": ("censo:Regulation", NEW, ""),
    "cereg:RegulationPackage": ("cereg:RegulationPackage", NEW, ""),
    # --- 4. three-valued compliance -----------------------------------------
    "censo:ComplianceOutcome": ("censo:ComplianceOutcome", OUTCOME, ""),
    "censo:Compliant": ("censo:Compliant", OUTCOME, ""),
    "censo:Exceedance": ("censo:Exceedance", OUTCOME, ""),
    "censo:IndeterminateCompliance":
        ("censo:IndeterminateCompliance", OUTCOME, ""),
    "censo:MethodInsufficient": ("censo:Method\nInsufficient", OUTCOME, ""),
    "censo:PreconditionUnmet": ("censo:Precondition\nUnmet", OUTCOME, ""),
    "censo:PossibleExceedance": ("censo:Possible\nExceedance", OUTCOME, ""),
    "censo:BoundNotEstablished": ("censo:BoundNot\nEstablished", OUTCOME, ""),
    "censo:NoThresholdDefined": ("censo:NoThreshold\nDefined", OUTCOME, ""),
}

# (child, parent) -- each must appear as an rdfs:subClassOf triple.
SUBCLASS = [
    ("censo:Analyte", "sosa:ObservableProperty"),
    ("censo:AnalyticalMethod", "sosa:Procedure"),
    ("censo:Campaign", "prov:Activity"),
    ("censo:Regulation", "prov:Entity"),
    ("cereg:RegulationPackage", "censo:Regulation"),
    ("censo:AssessedObservation", "sosa:Observation"),
    ("censo:CensoredObservation", "sosa:Observation"),
    ("censo:EstimatedObservation", "sosa:Observation"),
    ("censo:QuantifiedObservation", "sosa:Observation"),
    ("censo:UnresolvedObservation", "sosa:Observation"),
    ("censo:AnnualAverageThreshold", "censo:Threshold"),
    ("censo:MaximumAllowableThreshold", "censo:Threshold"),
    ("cereg:GroupThreshold", "censo:Threshold"),
    ("censo:MatrixCondition", "censo:ApplicabilityCondition"),
    ("censo:HardnessClassCondition", "censo:ApplicabilityCondition"),
    ("censo:BioavailabilityCondition", "censo:ApplicabilityCondition"),
    ("censo:Compliant", "censo:ComplianceOutcome"),
    ("censo:Exceedance", "censo:ComplianceOutcome"),
    ("censo:IndeterminateCompliance", "censo:ComplianceOutcome"),
    ("censo:MethodInsufficient", "censo:IndeterminateCompliance"),
    ("censo:PreconditionUnmet", "censo:IndeterminateCompliance"),
    ("censo:PossibleExceedance", "censo:IndeterminateCompliance"),
    ("censo:BoundNotEstablished", "censo:IndeterminateCompliance"),
    ("censo:NoThresholdDefined", "censo:IndeterminateCompliance"),
]

# (property, tail, head) -- each must have the stated rdfs:domain and rdfs:range.
OBJPROP = [
    ("censo:hasAnalyte", "sosa:Observation", "censo:Analyte"),
    ("censo:determinesAnalyte", "censo:AnalyticalMethod", "censo:Analyte"),
    ("censo:limitUnit", "censo:AnalyticalMethod", "qudt:Unit"),
    ("censo:atStation", "sosa:Observation", "sosa:FeatureOfInterest"),
    ("censo:duringCampaign", "sosa:Observation", "censo:Campaign"),
    ("censo:assessableAgainst", "sosa:Observation", "censo:Threshold"),
    ("censo:appliesToAnalyte", "censo:Threshold", "censo:Analyte"),
    ("censo:requiresCondition", "censo:Threshold", "censo:ApplicabilityCondition"),
    ("censo:requiresCovariate", "censo:ApplicabilityCondition",
     "sosa:ObservableProperty"),
    ("censo:conditionSatisfied", "sosa:Observation",
     "censo:ApplicabilityCondition"),
    ("censo:definedBy", "censo:Threshold", "censo:Regulation"),
    ("censo:thresholdUnit", "censo:Threshold", "qudt:Unit"),
    ("cereg:definesThreshold", "cereg:RegulationPackage", "censo:Threshold"),
]

# The three comparison properties the rule layer materialises. Drawn apart
# because owl:AllDisjointProperties over them is where exclusivity lives.
COMPARISON = ["censo:exceeds", "censo:possiblyExceeds", "censo:belowThreshold"]

# Datatype properties shown on the class they belong to, as a second row in the
# node. (class, [property, ...]) -- each must have that class as rdfs:domain.
ATTRS = {
    "censo:AnalyticalMethod": ["censo:limitOfDetection",
                               "censo:limitOfQuantification"],
    "sosa:Observation": ["censo:resultLowerBound", "censo:resultUpperBound",
                         "censo:reportedValue", "censo:censoringRecovered"],
    "censo:Threshold": ["censo:thresholdValue"],
    "censo:Analyte": ["censo:casNumber"],
}

# Drawn grey and dashed, and NOT put in a cluster of their own -- see the
# layout note in dot().
INHERITED_NODES = ["sosa:Observation", "sosa:ObservableProperty",
                   "sosa:Procedure", "sosa:Sample", "sosa:FeatureOfInterest",
                   "prov:Activity", "prov:Entity", "qudt:Unit"]

# The covering axioms: (named class, the classes it is the union of, marker).
# owl:unionOf in an owl:equivalentClass is what makes a taxonomy EXHAUSTIVE,
# and it is the half a plain subclass diagram cannot show. verify() checks each.
COVERING = [
    ("censo:AssessedObservation",
     ["censo:CensoredObservation", "censo:EstimatedObservation",
      "censo:QuantifiedObservation", "censo:UnresolvedObservation"],
     "&#8801; union of the four"),
    ("censo:DetectedObservation",
     ["censo:EstimatedObservation", "censo:QuantifiedObservation"],
     "&#8801; estimated &#8852; quantified"),
    ("censo:ComplianceOutcome",
     ["censo:Compliant", "censo:Exceedance", "censo:IndeterminateCompliance"],
     "&#8801; union of THREE"),
]

# (cluster id, title, member classes, annotation boxes drawn inside it).
# An annotation is (node id, heading, body, anchor) -- the anchor is unused for
# placement now that the box sits in the cluster, and is kept so the claim each
# box makes is still traceable to the class it is about.
CLUSTERS = [
    ("run", "1 &nbsp; the limit is carried onto the result",
     ["censo:Analyte", "censo:AnalyticalMethod",
      "censo:Campaign"],
     []),
    ("status", "2 &nbsp; the result is an interval, and its epistemic status is explicit",
     ["censo:AssessedObservation", "censo:DetectedObservation",
      "censo:CensoredObservation", "censo:EstimatedObservation",
      "censo:QuantifiedObservation", "censo:UnresolvedObservation"],
     [("ax_disj", "owl:AllDisjointClasses",
       "censored / estimated / quantified / unresolved are disjoint"
       "<BR ALIGN=\"LEFT\"/>AND exhaustive. a row asserted both censored and"
       "<BR ALIGN=\"LEFT\"/>quantified makes the ontology INCONSISTENT."
       "<BR ALIGN=\"LEFT\"/><BR ALIGN=\"LEFT\"/>"
       "a fifth situation &#8212; never measured &#8212; is deliberately"
       "<BR ALIGN=\"LEFT\"/>not a class: under the open world assumption,"
       "<BR ALIGN=\"LEFT\"/>not asserting the observation IS the way to say it"
       "<BR ALIGN=\"LEFT\"/>", "censo:AssessedObservation"),
      ("ax_zero", "CensoredObservation &#8849; resultLowerBound value \"0.0\"",
       "a non-detection permits any value down to zero."
       "<BR ALIGN=\"LEFT\"/>half-LOQ substitution violates this axiom &#8212;"
       "<BR ALIGN=\"LEFT\"/>which is the practice the vocabulary exists to stop"
       "<BR ALIGN=\"LEFT\"/>", "censo:CensoredObservation"),
      ("ax_unres",
       "UnresolvedObservation &#8849; &#172;&#8707;assessableAgainst.Threshold",
       "a row whose detection status cannot be established"
       "<BR ALIGN=\"LEFT\"/>may not be assessed for compliance at all"
       "<BR ALIGN=\"LEFT\"/>", "censo:UnresolvedObservation")]),
    ("thr", "3 &nbsp; a threshold is a conditional judgement, not a number",
     ["censo:Threshold", "censo:AnnualAverageThreshold",
      "cereg:GroupThreshold", "censo:ApplicabilityCondition",
      "censo:HardnessClassCondition", "censo:BioavailabilityCondition",
      "censo:Regulation", "cereg:RegulationPackage"],
     [("ax_cond", "requiresCondition &#8594; ApplicabilityCondition",
       "where a precondition of the standard is unmet there is"
       "<BR ALIGN=\"LEFT\"/>no comparison to make &#8212; not a strict one and"
       "<BR ALIGN=\"LEFT\"/>not a lenient one. the verdict is PreconditionUnmet,"
       "<BR ALIGN=\"LEFT\"/>never a default pass. a threshold column has"
       "<BR ALIGN=\"LEFT\"/>nowhere to record that a limit was inapplicable"
       "<BR ALIGN=\"LEFT\"/>", "censo:ApplicabilityCondition")]),
    ("out", "4 &nbsp; compliance is three-valued, and the third value records why",
     ["censo:ComplianceOutcome", "censo:Compliant", "censo:Exceedance",
      "censo:IndeterminateCompliance", "censo:MethodInsufficient",
      "censo:PreconditionUnmet", "censo:PossibleExceedance",
      "censo:NoThresholdDefined"],
     [("ax_cover", "ComplianceOutcome &#8801; Compliant &#8852; Exceedance "
                   "&#8852; Indeterminate",
       "THREE, not four. an interval straddling the limit decides"
       "<BR ALIGN=\"LEFT\"/>nothing, so PossibleExceedance is a species of"
       "<BR ALIGN=\"LEFT\"/>indeterminacy and not a peer of Exceedance."
       "<BR ALIGN=\"LEFT\"/><BR ALIGN=\"LEFT\"/>"
       "the subclasses are deliberately NOT disjoint from one"
       "<BR ALIGN=\"LEFT\"/>another: one observation may be MethodInsufficient"
       "<BR ALIGN=\"LEFT\"/>against one jurisdiction and PossibleExceedance"
       "<BR ALIGN=\"LEFT\"/>against another&#8217;s standard"
       "<BR ALIGN=\"LEFT\"/>", "censo:ComplianceOutcome")]),
]


# ------------------------------------------------------------ verification --
def verify(g: Graph) -> list[str]:
    """Every drawn edge must be in the ontology. Returns the failures."""
    bad = []
    for c, p in SUBCLASS:
        if (iri(c), RDFS.subClassOf, iri(p)) not in g:
            bad.append(f"rdfs:subClassOf missing: {c} -> {p}")
    for p, d, r in OBJPROP:
        if (iri(p), RDF.type, OWL.ObjectProperty) not in g:
            bad.append(f"not an owl:ObjectProperty: {p}")
            continue
        if (iri(p), RDFS.domain, iri(d)) not in g:
            bad.append(f"rdfs:domain mismatch: {p} is not on {d}")
        if (iri(p), RDFS.range, iri(r)) not in g:
            bad.append(f"rdfs:range mismatch: {p} does not reach {r}")
    for cls, props in ATTRS.items():
        for p in props:
            if (iri(p), RDF.type, OWL.DatatypeProperty) not in g:
                bad.append(f"not an owl:DatatypeProperty: {p}")
            elif (iri(p), RDFS.domain, iri(cls)) not in g:
                bad.append(f"rdfs:domain mismatch: {p} is not on {cls}")
    for p in COMPARISON:
        if (iri(p), RDF.type, OWL.ObjectProperty) not in g:
            bad.append(f"not an owl:ObjectProperty: {p}")
    # The axioms the figure asserts in its own annotations.
    for ax, want in (
        (OWL.AllDisjointClasses,
         {"censo:CensoredObservation", "censo:EstimatedObservation",
          "censo:QuantifiedObservation", "censo:UnresolvedObservation"}),
        (OWL.AllDisjointProperties, set(COMPARISON)),
    ):
        found = False
        for node in g.subjects(RDF.type, ax):
            for m in g.objects(node, OWL.members):
                if {qname(x) for x in g.items(m)} == want:
                    found = True
        if not found:
            bad.append(f"{qname(ax)} over {sorted(want)} not found")
    # The two covering axioms the figure draws as "= A or B or C".
    for cls, want in (
        ("censo:ComplianceOutcome",
         {"censo:Compliant", "censo:Exceedance",
          "censo:IndeterminateCompliance"}),
        ("censo:AssessedObservation",
         {"censo:CensoredObservation", "censo:EstimatedObservation",
          "censo:QuantifiedObservation", "censo:UnresolvedObservation"}),
        ("censo:DetectedObservation",
         {"censo:EstimatedObservation", "censo:QuantifiedObservation"}),
    ):
        found = False
        for eq in g.objects(iri(cls), OWL.equivalentClass):
            for u in g.objects(eq, OWL.unionOf):
                if {qname(x) for x in g.items(u)} == want:
                    found = True
        if not found:
            bad.append(f"{cls} is not the union of {sorted(want)}")
    # Every node the figure draws must be a declared class.
    for n in NODES:
        if n.startswith(("censo:", "cereg:")) and \
                (iri(n), RDF.type, OWL.Class) not in g:
            bad.append(f"not an owl:Class: {n}")
    return bad


# ------------------------------------------------------------------- draw --
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def node_html(nid: str, dashed: bool = False) -> str:
    """A class box; classes with datatype properties get a second compartment.

    `dashed` marks a class CENSO inherits rather than declares. It is the one
    distinction the figure has to carry, so it is carried twice -- by fill and
    by border colour -- and survives a greyscale print.
    """
    label, fill, _ = NODES[nid]
    head = "<BR/>".join(esc(x) for x in label.split("\n"))
    colour = "#bbbbbb" if dashed else "#333333"
    head_col = "#666666" if dashed else "#000000"
    rows = [f'<TR><TD ALIGN="CENTER"><FONT COLOR="{head_col}"><B>{head}</B>'
            f'</FONT></TD></TR>']
    for p in ATTRS.get(nid, []):
        rows.append(f'<TR><TD ALIGN="LEFT">'
                    f'<FONT POINT-SIZE="9">{esc(p)}</FONT></TD></TR>')
    body = "".join(rows)
    return (f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" '
            f'CELLPADDING="4" BGCOLOR="{fill}" COLOR="{colour}">'
            f'{body}</TABLE>>')


def dot() -> str:
    """Emit the DOT source.

    LAYOUT NOTES, because they are decisions and not defaults.

    rankdir=LR. In dot, siblings of a rank stack ALONG the cross-axis, so
    left-to-right stacks the six subclasses of IndeterminateCompliance and the
    four detection statuses vertically instead of spreading them across the
    page. Top-to-bottom put the same content in a 5429x965 strip.

    The inherited classes are NOT in a cluster. They were, and it was the
    worst thing about the first draft: sosa:Observation is the tail of nine
    edges, and pinning it inside a box on the far side of the figure made
    every one of them a long curve across the middle. They are marked by style
    instead -- grey fill, dashed border -- and dot is free to put each one
    beside whatever uses it.

    Subclass edges are written parent -> child with dir=back. The edge
    direction is also the rank direction, so child -> parent would rank the
    inherited classes AFTER the classes that specialise them.
    """
    L = ['digraph CENSO {',
         '  rankdir=LR;',
         '  newrank=true;',
         '  bgcolor="white";',
         '  splines=spline;',
         '  concentrate=false;',
         '  nodesep=0.22;',
         '  ranksep=0.85;',
         '  fontname="Helvetica";',
         '  node [shape=plaintext, fontname="Helvetica", fontsize=11];',
         '  edge [fontname="Helvetica", fontsize=9, color="%s"];' % EDGE_OBJ,
         '']

    # --- inherited classes: styled, not boxed ------------------------------
    for n in INHERITED_NODES:
        L.append(f'  "{n}" [label={node_html(n, dashed=True)}];')
    L.append('  "ssn-system:DetectionLimit" [label=<<TABLE BORDER="0" '
             'CELLBORDER="1" CELLSPACING="0" CELLPADDING="4" '
             f'BGCOLOR="{DISPLACED}" COLOR="#bbbbbb">'
             '<TR><TD><FONT COLOR="#888888">ssn-system:DetectionLimit</FONT>'
             '</TD></TR><TR><TD><FONT POINT-SIZE="9" COLOR="#888888">'
             'a property of the SENSOR</FONT></TD></TR></TABLE>>];')
    L.append('')

    # --- the four commitments ---------------------------------------------
    for cid, title, members, anns in CLUSTERS:
        L.append(f'  subgraph cluster_{cid} {{')
        L.append(f'    label=<<B>{title}</B>>;')
        L.append('    labeljust="l"; fontsize=12; fontcolor="#1f4e79";')
        L.append('    style="rounded"; color="#c3d2e2"; margin=12;')
        for n in members:
            L.append(f'    "{n}" [label={node_html(n)}];')
        # The axiom annotations live INSIDE the cluster whose claim they are.
        # Floating them outside put four boxes in a corner joined to their
        # anchors by dotted lines across the whole figure.
        for nid, head, body, _ in anns:
            L.append(f'    "{nid}" [label=<<TABLE BORDER="0" CELLBORDER="1" '
                     f'CELLSPACING="0" CELLPADDING="6" BGCOLOR="#fbfbf7" '
                     f'COLOR="#b9a97e"><TR><TD ALIGN="LEFT">'
                     f'<FONT POINT-SIZE="9"><B>{head}</B></FONT></TD></TR>'
                     f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="8" '
                     f'COLOR="#444444">{body}</FONT></TD></TR></TABLE>>];')
        L.append('  }')
    L.append('')

    # Pin each annotation to its anchor's rank. Without this dot puts the boxes
    # wherever there is room -- in LR that was a column of its own at the far
    # left of cluster 3, half the figure away from the classes it describes,
    # with the cluster's whole middle left empty.
    for _, _, _, anns in CLUSTERS:
        for nid, _, _, anchor in anns:
            L.append(f'  {{ rank=same; "{anchor}"; "{nid}"; }}')
    L.append('')

    # NOT attempted: invisible edges chaining the four clusters into their
    # numbered order. dot has no notion of cluster sequence, and forcing one
    # this way put the four commitments in a single chain -- 3777x1690, and the
    # clusters came out 2, 4, 3, 1 anyway, because the real edges outweigh the
    # invisible ones. The numbering carries the reading order instead.

    # --- subclass edges ----------------------------------------------------
    for c, p in SUBCLASS:
        L.append(f'  "{p}" -> "{c}" [dir=back, arrowtail=onormal, '
                 f'arrowhead=none, color="{EDGE_SUB}"];')
    L.append('')

    # --- the covering axioms, drawn as edges rather than only asserted -----
    # A subclass edge says "every A is a B". These say "and there is nothing
    # else", which is the half that makes the third compliance value work and
    # the four detection statuses exhaustive.
    for parent, children, note in COVERING:
        for i, ch in enumerate(children):
            lbl = (f'label=<<FONT POINT-SIZE="9" COLOR="#3b7a3b">{note}'
                   f'</FONT>>, ' if i == 0 else "")
            L.append(f'  "{parent}" -> "{ch}" [style=dashed, '
                     f'color="#3b7a3b", arrowhead=none, {lbl}constraint=false];')
    L.append('')

    # --- object properties -------------------------------------------------
    for p, d, r in OBJPROP:
        short = p.split(":", 1)[1] if p.startswith("censo:") else p
        L.append(f'  "{d}" -> "{r}" [label="{short}"];')
    L.append('')

    # --- the rule layer ----------------------------------------------------
    L.append('  "cmp" [label=<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" '
             'CELLPADDING="5" BGCOLOR="#ffffff" COLOR="#8a4b08">'
             '<TR><TD><B>the rule layer materialises</B></TD></TR>'
             + "".join(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="9">{esc(p)}'
                       f'</FONT></TD></TR>' for p in COMPARISON)
             + '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="8" COLOR="#8a4b08">'
               'owl:AllDisjointProperties<BR ALIGN="LEFT"/>'
               'exclusivity is PER observation&#8211;threshold<BR ALIGN="LEFT"/>'
               'pair, so two jurisdictions may<BR ALIGN="LEFT"/>'
               'disagree without contradiction<BR ALIGN="LEFT"/>'
               '<BR ALIGN="LEFT"/>'
               'OWL cannot compare two data values.<BR ALIGN="LEFT"/>'
               'it classifies over these, it does<BR ALIGN="LEFT"/>'
               'not compute them<BR ALIGN="LEFT"/></FONT></TD></TR></TABLE>>];')
    L.append(f'  "sosa:Observation" -> "cmp" [style=dashed, color="{EDGE_AX}", '
             f'arrowhead=none];')
    L.append(f'  "cmp" -> "censo:Threshold" [style=dashed, color="{EDGE_AX}"];')
    L.append(f'  "cmp" -> "censo:ComplianceOutcome" [style=dashed, '
             f'color="{EDGE_AX}"];')
    L.append('')

    # --- the displacement --------------------------------------------------
    L.append('  "chmo:limitOfDetection" [label=<<TABLE BORDER="0" '
             'CELLBORDER="1" CELLSPACING="0" CELLPADDING="4" BGCOLOR="#ffffff" '
             'COLOR="#bbbbbb"><TR><TD><FONT COLOR="#888888">'
             'CHMO:0002801 limit of detection</FONT></TD></TR><TR><TD>'
             '<FONT POINT-SIZE="9" COLOR="#888888">a figure of merit '
             'of the METHOD</FONT></TD></TR></TABLE>>];')
    L.append(f'  "ssn-system:DetectionLimit" -> "chmo:limitOfDetection" '
             f'[style=bold, color="#b03030", penwidth=1.4, '
             f'label=<<FONT POINT-SIZE="9" COLOR="#b03030">'
             f'sensor &#8594; method</FONT>>];')
    L.append(f'  "chmo:limitOfDetection" -> "sosa:Observation" '
             f'[style=bold, color="#b03030", penwidth=1.8, '
             f'label=<<FONT POINT-SIZE="10" COLOR="#b03030">'
             f'<B>what CENSO adds</B><BR/>method &#8594; the RESULT,<BR/>'
             f'as resultUpperBound</FONT>>];')

    L.append('}')
    return "\n".join(L)


def main() -> int:
    g = Graph()
    for f in ("censo-core.ttl", "censo-regulation.ttl"):
        p = ONTO / f
        if not p.exists():
            print(f"  missing {p}")
            return 1
        g.parse(p, format="turtle")

    bad = verify(g)
    if bad:
        print(f"  FAIL the figure draws {len(bad)} edge(s) the ontology "
              f"does not have:")
        for b in bad:
            print(f"        {b}")
        print("  The figure is a claim about the vocabulary. Fix the spec in "
              "this script, or the ontology, but do not draw it.")
        return 1

    FIGS.mkdir(parents=True, exist_ok=True)
    src = dot()
    (FIGS / f"{STEM}.dot").write_text(src, encoding="utf-8")
    for fmt in ("svg", "pdf", "png"):
        out = FIGS / f"{STEM}.{fmt}"
        r = subprocess.run(["dot", f"-T{fmt}", "-o", str(out)],
                           input=src.encode("utf-8"),
                           stderr=subprocess.PIPE)
        if r.returncode != 0:
            print("  FAIL graphviz:", r.stderr.decode()[:400])
            return 1
        print(f"  wrote paper/figures/{STEM}.{fmt}")

    n_edges = len(SUBCLASS) + len(OBJPROP) + sum(len(v) for v in ATTRS.values())
    EVAL.mkdir(parents=True, exist_ok=True)
    L = ["# The vocabulary figure\n",
         f"Generated by `scripts/91_ontology_figure.py` into "
         f"`paper/figures/{STEM}.svg`.\n",
         "Every edge drawn is verified against `ontology/censo-core.ttl` and "
         "`ontology/censo-regulation.ttl` before the figure is written: a "
         "`rdfs:subClassOf` the ontology does not assert, a property drawn "
         "between a domain and a range it does not declare, or a datatype "
         "property shown on the wrong class stops the build. A hand-drawn "
         "ontology diagram is a claim that nothing checks; this one cannot "
         "drift from the vocabulary.\n",
         "| drawn | n |", "|---|---|",
         f"| classes | {len(NODES)} |",
         f"| `rdfs:subClassOf` edges | {len(SUBCLASS)} |",
         f"| object properties (domain -> range) | {len(OBJPROP)} |",
         f"| datatype properties, on their class | "
         f"{sum(len(v) for v in ATTRS.values())} |",
         f"| edges verified against the TTL | {n_edges} |",
         "",
         "Axioms carried as annotations, each checked to exist:",
         "",
         "- `owl:AllDisjointClasses` over the four detection statuses",
         "- `owl:AllDisjointProperties` over "
         "`exceeds` / `possiblyExceeds` / `belowThreshold`",
         "- `censo:ComplianceOutcome` as the union of **three** outcomes",
         "- `censo:AssessedObservation` as the union of the four statuses",
         "- `censo:DetectedObservation` as estimated or quantified",
         "- `CensoredObservation` &#8849; `resultLowerBound` value `0.0`",
         "- `UnresolvedObservation` &#8849; "
         "&#172;&#8707;`assessableAgainst`.`Threshold`",
         ""]
    (EVAL / "ontology_figure.md").write_text("\n".join(L), encoding="utf-8")
    print(f"  wrote eval/ontology_figure.md")
    print(f"  {n_edges} edge(s) verified against the ontology, 0 unsupported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
