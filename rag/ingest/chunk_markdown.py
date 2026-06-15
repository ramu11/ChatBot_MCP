import json
import re
import hashlib
from pathlib import Path


"""
chunk_markdown.py (Production RAG Chunker - v2)

Upgrades:
---------
1. Markdown repair layer (fixes marker-pdf artifacts)
2. Structural normalization (code/YAML/list recovery)
3. Better heading detection (removes "...", NOTE noise)
4. CRD/YAML-aware grouping
5. Safer chunk boundaries (no broken configs)
6. Stable deterministic hashing
"""


# ----------------------------
# PATH CONFIG
# ----------------------------

MARKDOWN_ROOT = Path("rag/processed_markdown")
CHUNKS_ROOT = Path("rag/chunks")


# ----------------------------
# CHUNK CONFIG
# ----------------------------

MAX_WORDS = 800
OVERLAP_WORDS = 120


SKIP_SECTIONS = {
    "legal notice",
    "table of contents",
    "preface",
    "making open source more inclusive",
}


# ----------------------------
# 1. MARKDOWN REPAIR LAYER (NEW - CRITICAL)
# ----------------------------

def repair_markdown(text: str) -> str:
    """
    Fixes marker-pdf structural corruption BEFORE chunking.
    """

    if not text:
        return ""

    # Remove broken headings
    text = re.sub(r"^\.\.\.\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^#+\s*\.\.\.\s*$", "", text, flags=re.MULTILINE)

    # Fix NOTE-only sections becoming headings
    text = re.sub(r"^\s*NOTE\s*$", "", text, flags=re.MULTILINE)

    # Remove orphan CRD/YAML keys that appear alone
    text = re.sub(r"^\s*(singular|plural|shortNames|apiVersion|kind|metadata|spec):\s*$",
                  "", text, flags=re.MULTILINE)

    # Fix broken list artifacts
    text = re.sub(r"^\s*-\s*\d+\s*$", "", text, flags=re.MULTILINE)

    # Normalize spacing
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ----------------------------
# CLEANING UTILITIES
# ----------------------------

def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\\_", "_")
    text = text.replace("\\*", "*")
    text = text.replace("\\`", "`")

    text = re.sub(r"<span.*?</span>", "", text, flags=re.DOTALL)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"page\s+\d+\s+of\s+\d+", "", text, flags=re.IGNORECASE)

    # FIXED: Replaced standard space compression to clean only trailing line spaces.
    # This preserves structural indentation for config manifests and code blocks.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def clean_markdown(text: str) -> str:
    text = repair_markdown(text)
    text = clean_text(text)
    return text.strip()


# ----------------------------
# DEDUP (STABLE ACROSS RUNS)
# ----------------------------

def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ----------------------------
# TYPE DETECTION (IMPROVED)
# ----------------------------

def detect_chunk_type(text: str, section: str) -> str:
    t = text.lower()

    yaml_signals = [
        "apiVersion", "kind:", "metadata:", "spec:",
        "openAPIV3Schema", "subresources", "validation", "properties"
    ]

    if any(s in text for s in yaml_signals):
        return "config"

    if "```" in text:
        return "code"

    if section.strip().lower() == "note":
        return "note"

    if (
        "procedure" in section.lower()
        or re.search(r"^\s*\d+\.", text)
        or "oc " in t
    ):
        return "procedure"

    return "explanation"


# ----------------------------
# NOISE FILTER (STRICTER)
# ----------------------------

def is_noise_chunk(text: str) -> bool:
    if not text.strip():
        return True

    if text.strip() in {"...", "-", "—", "NOTE"}:
        return True

    words = text.split()

    if len(words) < 8:
        if not any(c in text for c in ["=", "{", "}", ":", "-", "```"]):
            return True

    if text.count("|") > 40:
        return True

    return False


# ----------------------------
# OVERLAP SPLITTER (SAFE)
# ----------------------------

