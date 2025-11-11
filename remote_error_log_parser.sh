#!/usr/bin/env bash
# remote_error_log_parser.sh
# Usage: bash -s -- <SINCE_YYYYMMDDHHMM>  (e.g., 202511052000)

SINCE="$1"
if [[ -z "$SINCE" ]]; then
  echo "Missing SINCE argument (YYYYMMDDHHMM)" >&2
  exit 2
fi

{ zcat /data/poursteady/log/*-console.txt-*.gz 2>/dev/null ; cat /data/poursteady/log/*-console.txt 2>/dev/null; } \
| awk -v since="$SINCE" 'BEGIN{IGNORECASE=1}
{
  # Expect first token like 2025-11-05T20:13:00-05:00
  split($1, dt, /[T:-]/)
  if (length(dt[1])==0 || length(dt[2])==0 || length(dt[3])==0) next
  datenum = dt[1] dt[2] dt[3]
  timenum = dt[4] * 100 + dt[5]
  datetime = datenum * 10000 + timenum

  if (datetime >= since) {
    line = $0
    if (/EMCY/) {
      match(line, /(0000|1000|2310|2340|3210|3220|4280|4310|5441|5442|5443|6100|7500|8110|8130|8331|8580|8611|9000|FF01|FF02|FF03|FF04|FF05)/)
      if (RSTART > 0) {
        code = substr(line, RSTART, RLENGTH)
        timestamp = $1
        emcy_count[code]++
        emcy_last_time[code] = timestamp
      }
    }
    if (/failure/) {
      failure_count++
      failure_last_timestamp = $1
    }
  }
}
END {
  for (code in emcy_count) {
    print emcy_count[code], code, emcy_last_time[code]
  }
  print (failure_count ? failure_count : 0) " SAOBO Errors " failure_last_timestamp
}' | sort -rn
