import streamlit as st
import anthropic
import base64
import json

st.set_page_config(page_title="Invoice Part Comparator", page_icon="📄", layout="wide")

st.markdown("""
    <style>
    .diff-header-a { color: #f5a623; font-weight: 600; }
    .diff-header-b { color: #4a9eff; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

st.title("📄 Invoice Part Comparator")
st.caption("Upload PDFs for two projects to find parts unique to each.")

# --- API Key ---
api_key = st.sidebar.text_input("Anthropic API Key", type="password",
    help="Get yours at https://console.anthropic.com")

st.sidebar.markdown("---")
st.sidebar.markdown("**How it works**\n1. Enter your API key\n2. Upload PDFs for each project\n3. Click Compare")

# --- Project columns ---
col_a, col_b = st.columns(2)

with col_a:
    st.markdown("### 🟠 Project A")
    name_a = st.text_input("Project A name", placeholder="e.g. Site A", key="name_a")
    files_a = st.file_uploader("Upload invoices", type="pdf", accept_multiple_files=True, key="files_a")

with col_b:
    st.markdown("### 🔵 Project B")
    name_b = st.text_input("Project B name", placeholder="e.g. Site B", key="name_b")
    files_b = st.file_uploader("Upload invoices", type="pdf", accept_multiple_files=True, key="files_b")

name_a = name_a or "Project A"
name_b = name_b or "Project B"

# --- Extract parts via Claude ---
def extract_parts(client, pdf_bytes, filename):
    b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=(
            "You are an invoice parser. Extract all parts/items/products from the invoice. "
            "Return ONLY a JSON array of objects with 'part_number' and 'description' fields. "
            "If a field is missing, use null. No preamble, no markdown, only valid JSON."
        ),
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                {"type": "text", "text": "Extract all parts/line items from this invoice. Return only JSON."}
            ]
        }]
    )
    text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(text)

def normalize_key(part):
    pn = str(part.get("part_number") or "").strip().upper()
    desc = str(part.get("description") or "").strip().lower()
    return pn or desc

# --- Compare button ---
st.markdown("---")
run = st.button("→ Compare Projects", type="primary", disabled=not (files_a and files_b and api_key))

if not api_key:
    st.info("Enter your Anthropic API key in the sidebar to get started.")
elif not (files_a and files_b):
    st.info("Upload at least one PDF per project to compare.")

if run:
    client = anthropic.Anthropic(api_key=api_key)
    all_parts_a, all_parts_b = [], []

    with st.status("Extracting parts…", expanded=True) as status:
        for f in files_a:
            st.write(f"Reading **{f.name}** ({name_a})…")
            try:
                parts = extract_parts(client, f.read(), f.name)
                all_parts_a.extend(parts)
            except Exception as e:
                st.warning(f"Could not parse {f.name}: {e}")

        for f in files_b:
            st.write(f"Reading **{f.name}** ({name_b})…")
            try:
                parts = extract_parts(client, f.read(), f.name)
                all_parts_b.extend(parts)
            except Exception as e:
                st.warning(f"Could not parse {f.name}: {e}")

        st.write("Comparing…")
        status.update(label="Done!", state="complete")

    # Build key maps
    keys_a = {}
    for p in all_parts_a:
        k = normalize_key(p)
        if k:
            keys_a[k] = p

    keys_b = {}
    for p in all_parts_b:
        k = normalize_key(p)
        if k:
            keys_b[k] = p

    only_in_a = [p for k, p in keys_a.items() if k not in keys_b]
    only_in_b = [p for k, p in keys_b.items() if k not in keys_a]
    total = len(only_in_a) + len(only_in_b)

    st.markdown(f"### Results — **{total}** difference(s) found")

    if total == 0:
        st.success("✅ No unique parts — both projects share the same parts list.")
    else:
        res_a, res_b = st.columns(2)

        with res_a:
            st.markdown(f'<p class="diff-header-a">Only in {name_a} ({len(only_in_a)} parts)</p>', unsafe_allow_html=True)
            if only_in_a:
                st.dataframe(
                    [{"Part Number": p.get("part_number") or "—", "Description": p.get("description") or "—"} for p in only_in_a],
                    use_container_width=True, hide_index=True
                )
            else:
                st.caption("None")

        with res_b:
            st.markdown(f'<p class="diff-header-b">Only in {name_b} ({len(only_in_b)} parts)</p>', unsafe_allow_html=True)
            if only_in_b:
                st.dataframe(
                    [{"Part Number": p.get("part_number") or "—", "Description": p.get("description") or "—"} for p in only_in_b],
                    use_container_width=True, hide_index=True
                )
            else:
                st.caption("None")
