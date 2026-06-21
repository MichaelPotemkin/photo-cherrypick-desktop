// Centralized UI tuning constants — previously bare magic numbers scattered across components (#89).
// Polling cadence and the lightbox magnification live here so they're discoverable and tunable in one
// place instead of hidden inline.

/** How often (ms) to re-poll a still-processing session's detail while analysis runs (SessionView). */
export const PROGRESS_POLL_MS = 1500;

/** How often (ms) to refetch the home-screen recent-sessions list so in-progress statuses stay fresh. */
export const SESSION_LIST_POLL_MS = 4000;

/** Lightbox hover-magnifier zoom factor — moderate, so detail stays readable. */
export const LIGHTBOX_ZOOM = 2.6;
