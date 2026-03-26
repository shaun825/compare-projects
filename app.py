import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Invoice Part Comparator", page_icon="📄", layout="wide")

st.title("📄 Invoice Part Comparator")
st.caption("Upload PDFs for two projects to find parts unique to each.")

# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_lines_from_pdf(uploaded_file):
    """Return all non-empty text lines from every page of a PDF."""
    lines = []
    with pdfplumber.open(BytesIO(uploaded_file.read())) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        lines.append(line)
    return lines


# Common invoice header/footer words to skip
SKIP_PATTERN = re.compile(
    r"^(invoice|date|bill to|ship to|total|subtotal|tax|page|po number|"
    r"purchase order|payment|due|qty|quantity|unit price|amount|description|"
    r"item|part\s*#|part no|thank you|terms|notes?|www\.|http)",
    re.IGNORECASE,
)

# Looks like a part number: alphanumeric, often with dashes/dots, 3-20 chars
PART_NUM_RE = re.compile(r"\b([A-Z0-9][A-Z0-9\-\.]{2,19})\b")


def looks_like_part_number(token: str) -> bool:
    """Heuristic: contains both letters and digits, or is all-caps alpha >= 4 chars."""
    has_digit = any(c.isdigit() for c in token)
    has_alpha = any(c.isalpha() for c in token)
    return (has_digit and has_alpha) or (token.isupper() and len(token) >= 4)


def extract_parts_from_lines(lines):
    """
    Parse lines into {'part_number': ..., 'description': ...} dicts.
    Strategy:
      1. Try to find a token that looks like a part number on each line.
      2. The rest of the line (cleaned) becomes the description.
      3. Lines that match skip patterns or are too short are ignored.
    """
    parts = []
    seen_keys = set()

    for line in lines:
        if SKIP_PATTERN.match(line):
            continue
        if len(line) < 4:
            continue

        tokens = line.split()
        part_number = None
        desc_tokens = []

        for tok in tokens:
            cleaned = tok.strip(".,;:()")
            if part_number is None and PART_NUM_RE.fullmatch(cleaned) and looks_like_part_number(cleaned):
                part_number = cleaned
            else:
                if re.search(r"[A-Za-z]", tok):
                    desc_tokens.append(tok)

        description = " ".join(desc_tokens).strip()

        if not part_number and len(description) < 5:
            continue

        key = (part_number or "").upper() or description.lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)

        parts.append({
            "part_number": part_number or "—",
            "description": description or "—",
            "_key": key,
        })

    return parts


def collect_parts(uploaded_files):
    """Extract and deduplicate parts across multiple PDFs."""
    all_parts = []
    seen_keys = set()
    for f in uploaded_files:
        lines = extract_lines_from_pdf(f)
        for part in extract_parts_from_lines(lines):
            if part["_key"] not in seen_keys:
                seen_keys.add(part["_key"])
                all_parts.append(part)
    return all_parts


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("### 🟠 Project A")
    name_a = st.text_input("Project A name", placeholder="e.g. Site A", key="name_a")
    files_a = st.file_uploader("Upload invoices", type="pdf",
                                accept_multiple_files=True, key="files_a")

with col_b:
    st.markdown("### 🔵 Project B")
    name_b = st.text_input("Project B name", placeholder="e.g. Site B", key="name_b")
    files_b = st.file_uploader("Upload invoices", type="pdf",
                                accept_multiple_files=True, key="files_b")

name_a = name_a or "Project A"
name_b = name_b or "Project B"

st.markdown("---")

can_run = bool(files_a and files_b)
run = st.button("→ Compare Projects", type="primary", disabled=not can_run)

if not can_run:
    st.info("Upload at least one PDF per project to compare.")

if run:
    with st.status("Reading invoices…", expanded=True) as status:
        st.write(f"Extracting parts from **{name_a}**…")
        parts_a = collect_parts(files_a)

        st.write(f"Extracting parts from **{name_b}**…")
        parts_b = collect_parts(files_b)

        st.write("Comparing…")

        keys_a = {p["_key"] for p in parts_a}
        keys_b = {p["_key"] for p in parts_b}

        only_in_a = [p for p in parts_a if p["_key"] not in keys_b]
        only_in_b = [p for p in parts_b if p["_key"] not in keys_a]

        status.update(label="Done!", state="complete")

    total = len(only_in_a) + len(only_in_b)
    st.markdown(f"### Results — **{total}** difference(s) found")

    if total == 0:
        st.success("✅ No unique parts — both projects share the same parts list.")
    else:
        res_a, res_b = st.columns(2)

        def to_df(parts):
            return pd.DataFrame([
                {"Part Number": p["part_number"], "Description": p["description"]}
                for p in parts
            ])

        with res_a:
            st.markdown(f"**🟠 Only in {name_a}** — {len(only_in_a)} part(s)")
            if only_in_a:
                st.dataframe(to_df(only_in_a), use_container_width=True, hide_index=True)
            else:
                st.caption("None")

        with res_b:
            st.markdown(f"**🔵 Only in {name_b}** — {len(only_in_b)} part(s)")
            if only_in_b:
                st.dataframe(to_df(only_in_b), use_container_width=True, hide_index=True)
            else:
                st.caption("None")

        # Download buttons
        st.markdown("---")
        dl_a, dl_b = st.columns(2)
        with dl_a:
            if only_in_a:
                csv_a = to_df(only_in_a).to_csv(index=False).encode()
                st.download_button(f"⬇ Download {name_a} differences",
                                   csv_a, f"{name_a}_only.csv", "text/csv")
        with dl_b:
            if only_in_b:
                csv_b = to_df(only_in_b).to_csv(index=False).encode()
                st.download_button(f"⬇ Download {name_b} differences",
                                   csv_b, f"{name_b}_only.csv", "text/csv")
