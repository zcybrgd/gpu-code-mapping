"""
clean_ncu.py
============
Parses NCU CSV from two formats (Jetson Orin / GTX):

  Format A — --print-source sass
      Header starts with: "Address","Source",...

  Format B — --print-source cuda,sass   ← USE THIS ONE
      Header starts with: "Line No","Source","Address","Source",...
      Gives you CUDA-C source line + SASS instruction in same row.

Usage:
    python clean_ncu.py                        # default INPUT_FILE below
    python clean_ncu.py cuda_sass.csv          # or pass as argument
    python clean_ncu.py metric_sass.csv
"""

import sys, csv, io

# ── CONFIG ────────────────────────────────────────────────────────────────────
INPUT_FILE  = "cuda_sass.csv"
OUTPUT_FILE = "clean_output.csv"

if len(sys.argv) > 1:
    INPUT_FILE = sys.argv[1]

# ── COMPLETE ALIAS MAP
# Covers ALL 64 columns from your Jetson cuda_sass.csv output.
# Left  = friendly alias name used in output CSV
# Right = list of possible raw column names (first match wins)
#         Supports both Jetson (stall_long_sb) and GTX (smsp__pcsamp_...) naming
ALIAS_MAP = {
    # ── Warp stall sampling — ALL SAMPLES ────────────────────────────────────
    "warp_stall_all":               ["Warp Stall Sampling (All Samples)"],
    "warp_stall_not_issued":        ["Warp Stall Sampling (Not-issued Samples)"],
    "sample_count":                 ["# Samples",
                                     "smsp__pcsamp_sample_count"],

    # ── Instruction counts ───────────────────────────────────────────────────
    "inst_executed":                ["Instructions Executed",
                                     "smsp__sass_thread_inst_executed"],
    "thread_inst_executed":         ["Thread Instructions Executed",
                                     "smsp__sass_thread_inst_executed_pred_on_threads"],
    "thread_inst_pred_on":          ["Predicated-On Thread Instructions Executed",
                                     "smsp__sass_thread_inst_executed_pred_on"],
    "avg_threads":                  ["Avg. Threads Executed"],
    "avg_threads_pred_on":          ["Avg. Predicated-On Threads Executed"],
    "divergent_branches":           ["Divergent Branches"],

    # ── Memory access info ───────────────────────────────────────────────────
    "address_space":                ["Address Space"],
    "access_operation":             ["Access Operation"],
    "access_size":                  ["Access Size"],

    # ── L1 cache ─────────────────────────────────────────────────────────────
    "l1_tag_global":                ["L1 Tag Requests Global"],
    "l1_conflicts_nway":            ["L1 Conflicts Shared N-Way"],

    # ── L2 cache ─────────────────────────────────────────────────────────────
    "l2_sectors_excess":            ["L2 Theoretical Sectors Global Excessive"],
    "l2_sectors_global":            ["L2 Theoretical Sectors Global"],
    "l2_sectors_ideal":             ["L2 Theoretical Sectors Global Ideal"],
    # L2 explicit evict/hit/miss policies (Jetson-specific columns)
    "l2_evict_policies":            ["L2 Explicit Evict Policies"],
    "l2_hit_evict_first":           ["L2 Explicit Hit Policy Evict First"],
    "l2_hit_evict_last":            ["L2 Explicit Hit Policy Evict Last"],
    "l2_hit_evict_normal":          ["L2 Explicit Hit Policy Evict Normal"],
    "l2_hit_evict_normal_demote":   ["L2 Explicit Hit Policy Evict Normal Demote"],
    "l2_miss_evict_first":          ["L2 Explicit Miss Policy Evict First"],
    "l2_miss_evict_normal":         ["L2 Explicit Miss Policy Evict Normal"],

    # ── Warp stall reasons (All Samples) ─────────────────────────────────────
    "stall_barrier":                ["stall_barrier",
                                     "smsp__pcsamp_warps_issue_stalled_barrier"],
    "stall_branch_resolving":       ["stall_branch_resolving",
                                     "smsp__pcsamp_warps_issue_stalled_branch_resolving"],
    "stall_dispatch":               ["stall_dispatch",
                                     "smsp__pcsamp_warps_issue_stalled_dispatch"],
    "stall_drain":                  ["stall_drain",
                                     "smsp__pcsamp_warps_issue_stalled_drain"],
    "stall_imc":                    ["stall_imc",
                                     "smsp__pcsamp_warps_issue_stalled_imc_miss"],
    "stall_lg":                     ["stall_lg",
                                     "smsp__pcsamp_warps_issue_stalled_lg_throttle"],
    "stall_long_sb":                ["stall_long_sb",
                                     "smsp__pcsamp_warps_issue_stalled_long_scoreboard"],
    "stall_math":                   ["stall_math",
                                     "smsp__pcsamp_warps_issue_stalled_math_pipe_throttle"],
    "stall_membar":                 ["stall_membar",
                                     "smsp__pcsamp_warps_issue_stalled_membar"],
    "stall_mio":                    ["stall_mio",
                                     "smsp__pcsamp_warps_issue_stalled_mio_throttle"],
    "stall_misc":                   ["stall_misc",
                                     "smsp__pcsamp_warps_issue_stalled_misc"],
    "stall_no_inst":                ["stall_no_inst",
                                     "smsp__pcsamp_warps_issue_stalled_no_instruction"],
    "stall_not_selected":           ["stall_not_selected",
                                     "smsp__pcsamp_warps_issue_stalled_not_selected"],
    "stall_selected":               ["stall_selected",
                                     "smsp__pcsamp_warps_issue_stalled_selected"],
    "stall_short_sb":               ["stall_short_sb",
                                     "smsp__pcsamp_warps_issue_stalled_short_scoreboard"],
    "stall_sleep":                  ["stall_sleep",
                                     "smsp__pcsamp_warps_issue_stalled_sleeping"],
    "stall_tex":                    ["stall_tex",
                                     "smsp__pcsamp_warps_issue_stalled_tex_throttle"],
    "stall_wait":                   ["stall_wait",
                                     "smsp__pcsamp_warps_issue_stalled_wait"],

    # ── Warp stall reasons (Not Issued) ──────────────────────────────────────
    "stall_barrier_ni":             ["stall_barrier (Not Issued)"],
    "stall_branch_resolving_ni":    ["stall_branch_resolving (Not Issued)"],
    "stall_dispatch_ni":            ["stall_dispatch (Not Issued)"],
    "stall_drain_ni":               ["stall_drain (Not Issued)"],
    "stall_imc_ni":                 ["stall_imc (Not Issued)"],
    "stall_lg_ni":                  ["stall_lg (Not Issued)"],
    "stall_long_sb_ni":             ["stall_long_sb (Not Issued)"],
    "stall_math_ni":                ["stall_math (Not Issued)"],
    "stall_membar_ni":              ["stall_membar (Not Issued)"],
    "stall_mio_ni":                 ["stall_mio (Not Issued)"],
    "stall_misc_ni":                ["stall_misc (Not Issued)"],
    "stall_no_inst_ni":             ["stall_no_inst (Not Issued)"],
    "stall_not_selected_ni":        ["stall_not_selected (Not Issued)"],
    "stall_selected_ni":            ["stall_selected (Not Issued)"],
    "stall_short_sb_ni":            ["stall_short_sb (Not Issued)"],
    "stall_sleeping_ni":            ["stall_sleeping (Not Issued)"],
    "stall_tex_ni":                 ["stall_tex (Not Issued)"],
    "stall_wait_ni":                ["stall_wait (Not Issued)"],
}

