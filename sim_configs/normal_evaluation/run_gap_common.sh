#!/bin/bash
# GAP benchmark trace overrides for normal_evaluation runs.
# Source this AFTER run_common.sh to replace SPEC_TRACES with the GAP traces
# located under ${TRACE_DIR}/gap.

GAP_TRACES=(
  "${TRACE_DIR}/gap/bc-3.trace.gz"
  "${TRACE_DIR}/gap/bc-5.trace.gz"
  "${TRACE_DIR}/gap/bc-12.trace.gz"
  "${TRACE_DIR}/gap/bfs-3.trace.gz"
  # "${TRACE_DIR}/gap/bfs-8.trace.gz"
  # "${TRACE_DIR}/gap/bfs-10.trace.gz"
  # "${TRACE_DIR}/gap/bfs-14.trace.gz"
  # "${TRACE_DIR}/gap/cc-5.trace.gz"
  # "${TRACE_DIR}/gap/cc-6.trace.gz"
  # "${TRACE_DIR}/gap/cc-13.trace.gz"
  # "${TRACE_DIR}/gap/cc-14.trace.gz"
  "${TRACE_DIR}/gap/pr-3.trace.gz"
  "${TRACE_DIR}/gap/pr-5.trace.gz"
  "${TRACE_DIR}/gap/pr-10.trace.gz"
  "${TRACE_DIR}/gap/pr-14.trace.gz"
  # "${TRACE_DIR}/gap/sssp-3.trace.gz"
  # "${TRACE_DIR}/gap/sssp-5.trace.gz"
  # "${TRACE_DIR}/gap/sssp-10.trace.gz"
  # "${TRACE_DIR}/gap/sssp-14.trace.gz"
)

SPEC_TRACES=("${GAP_TRACES[@]}")
