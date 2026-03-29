"""
Utility helpers for canonicalizing product and region labels so downstream
metrics can aggregate by a stable identifier.

ขั้นตอนที่รองรับ:
1) Deterministic normalization (lowercase, NFKC, remove punctuation/whitespace)
2) Manual alias / canonical map (first-pass overrides)
3) Blocking-based candidate generation (ลด O(N^2))
4) Fuzzy matchingด้วย RapidFuzz (token_set_ratio, partial_ratio, QRatio)
5) Union-find clustering -> canonical_id + metadata (representative, confidence)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple, Callable, Literal
from collections import defaultdict
import unicodedata
import re

from rapidfuzz import fuzz

from backend.src.utils.segment_normalization import SEGMENT_NORMALIZATION_MAP

EntityType = Literal["product", "region"]


@dataclass
class CanonicalCluster:
    canonical_id: str
    representative: str
    members: List[str]
    confidence: float
    scores: Dict[str, float]


@dataclass
class CanonicalizationResult:
    canonical_map: Dict[str, str]
    clusters: Dict[str, CanonicalCluster]
    normalized_labels: Dict[str, str]


SPECIAL_CHAR_PATTERN = re.compile(r"[^\w\s]", flags=re.UNICODE)
WHITESPACE_PATTERN = re.compile(r"\s+")

COUNTRY_ALIAS_MAP: Dict[str, str] = {
    "u.s.": "united states",
    "us": "united states",
    "usa": "united states",
    "u s": "united states",
    "united states of america": "united states",
    "thailand": "thailand",
    "thai": "thailand",
    "viet nam": "vietnam",
    "korea": "south korea",
    "republic of korea": "south korea",
    "s. korea": "south korea",
    "u.k.": "united kingdom",
    "uk": "united kingdom",
    "england": "united kingdom",
    "scotland": "united kingdom",
    "emea": "europe middle east africa",
    "apac": "asia pacific",
    "greater china": "china",
    "latam": "latin america",
    "mexico": "mexico",
    "na": "north america",
    "n. america": "north america",
    "americas": "americas",
    "anz": "australia new zealand",
}

REGION_CANONICAL_OVERRIDES: Dict[str, str] = {
    "north america": "north_america",
    "united states": "united_states",
    "united kingdom": "united_kingdom",
    "europe middle east africa": "emea",
    "europe": "europe",
    "asia pacific": "apac",
    "latin america": "latin_america",
    "japan": "japan",
    "china": "china",
    "greater china": "china",
    "australia new zealand": "australia_new_zealand",
    "thailand": "thailand",
    "vietnam": "vietnam",
    "south korea": "south_korea",
    "india": "india",
    "canada": "canada",
    "mexico": "mexico",
    "emea": "emea",
    "apac": "apac",
    "americas": "americas",
}

PRODUCT_ALIAS_MAP: Dict[str, str] = {
    # extend SEGMENT_NORMALIZATION_MAP with common synonyms
    **SEGMENT_NORMALIZATION_MAP,
    "microsoft office": "ms office",
    "office 365": "microsoft office",
    "office365": "microsoft office",
    "m365": "microsoft office",
    "azure cloud": "azure",
    "amazon web services": "aws",
    "google cloud platform": "google cloud",
    "alphabet cloud": "google cloud",
    "google workspace": "google workspace",
    "adobe creative cloud": "adobe cc",
    "adobe cc": "adobe creative cloud",
    "salesforce crm": "salesforce",
    "oracle cloud": "oracle cloud",
    "oracle fusion": "oracle cloud",
    "sap s/4hana": "sap s4hana",
    "sap hana": "sap s4hana",
    "iphone": "iphone",
    "ipad": "ipad",
    "mac": "mac",
    "aws": "aws",
}

PRODUCT_CANONICAL_OVERRIDES: Dict[str, str] = {
    "microsoft office": "microsoft_office",
    "ms office": "microsoft_office",
    "microsoft 365": "microsoft_office",
    "office 365": "microsoft_office",
    "azure": "azure_cloud",
    "azure cloud": "azure_cloud",
    "aws": "amazon_web_services",
    "amazon web services": "amazon_web_services",
    "google cloud": "google_cloud_platform",
    "google cloud platform": "google_cloud_platform",
    "google workspace": "google_workspace",
    "adobe creative cloud": "adobe_creative_cloud",
    "adobe cc": "adobe_creative_cloud",
    "salesforce": "salesforce_crm",
    "salesforce crm": "salesforce_crm",
    "oracle cloud": "oracle_cloud",
    "sap s4hana": "sap_s4hana",
    "sap hana": "sap_s4hana",
    "iphone": "apple_iphone",
    "ipad": "apple_ipad",
    "mac": "apple_mac",
}


def _normalize_text(raw: str) -> str:
    if raw is None:
        return ""
    text = unicodedata.normalize("NFKC", str(raw))
    text = text.lower().strip()
    text = SPECIAL_CHAR_PATTERN.sub(" ", text)
    text = WHITESPACE_PATTERN.sub(" ", text)
    return text.strip()


def _apply_first_pass(
    normalized: str,
    entity_type: EntityType,
) -> Tuple[str, str | None]:
    if not normalized:
        return normalized, None
    alias_map: Dict[str, str]
    override_map: Dict[str, str]
    if entity_type == "region":
        alias_map = COUNTRY_ALIAS_MAP
        override_map = REGION_CANONICAL_OVERRIDES
    else:
        alias_map = PRODUCT_ALIAS_MAP
        override_map = PRODUCT_CANONICAL_OVERRIDES

    mapped = alias_map.get(normalized, normalized)

    if entity_type == "product":
        seg_map_val = SEGMENT_NORMALIZATION_MAP.get(mapped)
        if seg_map_val:
            mapped = seg_map_val

    override = override_map.get(mapped)
    if override:
        return mapped, override

    # fall back to mapped text (no canonical override)
    return mapped, None


def _blocking_keys(normalized: str) -> List[str]:
    if not normalized:
        return []
    compact = normalized.replace(" ", "")
    tokens = normalized.split()
    keys = set()
    if len(compact) >= 4:
        keys.add(f"pre::{compact[:4]}")
        keys.add(f"suf::{compact[-4:]}")
    if tokens:
        keys.add("tok::" + "|".join(sorted(tokens[:3])))
        initials = "".join(token[:1] for token in tokens if token)
        if initials:
            keys.add(f"init::{initials}")
    if len(compact) >= 6:
        bigrams = [compact[i : i + 2] for i in range(len(compact) - 1)]
        if bigrams:
            keys.add("bi::" + "|".join(sorted(bigrams[:6])))
    return list(keys)


def _pair_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    scores = [
        fuzz.token_set_ratio(a, b),
        fuzz.partial_ratio(a, b),
        fuzz.QRatio(a, b),
    ]
    return max(scores)


class _UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, a: int, b: int) -> None:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a == root_b:
            return
        if self.rank[root_a] < self.rank[root_b]:
            self.parent[root_a] = root_b
        elif self.rank[root_a] > self.rank[root_b]:
            self.parent[root_b] = root_a
        else:
            self.parent[root_b] = root_a
            self.rank[root_a] += 1


def _representative_slug(label: str, entity_type: EntityType) -> str:
    base = label.strip().lower().replace(" ", "_")
    base = re.sub(r"[^a-z0-9_]+", "", base)
    base = re.sub(r"_+", "_", base).strip("_")
    if entity_type == "region":
        prefix = "region"
    else:
        prefix = "product"
    if not base:
        base = "unknown"
    return f"{prefix}_{base}"


def canonicalize_entities(
    labels: Iterable[str],
    entity_type: EntityType,
    confidence_threshold: float = 90.0,
    weak_threshold: float = 75.0,
) -> CanonicalizationResult:
    """Return canonical ids for labels of the specified entity type."""
    unique_labels = []
    seen: set[str] = set()
    for raw in labels:
        if raw is None:
            continue
        label = str(raw).strip()
        if not label:
            continue
        if label in seen:
            continue
        seen.add(label)
        unique_labels.append(label)

    normalized_lookup: Dict[str, str] = {}
    canonical_map: Dict[str, str] = {}
    pending_indices: List[int] = []
    normalized_items: List[str] = []
    manual_scores: Dict[str, float] = {}

    for idx, label in enumerate(unique_labels):
        normalized = _normalize_text(label)
        normalized_lookup[label] = normalized
        mapped, override = _apply_first_pass(normalized, entity_type)
        normalized_items.append(mapped)
        if override:
            canonical_map[label] = override
            manual_scores[label] = 100.0
        else:
            # Keep for fuzzy clustering
            pending_indices.append(idx)

    if pending_indices:
        blocks: Dict[str, List[int]] = defaultdict(list)
        for idx in pending_indices:
            norm = normalized_items[idx]
            for key in _blocking_keys(norm):
                blocks[key].append(idx)

        uf = _UnionFind(len(normalized_items))
        pair_scores: Dict[Tuple[int, int], float] = {}

        for candidate_indices in blocks.values():
            if len(candidate_indices) < 2:
                continue
            candidate_indices = list(dict.fromkeys(candidate_indices))
            for i in range(len(candidate_indices)):
                for j in range(i + 1, len(candidate_indices)):
                    a_idx = candidate_indices[i]
                    b_idx = candidate_indices[j]
                    if a_idx == b_idx:
                        continue
                    pair_key = (min(a_idx, b_idx), max(a_idx, b_idx))
                    if pair_key in pair_scores:
                        continue
                    score = _pair_similarity(normalized_items[a_idx], normalized_items[b_idx])
                    if score >= confidence_threshold:
                        uf.union(a_idx, b_idx)
                        pair_scores[pair_key] = score
                    elif score >= weak_threshold:
                        # Save score for potential manual review/metadata
                        pair_scores[pair_key] = score

        # Build clusters
        clusters_by_root: Dict[int, List[int]] = defaultdict(list)
        for idx in pending_indices:
            root = uf.find(idx)
            clusters_by_root[root].append(idx)

        clusters_meta: Dict[str, CanonicalCluster] = {}
    else:
        clusters_by_root = {}
        pair_scores = {}
        clusters_meta = {}

    clusters: Dict[str, CanonicalCluster] = {}

    def _resolve_cluster_members(members: List[int]) -> Tuple[str, str, float, Dict[str, float]]:
        if not members:
            slug = _representative_slug("unknown", entity_type)
            return slug, "unknown", 0.0, {}

        labels_in_cluster = [unique_labels[i] for i in members]
        overrides = []
        for lbl in labels_in_cluster:
            canonical_override = canonical_map.get(lbl)
            if canonical_override:
                overrides.append(canonical_override)
        if overrides:
            canonical_id = overrides[0]
            representative = labels_in_cluster[0]
            confidence = 1.0
            scores = {lbl: 100.0 for lbl in labels_in_cluster}
            return canonical_id, representative, confidence, scores

        normalized_labels = [normalized_items[i] for i in members]
        # choose representative as shortest normalized label
        candidate_pairs = [
            (normalized_labels[i], labels_in_cluster[i]) for i in range(len(labels_in_cluster))
        ]
        candidate_pairs.sort(key=lambda tup: (len(tup[0]), tup[0]))
        representative = candidate_pairs[0][1]
        canonical_id = _representative_slug(candidate_pairs[0][0], entity_type)
        scores = {}
        for lbl in labels_in_cluster:
            norm = normalized_lookup.get(lbl, "")
            scores[lbl] = _pair_similarity(norm, normalized_lookup.get(representative, norm))
        if len(labels_in_cluster) == 1:
            confidence = 1.0
        else:
            pairwise = []
            for i in range(len(labels_in_cluster)):
                for j in range(i + 1, len(labels_in_cluster)):
                    a = members[i]
                    b = members[j]
                    score = pair_scores.get((min(a, b), max(a, b)))
                    if score is not None:
                        pairwise.append(score)
            confidence = (sum(pairwise) / (len(pairwise) * 100.0)) if pairwise else 0.85
        return canonical_id, representative, confidence, scores

    handled_indices: set[int] = set()
    for root, member_idxs in clusters_by_root.items():
        canonical_id, representative, confidence, scores = _resolve_cluster_members(member_idxs)
        clusters[canonical_id] = CanonicalCluster(
            canonical_id=canonical_id,
            representative=representative,
            members=[unique_labels[i] for i in member_idxs],
            confidence=float(min(max(confidence, 0.0), 1.0)),
            scores={lbl: scores.get(lbl, 0.0) for lbl in [unique_labels[i] for i in member_idxs]},
        )
        for idx in member_idxs:
            canonical_map[unique_labels[idx]] = canonical_id
            handled_indices.add(idx)

    for idx, label in enumerate(unique_labels):
        if idx in handled_indices:
            continue
        existing = canonical_map.get(label)
        if existing:
            # ensure cluster metadata exists
            cluster = clusters.get(existing)
            if cluster:
                if label not in cluster.members:
                    cluster.members.append(label)
                    cluster.scores[label] = manual_scores.get(label, 100.0)
            else:
                clusters[existing] = CanonicalCluster(
                    canonical_id=existing,
                    representative=label,
                    members=[label],
                    confidence=1.0,
                    scores={label: manual_scores.get(label, 100.0)},
                )
            continue
        # No cluster or direct mapping: create standalone canonical id
        slug = _representative_slug(normalized_items[idx], entity_type)
        canonical_map[label] = slug
        clusters[slug] = CanonicalCluster(
            canonical_id=slug,
            representative=label,
            members=[label],
            confidence=1.0,
            scores={label: 100.0},
        )

    return CanonicalizationResult(
        canonical_map=canonical_map,
        clusters=clusters,
        normalized_labels=normalized_lookup,
    )