# ── READ FILE ─────────────────────────────────────────────────────────────────
print(f"[*] Reading {INPUT_FILE} ...")
raw = None
for enc in ("utf-8-sig", "utf-16", "utf-8"):
    try:
        with open(INPUT_FILE, encoding=enc) as f:
            raw = f.read()
        print(f"[+] Encoding: {enc}")
        break
    except Exception:
        continue

if raw is None:
    print("[ERROR] Could not read file")
    sys.exit(1)

lines = [l for l in raw.splitlines()
         if l.strip()
         and not l.startswith("==")
         and not l.startswith("C[")]

# ── DETECT FORMAT ─────────────────────────────────────────────────────────────
header_idx  = None
format_type = None

for i, line in enumerate(lines):
    if line.startswith('"Line No"'):
        header_idx, format_type = i, "B"
        break
    if line.startswith('"Address"') and '"Source"' in line:
        header_idx, format_type = i, "A"
        break

if header_idx is None:
    print("[ERROR] Could not detect format / find header")
    for l in lines[:6]:
        print(f"  {repr(l[:120])}")
    sys.exit(1)

print(f"[+] Format: {'cuda,sass (B)' if format_type == 'B' else 'sass-only (A)'}")

csv_content = "\n".join(lines[header_idx:])
reader      = csv.reader(io.StringIO(csv_content))
headers     = [h.strip() for h in next(reader)]
all_rows    = list(reader)

