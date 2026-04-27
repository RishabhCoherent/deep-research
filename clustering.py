"""Article clustering — K-Means + LDA hybrid, fully self-contained.

Mode A: K-Means on OpenAI Embeddings (hard clustering, semantic)
Mode B: LDA Topic Modeling on TF-IDF (soft clustering, probabilistic)
Mode C: Hybrid — hard cluster labels from A + soft topic distribution from B

Outputs cluster_report.json with hard + soft assignments.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Callable

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score, silhouette_samples
from sklearn.preprocessing import normalize

from backend.enrichment.common import log, get_connection, preprocess_text

logger = logging.getLogger(__name__)


# =========================================================================
# DATA LOADING
# =========================================================================

def load_articles(db_path: str) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT id, title, summary, content, source, feed_name, url, "
        "published_at, matched_keywords FROM articles"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_embeddings(run_dir: str) -> tuple[np.ndarray, list[int]]:
    matrix = np.load(os.path.join(run_dir, "embeddings.npy"))
    with open(os.path.join(run_dir, "embeddings_ids.json")) as f:
        ids = json.load(f)
    return matrix, ids


def build_corpus(articles: list[dict]) -> list[str]:
    """Build cleaned text corpus using title + summary + full content."""
    corpus = []
    for art in articles:
        parts = [art["title"] or "", art["summary"] or "", art["content"] or ""]
        raw = " ".join(parts)
        corpus.append(preprocess_text(raw))
    return corpus


# =========================================================================
# MODE A — K-Means on OpenAI Embeddings
# =========================================================================

def _apply_cached_clusters(db_path: str, articles: list[dict], report: dict) -> None:
    """Re-apply cluster labels from a cached report to the DB."""
    conn = get_connection(db_path)
    # Build article_id → cluster_label mapping from report
    id_to_label: dict[int, str] = {}
    for cluster in report.get("clusters", []):
        label = cluster["label"]
        for art in cluster.get("articles", []):
            id_to_label[art["id"]] = label

    # Columns created by init_db in collector.py — no ALTER TABLE needed

    for art in articles:
        label = id_to_label.get(art["id"], "")
        if label:
            conn.execute("UPDATE articles SET cluster_label=%s WHERE id=%s", (label, art["id"]))
    conn.commit()
    conn.close()
    logger.info("Applied cached cluster labels to %d articles", len(id_to_label))


def _detect_elbow(ks: list[int], inertias: list[float]) -> int:
    """Kneedle algorithm: find K where adding more clusters gives diminishing returns."""
    x = np.array(ks, dtype=float)
    y = np.array(inertias, dtype=float)
    x_norm = (x - x.min()) / (x.max() - x.min())
    y_norm = (y - y.min()) / (y.max() - y.min())
    p1 = np.array([x_norm[0], y_norm[0]])
    p2 = np.array([x_norm[-1], y_norm[-1]])
    line_vec = p2 - p1
    line_len = np.linalg.norm(line_vec)
    line_unit = line_vec / line_len
    distances = []
    for i in range(len(x_norm)):
        point = np.array([x_norm[i], y_norm[i]])
        vec = point - p1
        proj_len = np.dot(vec, line_unit)
        proj = p1 + proj_len * line_unit
        dist = np.linalg.norm(point - proj)
        distances.append(dist)
    return ks[int(np.argmax(distances))]


def find_optimal_k(data_matrix: np.ndarray, k_min: int = 3, k_max: int = 50) -> tuple[int, dict]:
    """Scan K values using elbow method on inertia (fast — no silhouette during scan)."""
    n_samples = data_matrix.shape[0]
    k_max = min(k_max, n_samples - 1)
    # Smart range: step by 2 for small ranges, 3 for large
    step = 2 if k_max <= 30 else 3
    scan_ks = list(range(k_min, k_max + 1, step))
    if k_max not in scan_ks:
        scan_ks.append(k_max)
    results: dict[int, dict] = {}

    logger.info("Scanning K = %d to %d (step=%d, %d points)...", k_min, k_max, step, len(scan_ks))

    for k in scan_ks:
        km = KMeans(n_clusters=k, n_init=3, max_iter=200, random_state=42)
        km.fit(data_matrix)
        results[k] = {"inertia": km.inertia_}
        logger.info("  K=%d  inertia=%.1f", k, km.inertia_)

    ks = sorted(results.keys())
    inertias = [results[k]["inertia"] for k in ks]
    elbow_k = _detect_elbow(ks, inertias)

    logger.info("Elbow at K = %d", elbow_k)
    return elbow_k, results


def run_kmeans(embeddings: np.ndarray, k: int) -> tuple:
    normed = normalize(embeddings)
    km = KMeans(n_clusters=k, n_init=5, max_iter=300, random_state=42)
    labels = km.fit_predict(normed)
    sil = silhouette_score(normed, labels, metric="cosine")
    sil_samples = silhouette_samples(normed, labels, metric="cosine")
    return km, labels, sil, sil_samples, normed


def label_clusters_from_tfidf(
    labels: np.ndarray, tfidf_matrix, vectorizer: TfidfVectorizer, n_terms: int = 10
) -> dict[int, dict]:
    """Auto-label each embedding cluster using TF-IDF term weights."""
    terms = vectorizer.get_feature_names_out()
    n_clusters = len(set(labels))
    cluster_info: dict[int, dict] = {}

    for cid in range(n_clusters):
        mask = labels == cid
        cluster_vectors = tfidf_matrix[mask]
        mean_tfidf = np.asarray(cluster_vectors.mean(axis=0)).flatten()
        top_indices = mean_tfidf.argsort()[::-1][:n_terms]
        top_terms = [terms[i] for i in top_indices]
        top_scores = [float(mean_tfidf[i]) for i in top_indices]

        label = " / ".join(top_terms[:3]).title()
        cluster_info[cid] = {
            "label": label,
            "top_terms": top_terms,
            "top_scores": top_scores,
        }

    return cluster_info


# =========================================================================
# MODE B — LDA Topic Modeling
# =========================================================================

def find_optimal_lda_topics(tfidf_matrix, t_min: int = 5, t_max: int = 30) -> tuple[int, dict]:
    """Test topic counts and pick the one where topics are most balanced."""
    results: dict[int, dict] = {}
    best_ratio = float("inf")
    best_t = t_min

    logger.info("Searching optimal topic count (%d to %d)...", t_min, t_max)

    for t in range(t_min, t_max + 1, 2):
        lda = LatentDirichletAllocation(
            n_components=t, max_iter=25, learning_method="online",
            random_state=42, n_jobs=-1,
        )
        doc_topics = lda.fit_transform(tfidf_matrix)
        primary = doc_topics.argmax(axis=1)
        counts = np.bincount(primary, minlength=t)
        avg_size = len(primary) / t
        max_size = counts.max()
        dominance = max_size / avg_size
        perp = lda.perplexity(tfidf_matrix)
        results[t] = {"dominance": dominance, "perplexity": perp, "max_topic_pct": max_size / len(primary)}
        logger.info(
            "  topics=%d  dominance=%.2f  largest=%d/%d (%.0f%%)  perplexity=%.1f%s",
            t, dominance, max_size, len(primary), max_size / len(primary) * 100, perp,
            " <-- best" if dominance < best_ratio else "",
        )

        if dominance < best_ratio:
            best_ratio = dominance
            best_t = t

    logger.info("Best topic count = %d (dominance ratio = %.2f)", best_t, best_ratio)
    return best_t, results


def run_lda(tfidf_matrix, vectorizer: TfidfVectorizer, n_topics: int | None = None) -> tuple:
    """LDA: each article is a mixture of topics. Auto-detects optimal count if n_topics is None."""
    lda_search_results = None
    if n_topics is None:
        n_topics, lda_search_results = find_optimal_lda_topics(tfidf_matrix)

    logger.info("Fitting final LDA with %d topics...", n_topics)
    lda = LatentDirichletAllocation(
        n_components=n_topics,
        max_iter=50,
        learning_method="online",
        random_state=42,
        n_jobs=-1,
    )
    doc_topic_dist = lda.fit_transform(tfidf_matrix)

    terms = vectorizer.get_feature_names_out()
    topic_info: dict[int, dict] = {}
    for tid in range(n_topics):
        top_indices = lda.components_[tid].argsort()[::-1][:10]
        top_terms = [terms[i] for i in top_indices]
        top_weights = [float(lda.components_[tid][i]) for i in top_indices]
        label = " / ".join(top_terms[:3]).title()
        topic_info[tid] = {"label": label, "top_terms": top_terms, "top_weights": top_weights}

    perplexity = lda.perplexity(tfidf_matrix)
    logger.info("Final LDA perplexity: %.1f", perplexity)
    return lda, doc_topic_dist, topic_info, lda_search_results


# =========================================================================
# SAVE RESULTS
# =========================================================================

def save_to_db(
    db_path: str,
    articles: list[dict],
    labels: np.ndarray,
    cluster_info: dict[int, dict],
    doc_topic_dist: np.ndarray,
    topic_info: dict[int, dict],
) -> None:
    conn = get_connection(db_path)
    # Columns created by init_db in collector.py — no ALTER TABLE needed

    for i, art in enumerate(articles):
        cid = int(labels[i])
        topic_dist = {
            topic_info[tid]["label"]: round(float(doc_topic_dist[i, tid]), 4)
            for tid in range(doc_topic_dist.shape[1])
            if doc_topic_dist[i, tid] > 0.05
        }
        conn.execute(
            "UPDATE articles SET cluster_id=%s, cluster_label=%s, topic_distribution=%s WHERE id=%s",
            (cid, cluster_info[cid]["label"], json.dumps(topic_dist, ensure_ascii=False), art["id"]),
        )

    conn.commit()
    conn.close()
    logger.info("Cluster + topic assignments saved to database.")


def export_report(
    run_dir: str,
    articles: list[dict],
    labels: np.ndarray,
    cluster_info: dict[int, dict],
    sil_score: float,
    doc_topic_dist: np.ndarray,
    topic_info: dict[int, dict],
) -> None:
    n_topics = doc_topic_dist.shape[1]
    report: dict = {
        "total_articles": len(articles),
        "num_clusters": len(cluster_info),
        "silhouette_score": round(sil_score, 4),
        "clustering_method": "K-Means on OpenAI text-embedding-3-small",
        "topic_model": f"LDA with {n_topics} topics",
        "clusters": [],
        "lda_topics": [],
    }

    for cid in sorted(cluster_info.keys()):
        mask = [i for i, l in enumerate(labels) if l == cid]
        cluster_articles = []
        for i in mask:
            top_topic_idx = int(doc_topic_dist[i].argmax())
            cluster_articles.append({
                "id": articles[i]["id"],
                "title": articles[i]["title"],
                "source": articles[i]["source"],
                "url": articles[i]["url"],
                "published_at": articles[i]["published_at"],
                "primary_lda_topic": topic_info[top_topic_idx]["label"],
                "topic_confidence": round(float(doc_topic_dist[i].max()), 4),
            })
        report["clusters"].append({
            "cluster_id": cid,
            "label": cluster_info[cid]["label"],
            "size": len(mask),
            "top_terms": cluster_info[cid]["top_terms"],
            "articles": cluster_articles,
        })

    for tid in sorted(topic_info.keys()):
        report["lda_topics"].append({
            "topic_id": tid,
            "label": topic_info[tid]["label"],
            "top_terms": topic_info[tid]["top_terms"],
            "article_count": int((doc_topic_dist.argmax(axis=1) == tid).sum()),
        })

    report_path = os.path.join(run_dir, "cluster_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("Saved: %s", report_path)


# =========================================================================
# MAIN PIPELINE
# =========================================================================

def _embeddings_hash(run_dir: str) -> str:
    """Hash based on embeddings file size + article IDs (stable across copies)."""
    emb_path = os.path.join(run_dir, "embeddings.npy")
    ids_path = os.path.join(run_dir, "embeddings_ids.json")
    size = os.path.getsize(emb_path)
    ids_hash = ""
    if os.path.exists(ids_path):
        with open(ids_path) as f:
            ids_hash = hashlib.md5(f.read().encode()).hexdigest()[:12]
    return f"{size}_{ids_hash}"


def run_pipeline(db_path: str, run_dir: str, force_k: int | None = None) -> dict:
    """Run the full clustering pipeline. Returns the cluster report dict."""
    logger.info("ARTICLE CLUSTERING PIPELINE v2 — Embeddings + K-Means + LDA Hybrid")

    # --- Check shared cache (data_dir level, survives across runs) ---
    report_path = os.path.join(run_dir, "cluster_report.json")
    shared_dir = os.path.dirname(run_dir)  # data_dir
    shared_report = os.path.join(shared_dir, "shared_cluster_report.json")
    shared_key = os.path.join(shared_dir, "shared_cluster_cache_key.txt")
    emb_path = os.path.join(run_dir, "embeddings.npy")

    if os.path.exists(emb_path) and os.path.exists(shared_report) and os.path.exists(shared_key) and not force_k:
        current_key = _embeddings_hash(run_dir)
        with open(shared_key) as f:
            cached_key = f.read().strip()
        if current_key == cached_key:
            logger.info("Embeddings unchanged — reusing cached clustering results")
            import shutil
            shutil.copy2(shared_report, report_path)
            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)
            # Re-apply cluster assignments to DB
            articles = load_articles(db_path)
            if articles and report.get("clusters"):
                _apply_cached_clusters(db_path, articles, report)
            return {
                "num_clusters": report.get("num_clusters", 0),
                "silhouette_score": report.get("silhouette_score", 0),
                "total_articles": len(articles),
            }

    # --- Load ---
    logger.info("[1/7] Loading articles...")
    articles = load_articles(db_path)
    logger.info("  %d articles loaded", len(articles))

    if len(articles) < 10:
        logger.warning("Not enough articles (%d). Need at least 10.", len(articles))
        return {"num_clusters": 0, "error": "not_enough_articles"}

    logger.info("[2/7] Loading OpenAI embeddings...")
    emb_path = os.path.join(run_dir, "embeddings.npy")
    if not os.path.exists(emb_path):
        logger.error("embeddings.npy not found in %s. Run embedder first.", run_dir)
        return {"num_clusters": 0, "error": "missing_embeddings"}
    embeddings, emb_ids = load_embeddings(run_dir)
    logger.info("  Embeddings: %s", embeddings.shape)

    id_to_idx = {aid: i for i, aid in enumerate(emb_ids)}
    art_indices = [id_to_idx[a["id"]] for a in articles if a["id"] in id_to_idx]
    articles = [a for a in articles if a["id"] in id_to_idx]
    embeddings = embeddings[art_indices]

    # --- TF-IDF ---
    logger.info("[3/7] Building TF-IDF from full article text...")
    corpus = build_corpus(articles)
    vectorizer = TfidfVectorizer(
        max_features=5000, min_df=2, max_df=0.85,
        ngram_range=(1, 2), sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(corpus)
    logger.info("  TF-IDF: %s", tfidf_matrix.shape)

    # --- Mode A: K-Means ---
    logger.info("[4/7] MODE A — K-Means on OpenAI Embeddings...")
    normed = normalize(embeddings)
    k_results = None
    if force_k:
        best_k = force_k
        logger.info("  Using forced K = %d", best_k)
    else:
        best_k, k_results = find_optimal_k(normed)

    km, labels, sil, sil_samples_arr, normed = run_kmeans(embeddings, best_k)
    logger.info("  SILHOUETTE SCORE: %.4f", sil)

    # --- Label clusters ---
    logger.info("[5/7] Auto-labeling clusters from TF-IDF terms...")
    cluster_info = label_clusters_from_tfidf(labels, tfidf_matrix, vectorizer)

    # --- Mode B: LDA ---
    logger.info("[6/7] MODE B — LDA Topic Modeling...")
    # Use K-means cluster count as topic count (skip expensive LDA search)
    lda, doc_topic_dist, topic_info, lda_search = run_lda(tfidf_matrix, vectorizer, n_topics=best_k)

    # --- Save ---
    logger.info("[7/7] Saving results...")
    save_to_db(db_path, articles, labels, cluster_info, doc_topic_dist, topic_info)
    export_report(run_dir, articles, labels, cluster_info, sil, doc_topic_dist, topic_info)

    # Log summary
    for cid in sorted(cluster_info.keys()):
        count = int((labels == cid).sum())
        logger.info("  Cluster %d: %s (%d articles)", cid, cluster_info[cid]["label"], count)

    # Save to shared cache for reuse across runs
    try:
        import shutil
        shutil.copy2(report_path, os.path.join(shared_dir, "shared_cluster_report.json"))
        with open(os.path.join(shared_dir, "shared_cluster_cache_key.txt"), "w") as f:
            f.write(_embeddings_hash(run_dir))
    except Exception:
        pass

    logger.info("DONE — %d clusters, silhouette=%.4f", len(cluster_info), sil)

    return {
        "num_clusters": len(cluster_info),
        "silhouette_score": round(sil, 4),
        "total_articles": len(articles),
    }


# =========================================================================
# PIPELINE STEP
# =========================================================================

class ClustererStep:
    name = "clustering"
    progress_start = 40
    progress_end = 50

    def run(self, context: dict, on_progress: Callable[[str], None]) -> dict:
        if mock := context.get("_mock"):
            clusters_meta = mock.load("clusters")
            n = clusters_meta.get("n_clusters", 4)
            assignments = clusters_meta.get("assignments", {})
            conn = get_connection(context["db_path"])
            rows = conn.execute("SELECT id FROM articles ORDER BY id").fetchall()
            for i, row in enumerate(rows):
                conn.execute("UPDATE articles SET categories = %s WHERE id = %s",
                             (str(assignments.get(str(i), i % n)), row["id"]))
            conn.commit()
            conn.close()
            log(on_progress, f"[MOCK] Applied {n} cluster assignments")
            return {**context, "num_clusters": n, "_step_summary": f"[MOCK] {n} clusters"}

        db_path = context["db_path"]
        run_dir = context["run_dir"]

        log(on_progress, "Running article clustering...")
        result = run_pipeline(db_path=db_path, run_dir=run_dir, force_k=context.get("force_k"))

        num_clusters = result.get("num_clusters", 0)
        log(on_progress, f"Clustering complete: {num_clusters} clusters")
        return {**context, "num_clusters": num_clusters, "_step_summary": f"{num_clusters} clusters"}