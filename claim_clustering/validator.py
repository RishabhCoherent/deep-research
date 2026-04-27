"""LLM-powered post-cluster validation: detect and split incoherent clusters.

After tuple-based clustering, some clusters still mix unlike claims because the
LLM extractor missed entity/segment/time distinctions in the original article
(e.g. "industry shipped 34M, AMD shipped 4M, NVIDIA shipped 30M" all extracted
with entity="global"). Tuple matching can't catch these — they share the same
canonical key but measure different things.

This module re-examines each "suspicious" cluster (multi-claim, contested
spread) and asks an LLM:
    "Are these claims measuring exactly the same thing? If not, regroup them."

Output: a possibly-larger list of proto-clusters, each more coherent.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .clusterer import _ProtoCluster
from .extractor import _get_client
from .models import ClaimDimension, RawClaim


# A cluster is "suspicious" if it has >= 3 claims AND a wide spread, OR
# >= 2 claims with widely different raw_text subjects. These are the only
# clusters worth spending an LLM call on.
_MIN_CLAIMS_TO_CHECK = 3
_MIN_SPREAD_TO_CHECK = 0.40    # 40%


_VALIDATOR_SYSTEM = """You are a claim-clustering validator. You receive a set
of numeric claims that an upstream system grouped together as "the same
measurement". Your job is to confirm or split.

