# Cross-arm drift comparison

Arms compared: opus-4-7, sonnet-4-6

## Tier 1/2 accuracy (correct / total) by fill level

| fill | opus-4-7 | sonnet-4-6 |
|------|------|------|
| 0.00 | 35/35 (100.0%) | 35/35 (100.0%) |
| 0.25 | 105/105 (100.0%) | 105/105 (100.0%) |
| 0.50 | 100/105 (95.2%) | 105/105 (100.0%) |
| 0.75 | 105/105 (100.0%) | 105/105 (100.0%) |
| 0.95 | 105/105 (100.0%) | 100/105 (95.2%) |

## Tier 3 reasoning_quality (mean) by fill level

| fill | opus-4-7 | sonnet-4-6 |
|------|------|------|
| 0.00 | 8.05 | 7.43 |
| 0.25 | 7.33 | 8.00 |
| 0.50 | 6.89 | 7.94 |
| 0.75 | 7.17 | 7.19 |
| 0.95 | 7.02 | 7.60 |

## Tier 3 unsupported_claims (mean) by fill level

| fill | opus-4-7 | sonnet-4-6 |
|------|------|------|
| 0.00 | 0.24 | 0.10 |
| 0.25 | 0.76 | 0.46 |
| 0.50 | 0.62 | 0.46 |
| 0.75 | 1.02 | 0.95 |
| 0.95 | 1.68 | 1.06 |

## Cost per arm

| arm | analyst | cost (USD) | n graded records |
|-----|---------|------------|------------------|
| opus-4-7 | claude-opus-4-7 | $582.33 | 728 |
| sonnet-4-6 | claude-sonnet-4-6 | $522.96 | 728 |

