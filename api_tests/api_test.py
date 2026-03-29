import sys, os, re, csv
NCU_API_PATH = "/opt/nvidia/nsight-compute/2024.3.1/extras/python"
sys.path.insert(0, NCU_API_PATH)
import ncu_report


def print_rules(action):
    rules = action.rule_results_as_dicts()

    if not rules:
        print("No rule results.")
        return

    for i, rule in enumerate(rules, 1):
        print(f"\n{'='*60}")
        print(f"[{i}] RULE: {rule.get('name', 'N/A')}")
        print(f"{'='*60}")
        print(f"Section       : {rule.get('section_identifier')}")
        print(f"Identifier    : {rule.get('rule_identifier')}")
        msg = rule.get("rule_message", {})
        print(f"\nTitle      : {msg.get('title', '')}")
        print(f"Message    : {msg.get('message', '')}")
        focus = rule.get("focus_metrics", [])
        if focus:
            print("\nFocus Metrics:")
            for m in focus:
                print(f"  - {m['name']}")
                print(f"      value   : {m['value']:.4f}")
                print(f"      severity: {m['severity']}")
                print(f"      info    : {m['info']}")
        speedup = rule.get("speedup_estimation")
        if speedup:
            print("\nSpeedup Estimate:")
            print(f"  type   : {speedup['type']}")
            print(f"  value  : {speedup['speedup']:.2f}%")


def print_source_markers(action):
    markers = action.source_markers()
    if not markers:
        print("No source markers.")
        return
    print("\n" + "="*60)
    print("SOURCE MARKERS")
    print("="*60)
    for m in markers:
        print("\n---")
        print(f"Rule        : {m.get('rule_identifier')}")
        print(f"Section     : {m.get('section_identifier')}")
        print(f"Message     : {m.get('message')}")
        if "source_location" in m:
            loc = m["source_location"]
            print(f"File        : {loc.get('file_name')}")
            print(f"Line        : {loc.get('line')}")
        if "source_address" in m:
            print(f"Address     : {m.get('source_address')}")


my_context = ncu_report.load_report("my_report.ncu-rep")
print("Number of ranges:", my_context.num_ranges())
my_range = my_context.range_by_idx(0)
print("Number of actions of the first range:", my_range.num_actions())
my_action = my_range.action_by_idx(0)
print("Action name:", my_action.name())
print("Workload type:", my_action.workload_type())
workload types are CMDLIST, GRAPH, KERNEL, RANGE
print(my_action.metric_names())
print("LTS__T_SECTOR_OP_READ_HIT_RATE.PCT:", my_action.metric_by_name('lts__t_sector_op_read_hit_rate.pct').value())
display_name_metric = my_action.metric_by_name('device__attribute_display_name')
print("device: ", display_name_metric.as_string())
print("IAction methods:", dir(ncu_report.IAction))



info = my_action.source_info(30086052672)
if info:
    print("File:", info.file_name())
    print("Line:", info.line())
else:
    print("No source info available")

#metric =  my_action.metric_by_name('smsp__sass_average_data_bytes_per_sector_mem_global_op_ld.ratio')
metric = my_action["smsp__pcsamp_warps_issue_stalled_long_scoreboard"]
if metric.has_correlation_ids():
    print("Has correlation!")
else:
    print("No correlation available.")

corr = metric.correlation_ids()
for i in range(metric.num_instances()):
    value = metric.value(i)
    pc = corr.value(i)

    print(f"\nInstance {i}")
    print(f"Value: {value}")
    print(f"PC: {pc}")