Two claims belong in the SAME group iff they measure THE SAME THING. They
are DIFFERENT (and must be split) if any of these axes differ between them:

  - SUBJECT/ENTITY differs (a specific entity is never the same as an
    aggregate; a sub-cohort is never the same as the parent population).
  - SEGMENT/SUB-SCOPE differs (a sub-product / sub-population / sub-region
    / sub-class is not the same as its parent).
  - TIME SLICE differs (a quarter is not a full year; a snapshot is not
    cumulative; one calendar year is not another).
  - METRIC_KIND differs (two different measurements are not the same just
    because they have similar units).
  - UNIT FAMILY differs (already enforced upstream — don't worry about this).

These axes apply across all domains (market research, clinical research,
policy analysis, social science, etc.) — do NOT assume the cluster is about
markets specifically.

If ALL claims in the input belong together, return a single group.
If they should be split, emit a group per coherent subset.

INPUT format:
  {"claims": [{"id": 0, "value": 8.4, "unit": "units_M", "raw_text": "..."}, ...]}

OUTPUT format (return JSON object):
  {"groups": [
     {
       "subject": "<short label naming the coherent measurement>",
       "claim_ids": [0, 2],
       "reason": "<one sentence why these belong together>"
     },
     {"subject": "...", "claim_ids": [1], "reason": "..."}
  ]}

EVERY input claim_id MUST appear in exactly one output group. Do not invent
claim_ids that weren't in the input. Do not duplicate ids across groups.
"""


def _looks_suspicious(cluster: _ProtoCluster) -> bool:
    """Decide whether this cluster is worth re-examining."""
    n = len(cluster.claims)
    if n < _MIN_CLAIMS_TO_CHECK:
        return False
    values = [c.value for c in cluster.claims]
    if not values:
        return False
    mean_v = sum(values) / len(values)
    if mean_v == 0:
        return n >= _MIN_CLAIMS_TO_CHECK   # zero-mean clusters are weird, check
    spread = (max(values) - min(values)) / abs(mean_v)
    return spread >= _MIN_SPREAD_TO_CHECK


def _claims_payload(cluster: _ProtoCluster) -> str:
    """Compact JSON payload for the LLM."""
    items = []
    for i, c in enumerate(cluster.claims):
        items.append({
            "id": i,
            "value": round(c.value, 4),
            "unit": c.unit_family,
            "descriptor": (c.descriptor or "")[:200],
            "qualifiers": dict(c.qualifiers or {}),
            "raw_text": (c.raw_text or "")[:300],
            "source_domain": c.source_domain,
        })
    return json.dumps({
        "cluster_descriptor": cluster.dimension.descriptor[:200],
        "cluster_qualifier_summary": dict(cluster.dimension.qualifier_summary or {}),
        "claims": items,
    }, ensure_ascii=False)


def _parse_validator_output(raw: str) -> Optional[list[dict]]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return None
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        return None
    return groups


def _split_cluster_via_groups(
    cluster: _ProtoCluster, groups: list[dict],
) -> list[_ProtoCluster]:
    """Apply a validator's grouping back onto the proto-cluster.

    Each group becomes a new _ProtoCluster. The new dimension's `descriptor`
    is taken from the validator's "subject" field (its proposed name for the
    sub-group), with the original cluster's unit_family preserved.
    """
    n = len(cluster.claims)
    used: set[int] = set()
    new_clusters: list[_ProtoCluster] = []
    for grp in groups:
        ids = grp.get("claim_ids") or []
        if not isinstance(ids, list):
            continue
        valid_ids = [i for i in ids if isinstance(i, int) and 0 <= i < n and i not in used]
        if not valid_ids:
            continue
        used.update(valid_ids)
        subject = (grp.get("subject") or "").strip()[:300]
        # Pick a representative descriptor: validator's subject if substantive,
        # else first claim's own descriptor.
        if not subject or len(subject) < 5:
            subject = cluster.claims[valid_ids[0]].descriptor or cluster.dimension.descriptor

        new_dim_kwargs = cluster.dimension.model_dump()
        new_dim_kwargs["descriptor"] = subject[:400]
        # Refresh qualifier_summary from the actual members in this split group
        members = [cluster.claims[i] for i in valid_ids]
        agg: dict[str, set[str]] = {}
        for m in members:
            for k, v in (m.qualifiers or {}).items():
                if not k or v is None or v == "":
                    continue
                agg.setdefault(k, set()).add(str(v))
        new_dim_kwargs["qualifier_summary"] = {k: sorted(v) for k, v in agg.items()}
        new_dim = ClaimDimension(**new_dim_kwargs)
        proto = _ProtoCluster(dimension=new_dim)
        for i in valid_ids:
            proto.add(cluster.claims[i])
        new_clusters.append(proto)

    # Salvage unassigned claims into one residual cluster keeping orig dim
    leftover = [i for i in range(n) if i not in used]
    if leftover:
        proto = _ProtoCluster(dimension=cluster.dimension)
        for i in leftover:
            proto.add(cluster.claims[i])
        new_clusters.append(proto)

    return new_clusters or [cluster]


def validate_and_split(
    clusters: list[_ProtoCluster],
    *,
    model: str = "gpt-4o-mini",
    on_progress=None,
) -> list[_ProtoCluster]:
    """Run the LLM validator over suspicious clusters and split where needed.

    Non-suspicious clusters pass through untouched. Returns a list that may
    be longer than the input (due to splits) but never shorter.
    """
    log = on_progress or (lambda _msg: None)
    out: list[_ProtoCluster] = []
    n_checked = 0
    n_split = 0
    n_added_clusters = 0

    for cluster in clusters:
        if not _looks_suspicious(cluster):
            out.append(cluster)
            continue
        n_checked += 1
        try:
            response = _get_client().chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _VALIDATOR_SYSTEM},
                    {"role": "user", "content": _claims_payload(cluster)},
                ],
                temperature=0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            log(f"[validator] LLM error on cluster {cluster.dimension.key()[:60]}: {exc}")
            out.append(cluster)
            continue

        groups = _parse_validator_output(response.choices[0].message.content or "")
        if not groups or len(groups) < 2:
            # Validator agreed it's one cluster (or returned nothing useful)
            out.append(cluster)
            continue

        # Split applied
        new_clusters = _split_cluster_via_groups(cluster, groups)
        if len(new_clusters) > 1:
            n_split += 1
            n_added_clusters += len(new_clusters) - 1
        out.extend(new_clusters)

    log(f"[validator] checked {n_checked}, split {n_split}, added {n_added_clusters} new clusters")
    return out