print(f"[+] Columns: {len(headers)}  |  Data rows: {len(all_rows)}")

# ── EXTRACT SASS ROWS WITH SOURCE CONTEXT ─────────────────────────────────────
output_rows = []

if format_type == "A":
    addr_idx = headers.index("Address")
    src_idx  = headers.index("Source")
    for row in all_rows:
        if len(row) <= addr_idx:
            continue
        addr = row[addr_idx].strip()
        if not addr.startswith("0x"):
            continue
        out = {
            "cuda_line":   "",
            "cuda_source": "",
            "sass_addr":   addr,
            "sass_text":   row[src_idx].strip() if src_idx < len(row) else "",
        }
        for i, h in enumerate(headers):
            if h not in ("Address", "Source") and i < len(row):
                out[h] = row[i].strip()
        output_rows.append(out)

elif format_type == "B":
    # cols: Line No(0), Source/cuda(1), Address(2), Source/sass(3), metrics(4+)
    metric_headers      = headers[4:]
    current_cuda_line   = ""
    current_cuda_source = ""

    for row in all_rows:
        if len(row) < 4:
            continue
        line_no  = row[0].strip()
        cuda_src = row[1].strip()
        addr     = row[2].strip()
        sass_src = row[3].strip()

        if line_no and addr == "-":
            current_cuda_line   = line_no
            current_cuda_source = cuda_src
            continue

        if addr.startswith("0x"):
            out = {
                "cuda_line":   current_cuda_line,
                "cuda_source": current_cuda_source,
                "sass_addr":   addr,
                "sass_text":   sass_src,
            }
            for i, h in enumerate(metric_headers):
                out[h] = row[4 + i].strip() if (4 + i) < len(row) else ""
            output_rows.append(out)

print(f"[+] SASS instruction rows: {len(output_rows)}")

if not output_rows:
    print("[ERROR] No rows extracted")
    sys.exit(1)

# ── RESOLVE ALIASES ───────────────────────────────────────────────────────────
all_keys = list(output_rows[0].keys())

def find_col(candidates, keys):
    for c in candidates:
        if c in keys:
            return c
    return None

found, missing = {}, []
for alias, candidates in ALIAS_MAP.items():
    real = find_col(candidates, all_keys)
    if real:
        found[alias] = real
    else:
        missing.append(alias)

print(f"[+] Aliases resolved: {len(found)}/{len(ALIAS_MAP)}")
if missing:
    print(f"[!] Not found ({len(missing)}): {missing}")

# ── SAFE INT CONVERSION ───────────────────────────────────────────────────────
def safe_int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except Exception:
        return 0

# Add alias columns to every row
for row in output_rows:
    for alias, real in found.items():
        row[alias] = safe_int(row.get(real, 0))

# ── SORT BY WORST STALL ───────────────────────────────────────────────────────
sort_alias = None
for candidate in ("stall_long_sb", "warp_stall_all", "sample_count"):
    if candidate in found:
        sort_alias = candidate
        sort_col   = found[candidate]
        break

if sort_alias:
    output_rows.sort(key=lambda r: r.get(sort_alias, 0), reverse=True)
    print(f"[+] Sorted by: '{sort_alias}'")

# ── BUILD FINAL COLUMN ORDER ──────────────────────────────────────────────────
base_cols  = ["cuda_line", "cuda_source", "sass_addr", "sass_text"]
alias_cols = list(found.keys())
covered    = set(found.values())
extra_cols = [k for k in all_keys
              if k not in base_cols and k not in covered and k not in alias_cols]
final_cols = base_cols + alias_cols + extra_cols

# ── WRITE OUTPUT ──────────────────────────────────────────────────────────────
with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=final_cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(output_rows)

print(f"\n[✔] {OUTPUT_FILE}  —  {len(output_rows)} rows × {len(final_cols)} columns")

# ── TOP 10 HOTSPOTS ───────────────────────────────────────────────────────────
if sort_alias:
    print(f"\n── Top 10  (by {sort_alias}) {'─'*45}")
    print(f"  {'cuda_line':>9}  {'sass_addr':<14}  {sort_alias:>12}  sass_text")
    print("  " + "─" * 72)
    for row in output_rows[:10]:
        print(f"  {str(row.get('cuda_line',''))[:9]:>9}  "
              f"{row['sass_addr']:<14}  "
              f"{row.get(sort_alias, 0):>12}  "
              f"{row['sass_text'][:45]}")
