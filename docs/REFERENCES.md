# References

Full citations for the reference keys used in the Metric & Heuristic Matrix
(`docs/METRIC_MATRIX.md`) and in report footnotes.

| Key | Citation |
|---|---|
| DCMA14 | Defense Contract Management Agency, *Earned Value Management System Program Analysis Pamphlet (PAP)*, DCMA-EA PAM 200.1, October 2012, §4 "14-Point Schedule Metrics."  The 14-Point Assessment was first issued as a DCMA EVM Center check sheet (~2005) and remains the de-facto industry standard; DCMA's current compliance surveillance uses the DECM metric set, which covers the same ground.  Thresholds: Logic ≤ 5%; Leads 0; Lags ≤ 5%; FS ≥ 90% (SF ≈ 0); Hard constraints ≤ 5%; High float (> 44 wd) ≤ 5%; Negative float 0; High duration (> 44 wd baseline) ≤ 5%; Invalid dates 0; Resources loaded; Missed tasks ≤ 5%; Critical path test pass; CPLI ≥ 0.95; BEI ≥ 0.95. |
| GAO | U.S. Government Accountability Office, *Schedule Assessment Guide: Best Practices for Project Schedules*, GAO-16-89G, December 2015.  Ten best practices under four characteristics of a reliable schedule (comprehensive, well-constructed, credible, controlled); five-point Met/Not-Met assessment scale. |
| NASA | NASA, *Schedule Management Handbook*, NASA/SP-2010-3403, January 2010 — "Schedule Assessment and Analysis" process group; automated in the NASA Schedule Test and Assessment Tool (STAT).  Health-check thresholds mirror the DCMA values (44-working-day screens, 5% populations, zero leads/negative float/invalid dates). |
| PASEG | National Defense Industrial Association, Integrated Program Management Division, *Planning & Scheduling Excellence Guide (PASEG)*, v6.0, 30 September 2025 (v5.0 September 2022).  Section 2: Generally Accepted Scheduling Principles (GASP, 8 tenets); Section 9: Schedule Maintenance (statusing to timenow); Section 10: Schedule Analysis (10.2 Schedule Health Assessment; 10.4 Schedule Execution Metrics — CPLI, SPI, BEI, CEI, TFCI, schedule rate charts, earned-schedule indices).  PASEG anchors indices on 1.00 and treats numeric tripwires as program-negotiable; the fixed tripwires cited in this tool are DCMA's. |
| AACE29R | AACE International, Recommended Practice No. 29R-03, *Forensic Schedule Analysis*, 25 April 2011, §2 "Source Validation" (baseline, update, and as-built validation protocols) and method implementation protocols (MIPs). |
| AACE78R | AACE International, Recommended Practice No. 78R-13, *Original Baseline Schedule Review — As Applied in Engineering, Procurement, and Construction*, 2014. |
| SCL | Society of Construction Law, *Delay and Disruption Protocol*, 2nd edition, February 2017 — Core Principles on programme and records; guidance on programme preparation, acceptance, and updating. |
| FUSE | Deltek Acumen Fuse metric library, per Deltek documentation (help.deltek.com, Acumen 8.x: "Metric Formulas and Thresholds," "Tripwire Thresholds," "DCMA 14 Point Assessment Metric Descriptions," "Industry Standards Metrics," "Fuse Schedule Index") and the "Acumen Fuse Metrics & Descriptions" guide.  Used as the market-capability parity reference (metric names, default tripwires, S1–S5 workflow, Forensics comparison, scoring modes) — see `docs/FUSE_PARITY.md`. |
| RPW | Ron Winter Consulting LLC — *Schedule Analyzer* software checks and the papers "The Inner Workings of Oracle Primavera P6" and AACE conference papers on XER analysis; the classic P6 forensic data-integrity practice (retained logic vs progress override, Expected Finish behavior, multi-calendar float distortion, actual-date changes). |
| CIOB | Chartered Institute of Building, *Guide to Good Practice in the Management of Time in Complex Projects*, Wiley-Blackwell, 2011. |

## Verification status

Threshold values and section attributions above were compiled from the primary
documents where accessible and corroborated across multiple independent
secondary sources where the primary PDF could not be fetched from the build
environment (GAO, NASA, DCMA, and NDIA host PDFs behind an egress policy).
Before quoting a section or page number in an expert report, verify it against
the primary PDF; `docs/METRIC_MATRIX.md` deliberately cites at the
document-plus-section level only where confirmed.
