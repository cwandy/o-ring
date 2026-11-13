# Data files

Material, fluid, rule and standard-size data (YAML / CSV). Filled in phase 1 (materials, rules)
and phase 5 (standards). Every numeric value carries `source` (a `ref_id` in `references.yaml`)
and `data_quality` (`measured_reference` | `literature` | `vendor` | `user_measured` |
`extrapolated` | `placeholder`). See SPEC.md §5 and §13.

The loader reads this directory by default; override with the `ORING_DESIGNER_DATA` env variable.
