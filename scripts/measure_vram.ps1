param(
  [int]$IntervalSec = 1,
  [int]$Count = 60
)

for ($i = 0; $i -lt $Count; $i++) {
  nvidia-smi --query-gpu=timestamp,name,memory.used,memory.total --format=csv,noheader
  Start-Sleep -Seconds $IntervalSec
}
