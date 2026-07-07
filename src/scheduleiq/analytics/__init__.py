"""Path analytics: milestone-targeted driving-path extraction, top-N float
paths, proximity profiling, merge-point ranking, and cross-update path
stability.

These are the v0.2 "no CPM engine" analytics of ANALYTICS_PROPOSAL.md §§1.1
and 2.1-2.4 (backlog A1, P1-P4): they read the dates and floats the source
tool already computed and reason about *which relationships drive the
completion date*, never recomputing CPM (ADR-0004).  Everything is computed
to a selectable target (default: the project-completion milestone), producing
report-ready fingerprints of what is doing what to the date.
"""
from .paths import (DrivingPath, FloatPath, MergePoint, PathStep,
                    PathStabilityPair, driving_path, float_paths,
                    merge_ranking, path_stability, proximity_profile,
                    run_path_analytics)
from .statistical import (BenfordResult, DriftResult, PhysicsFinding,
                          ProgressPhysicsResult, RatePoint, benford_screen,
                          distribution_drift, ks_distance, progress_physics,
                          run_stats)
from .earned_schedule import (EarnedSchedulePoint, EarnedScheduleResult,
                              earned_schedule)

__all__ = [
    "PathStep", "DrivingPath", "FloatPath", "MergePoint", "PathStabilityPair",
    "driving_path", "float_paths", "proximity_profile", "merge_ranking",
    "path_stability", "run_path_analytics",
    "BenfordResult", "DriftResult", "RatePoint", "PhysicsFinding",
    "ProgressPhysicsResult", "benford_screen", "distribution_drift",
    "ks_distance", "progress_physics", "run_stats",
    "EarnedSchedulePoint", "EarnedScheduleResult", "earned_schedule",
]
