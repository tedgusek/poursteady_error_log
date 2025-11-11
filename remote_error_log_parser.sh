{ zcat /data/poursteady/log/*-console.txt-*.gz 2>/dev/null ; cat /data/poursteady/log/*-console.txt ; } | awk 'BEGIN{IGNORECASE=1} 
{
  split($1, dt, /[T:-]/)
  datenum = dt[1] dt[2] dt[3]
  timenum = dt[4] * 100 + dt[5]
  datetime = datenum * 10000 + timenum
  
  if (datetime >= 202511052000) {
    line = $0
    
    # Process EMCY lines
    if (/EMCY/) {
      match(line, /(0000|1000|2310|2340|3210|3220|4280|4310|5441|5442|5443|6100|7500|8110|8130|8331|8580|8611|9000|FF01|FF02|FF03|FF04|FF05)/)
      if (RSTART > 0) {
        code = substr(line, RSTART, RLENGTH)
        timestamp = $1
        emcy_count[code]++
        emcy_last_time[code] = timestamp
      }
    }
    
    # Process failure lines
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