def split_large_section(text: str):
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current = []
    current_words = 0

    for para in paragraphs:
        w = len(para.split())

        if current_words + w > MAX_WORDS and current:

            chunk = "\n\n".join(current)
            chunks.append(chunk)

            overlap_tokens = chunk.split()[-OVERLAP_WORDS:]
            overlap = " ".join(overlap_tokens) if overlap_tokens else ""

            current = [overlap, para] if overlap else [para]
            current_words = len(overlap.split()) + w if overlap else w

        else:
            current.append(para)
            current_words += w

    if current:
        chunks.append("\n\n".join(current))

    return chunks


# ----------------------------
# SECTION PARSER (FIXED)
# ----------------------------

def parse_markdown_sections(markdown_text: str):
    lines = markdown_text.splitlines()

    sections = []
    current_heading = "Introduction"
    current_content = []

    heading_pattern = re.compile(r"^\s*(#+)\s*(.+\S)")

    for line in lines:

        match = heading_pattern.match(line)

        if match:

            heading = clean_text(match.group(2)).strip()

            # DROP INVALID HEADINGS
            if heading in {"...", "NOTE", ""}:
                continue

            if current_content:
                content = "\n".join(current_content).strip()
                if content:
                    sections.append((current_heading, content))

            current_heading = heading
            current_content = []

        else:
            current_content.append(line)

    if current_content:
        content = "\n".join(current_content).strip()
        if content:
            sections.append((current_heading, content))

    return sections


# ----------------------------
# CHUNK BUILDER
# ----------------------------

def build_chunks(md_file: Path):

    print(f"[INFO] Processing: {md_file}")

    text = md_file.read_text(encoding="utf-8")
    text = clean_markdown(text)

    sections = parse_markdown_sections(text)

    chunks = []

    relative_path = md_file.relative_to(MARKDOWN_ROOT)

    product = relative_path.parts[0]
    version = relative_path.parts[1]
    guide = md_file.stem

    global_id = 1
    
    # FIXED: Instantiated locally per document to ensure boilerplate paragraphs 
    # are shared correctly across completely isolated manuals.
    seen_hashes = set()

    for section, content in sections:

        if section.lower() in SKIP_SECTIONS:
            continue

        # PERFORMANCE ENHANCEMENT: Removed redundant inner loop structural cleanup operations
        for chunk in split_large_section(content):

            if is_noise_chunk(chunk):
                continue

            h = hash_text(chunk)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            ctype = detect_chunk_type(chunk, section)

            final_text = (
                f"[Product: {product}] "
                f"[Version: {version}] "
                f"[Guide: {guide}] "
                f"[Section: {section}] "
                f"[Type: {ctype}]\n\n"
                f"{chunk}"
            )

            chunk_id = hash_text(final_text)

            chunks.append({
                "id": chunk_id,
                "chunk_hash": chunk_id,
                "content": final_text,
                "metadata": {
                    "product": product,
                    "version": version,
                    "guide": guide,
                    "section": section,
                    "chunk_type": ctype,
                    "source_file": md_file.name,
                    "chunk_index": global_id
                }
            })

            global_id += 1

    print(f"[INFO] Generated {len(chunks)} chunks")

    return chunks


# ----------------------------
# SAVE + PIPELINE (UNCHANGED)
# ----------------------------

def save_chunks(md_file: Path, chunks: list):

    out_dir = CHUNKS_ROOT / md_file.relative_to(MARKDOWN_ROOT).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    out_file = out_dir / f"{md_file.stem}_chunks.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] Saved: {out_file}")


def process_all_markdown():

    files = list(MARKDOWN_ROOT.rglob("*.md"))

    if not files:
        print("[INFO] No markdown found.")
        return

    print(f"[INFO] Found {len(files)} files")

    for f in files:
        try:
            chunks = build_chunks(f)
            save_chunks(f, chunks)
        except Exception as e:
            print(f"[ERROR] {f}: {e}")

    print("[INFO] Done.")


if __name__ == "__main__":
    process_all_markdown()
