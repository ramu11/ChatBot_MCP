"""
pdf_to_markdown.py

Purpose
-------
This script converts Red Hat product PDF documentation into structured
Markdown format using `marker-pdf`.

Why this exists
----------------
Running `marker_single` manually for every PDF becomes difficult as the
number of products, versions, and guides increases.

This utility automates the ingestion process by:

1. Scanning all PDFs recursively from:
      rag/raw_pdfs/

2. Converting PDFs into Markdown using:
      marker_single

3. Preserving the same folder hierarchy inside:
      rag/processed_markdown/

4. Skipping already processed PDFs

5. Continuing processing even if one PDF fails

Example
-------
Input:
    rag/raw_pdfs/streams_for_apache_kafka/3.2/file.pdf

Output:
    rag/processed_markdown/streams_for_apache_kafka/3.2/file/

Generated output typically includes:
    - .md file
    - extraction metadata
    - extracted images

Architecture Role
-----------------
This is part of the OFFLINE ingestion pipeline.

Pipeline Flow:
    PDFs
      ↓
    Markdown Extraction   ← THIS FILE
      ↓
    Semantic Chunking
      ↓
    Embeddings
      ↓
    Chroma Vector Store
      ↓
    Retrieval

Important
---------
This script only performs PDF → Markdown conversion.

It does NOT:
    - create embeddings
    - chunk documents
    - store vectors
    - perform retrieval
"""

import subprocess
from pathlib import Path
import re
import hashlib
import shutil


# Source location containing all Red Hat product PDFs
RAW_PDF_DIR = Path("rag/raw_pdfs")

# Destination location for generated markdown content
OUTPUT_DIR = Path("rag/processed_markdown")


# ----------------------------
# PDF HASH TRACKING (NEW)
# ----------------------------

def hash_pdf(pdf_path: Path) -> str:
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_hash_file(output_dir: Path) -> Path:
    return output_dir / ".pdf_hash"


def is_up_to_date(pdf_path: Path, expected_output_dir: Path, current_hash: str) -> bool:
    md_files = list(expected_output_dir.rglob("*.md"))

    if not md_files:
        return False

    hash_file = get_hash_file(expected_output_dir)

    if not hash_file.exists():
        return False

    try:
        stored_hash = hash_file.read_text().strip()
    except Exception:
        return False

    return stored_hash == current_hash


# ----------------------------
# POST CLEANUP (FIXED - IMPORTANT)
# ----------------------------

def clean_marker_output(text: str) -> str:
    if not text:
        return ""

    # remove page artifacts
    text = re.sub(r"page\s+\d+\s+of\s+\d+", "", text, flags=re.IGNORECASE)

    # remove marker noise headings
    text = re.sub(r"^\.\.\.\s*$", "", text, flags=re.MULTILINE)

    # REMOVE YAML/CRD LEAKS (your real issue)
    text = re.sub(
        r"^\s*(singular|plural|shortNames|apiVersion|kind|metadata|spec|status|subresources):.*$",
        "",
        text,
        flags=re.MULTILINE
    )

    # REMOVE BROKEN TABLE ROW ARTIFACTS
    text = re.sub(r"\n\|\s*\d+\s*\n", "\n", text)

    # normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def has_meaningful_content(md_path: Path, pre_cleaned_text: str = None) -> bool:
    # Use memory cache context if available to completely fix double disk operations
    if pre_cleaned_text is not None:
        content = pre_cleaned_text
    else:
        try:
            content = md_path.read_text(encoding="utf-8")
            content = clean_marker_output(content)
        except Exception:
            return False

    words = content.split()

    # stronger rejection rule (fixes garbage MD passing validation)
    if len(words) < 60:
        return False

    return True


# ----------------------------
# CORE CONVERSION
# ----------------------------

def convert_pdf(pdf_path: Path):

    relative_path = pdf_path.relative_to(RAW_PDF_DIR)

    output_path = OUTPUT_DIR / relative_path.parent
    pdf_name = pdf_path.stem

    expected_output_dir = output_path / pdf_name

    # Calculate PDF hash once to optimize tracking lookups
    pdf_hash = hash_pdf(pdf_path)

    # SMART SKIP (UNCHANGED LOGIC, but safer validation)
    if is_up_to_date(pdf_path, expected_output_dir, pdf_hash):
        print(f"[SKIP] Up-to-date: {pdf_path}")
        return

    output_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        "marker_single",
        str(pdf_path),
        "--output_dir",
        str(output_path)
    ]

    print(f"[INFO] Processing: {pdf_path}")

    try:
        # Prevent diagnostic logs from polluting run script outputs
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        md_files = list(expected_output_dir.rglob("*.md"))

        if not md_files:
            print(f"[WARN] No markdown generated: {pdf_path}")
            return

        # Tracks generated files status for final validation
        validations = []

        # CLEAN OUTPUTS (IMPORTANT FIX)
        for md in md_files:
            try:
                cleaned = clean_marker_output(md.read_text(encoding="utf-8"))
                md.write_text(cleaned, encoding="utf-8")
                
                # Check directly using current tracking memory state 
                validations.append(has_meaningful_content(md, pre_cleaned_text=cleaned))
            except Exception:
                validations.append(False)

        # FINAL VALIDATION
        if not any(validations):
            print(f"[WARN] Low quality output: {pdf_path}")
            # Wipe corrupt output dir cleanly to prevent bad data skips
            shutil.rmtree(expected_output_dir, ignore_errors=True)
            return

        # WRITE HASH ONLY AFTER SUCCESS
        hash_file = get_hash_file(expected_output_dir)
        hash_file.write_text(pdf_hash)

        print(f"[SUCCESS] Converted: {pdf_path}")

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to process: {pdf_path}")
        if e.stderr:
            print(e.stderr.strip())


# ----------------------------
# PIPELINE
# ----------------------------

def process_all_pdfs():

    pdf_files = list(RAW_PDF_DIR.rglob("*.pdf"))

    if not pdf_files:
        print("[INFO] No PDF files found.")
        return

    print(f"[INFO] Found {len(pdf_files)} PDF files")

    for pdf_file in pdf_files:
        convert_pdf(pdf_file)

    print("[INFO] PDF ingestion completed.")


# ----------------------------
# MAIN
# ----------------------------

if __name__ == "__main__":
    process_all_pdfs()
