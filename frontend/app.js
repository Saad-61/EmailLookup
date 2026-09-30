/* ──────────────────────────────────────────────────────────────────────────
   app.js — Modern SaaS OSINT & Email Verification Frontend
   ────────────────────────────────────────────────────────────────────────── */

const API_BASE = window.location.origin;

// ── High-Fidelity SVG Platform Icons ───────────────────────────────────────────
const SVG_ICONS = {
  linkedin: `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/>
    </svg>`,
  instagram: `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
    </svg>`,
  twitter: `
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
    </svg>`,
  facebook: `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
    </svg>`,
  tiktok: `
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.24 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/>
    </svg>`,
  pinterest: `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="12" fill="#E60023"/>
      <path d="M12.18 4.5C8.04 4.5 5.25 7.42 5.25 10.95c0 2.37 1.28 4.04 2.15 4.04.3 0 .49-.5.59-.88.08-.2.08-.29 0-.49-.4-.49-.59-1.28-.59-2.27 0-2.76 2.07-5.33 5.42-5.33 2.76 0 4.73 1.67 4.73 4.44 0 2.66-1.28 4.93-3.25 4.93-1.08 0-1.77-.79-1.48-1.77.29-1.18.89-2.46.89-3.35 0-.79-.39-1.38-1.28-1.38-.98 0-1.87.98-1.87 2.36 0 .89.3 1.48.3 1.48l-1.28 5.32c-.39 1.58-.1 3.84 0 4.14.1.1.2.1.3.1.1-.1 1.48-1.97 1.87-3.45l.69-2.66c.39.69 1.38 1.28 2.36 1.28 3.35 0 5.62-3.05 5.62-6.99C21.65 7.52 17.41 4.5 12.18 4.5z" fill="#FFFFFF"/>
    </svg>`,
  spotify: `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>
    </svg>`,
  github: `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0 0 22 12.017C22 6.484 17.522 2 12 2z"/>
    </svg>`,
  youtube: `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
    </svg>`,
};

// ── Tab Switching (Zero-Glitch) ───────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    });
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");
    const targetPanel = document.getElementById("panel-" + btn.dataset.tab);
    if (targetPanel) targetPanel.classList.add("active");
  });
});

// ── Skeleton Loader Helpers ───────────────────────────────────────────────────
function showLookupSkeleton() {
  document.getElementById("lookup-results").classList.add("hidden");
  document.getElementById("lookup-skeleton").classList.remove("hidden");
}

function hideLookupSkeleton() {
  document.getElementById("lookup-skeleton").classList.add("hidden");
}

function showVerifySkeleton() {
  document.getElementById("verify-results").classList.add("hidden");
  document.getElementById("verify-skeleton").classList.remove("hidden");
}

function hideVerifySkeleton() {
  document.getElementById("verify-skeleton").classList.add("hidden");
}

// ── Utility ───────────────────────────────────────────────────────────────────
function setLoading(btnEl, isLoading) {
  const textEl = btnEl.querySelector(".btn-text");
  const spinnerEl = btnEl.querySelector(".btn-spinner");
  btnEl.disabled = isLoading;
  textEl.textContent = isLoading ? "Searching..." : (btnEl.dataset.originalText || "Search");
  spinnerEl.classList.toggle("hidden", !isLoading);
}

function showError(containerId, msg) {
  const el = document.getElementById(containerId);
  el.textContent = msg;
  el.classList.remove("hidden");
}

function hideError(containerId) {
  document.getElementById(containerId).classList.add("hidden");
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ── Email Validation & Typo Checking ─────────────────────────────────────────
const INVALID_TYPO_DOMAINS = new Set([
  "gmil.com", "gmai.com", "gamil.com", "gmial.com", "gmaill.com", "gmal.com",
  "gmaik.com", "gmaul.com", "gmajl.com", "gnail.com", "gmaili.com",
  "yaho.com", "yahooo.com", "yaho.co", "yhaoo.com",
  "hotmial.com", "hotmaill.com", "hotmai.com", "hotmil.com",
  "outlok.com", "outloo.com", "outllok.com",
  "iclod.com", "protonmal.com",
]);

const INVALID_TLD_TYPOS = ["cor", "cpm", "ocm", "comm", "coom", "con", "cm", "xom", "vom"];

function isValidEmailAddress(email) {
  if (!email || typeof email !== "string") return false;
  const trimmed = email.trim();
  const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  if (!EMAIL_REGEX.test(trimmed)) return false;

  const parts = trimmed.split("@");
  if (parts.length !== 2) return false;
  const domain = parts[1].toLowerCase().trim();

  if (INVALID_TYPO_DOMAINS.has(domain)) {
    return false;
  }
  for (const typo of INVALID_TLD_TYPOS) {
    if (domain.endsWith(`.${typo}`)) {
      return false;
    }
  }
  return true;
}

// ── ─────────────────────────────────────────────────────────────────────────
//    REVERSE LOOKUP
// ── ─────────────────────────────────────────────────────────────────────────
const lookupBtn = document.getElementById("lookup-btn");
lookupBtn.dataset.originalText = "Search";

document.getElementById("lookup-input").addEventListener("keydown", e => {
  if (e.key === "Enter") lookupBtn.click();
});

async function doLookup(forceRefresh = false) {
  const inputEl = document.getElementById("lookup-input");
  const email = inputEl.value.trim();

  if (!isValidEmailAddress(email)) {
    showError("lookup-error", "Please enter a valid email address.");
    return;
  }

  hideError("lookup-error");

  // Show shimmer skeleton state
  showLookupSkeleton();
  setLoading(lookupBtn, true);
  lookupBtn.querySelector(".btn-text").textContent = forceRefresh ? "Refreshing..." : "Searching...";

  try {
    const res = await fetch(`${API_BASE}/api/lookup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, force_refresh: forceRefresh }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Lookup failed");
    }

    const data = await res.json();
    hideLookupSkeleton();
    renderLookupResults(data);
    document.getElementById("lookup-results").classList.remove("hidden");
  } catch (err) {
    hideLookupSkeleton();
    showError("lookup-error", err.message || "Lookup failed");
  } finally {
    setLoading(lookupBtn, false);
    lookupBtn.querySelector(".btn-text").textContent = "Search";
  }
}

lookupBtn.addEventListener("click", () => doLookup(false));

// ── Cache Invalidation / Force Refresh ──
const forceRefreshBtn = document.getElementById("force-refresh-btn");
if (forceRefreshBtn) {
  forceRefreshBtn.addEventListener("click", async () => {
    const email = document.getElementById("lookup-input").value.trim();
    if (!email) return;
    try {
      forceRefreshBtn.disabled = true;
      forceRefreshBtn.classList.add("loading");
      await fetch(`${API_BASE}/api/cache/invalidate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
    } catch (e) {
      console.warn("Cache invalidate error:", e);
    } finally {
      forceRefreshBtn.disabled = false;
      forceRefreshBtn.classList.remove("loading");
    }
    doLookup(true);
  });
}

// ── Copy Name to Clipboard ──
const copyNameBtn = document.getElementById("copy-name-btn");
if (copyNameBtn) {
  copyNameBtn.addEventListener("click", () => {
    const name = document.getElementById("person-name").textContent;
    if (name && name !== "Unknown Person") {
      navigator.clipboard.writeText(name);
      copyNameBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      `;
      setTimeout(() => {
        copyNameBtn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
        `;
      }, 1500);
    }
  });
}

// ── Candidate Profiles State & Tab Switching ──
let currentLookupCandidates = {};
let currentCandidatePlatform = "linkedin";

const CANDIDATE_PLATFORMS = [
  { id: "linkedin", label: "LinkedIn", icon: SVG_ICONS.linkedin },
  { id: "github", label: "GitHub", icon: SVG_ICONS.github },
  { id: "instagram", label: "Instagram", icon: SVG_ICONS.instagram },
  { id: "facebook", label: "Facebook", icon: SVG_ICONS.facebook },
  { id: "twitter", label: "X", icon: SVG_ICONS.twitter },
  { id: "pinterest", label: "Pinterest", icon: SVG_ICONS.pinterest },
  { id: "tiktok", label: "TikTok", icon: SVG_ICONS.tiktok },
  { id: "spotify", label: "Spotify", icon: SVG_ICONS.spotify },
];

function switchCandidateTab(platId) {
  currentCandidatePlatform = platId;

  // Update active class on tab buttons
  document.querySelectorAll(".cand-tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.plat === platId);
  });

  const listEl = document.getElementById("cand-items-list");
  const scrollContainer = document.getElementById("cand-scroll-container");
  if (!listEl) return;

  const candidatesToRender = currentLookupCandidates[platId] || [];

  if (candidatesToRender.length > 0) {
    listEl.innerHTML = candidatesToRender.map(renderCandidateCard).join("");
  } else {
    const platObj = CANDIDATE_PLATFORMS.find(p => p.id === platId);
    const platName = platObj ? platObj.label : platId;
    listEl.innerHTML = `<p class="no-data">No candidate accounts found on ${escapeHtml(platName)}.</p>`;
  }

  if (scrollContainer) {
    scrollContainer.scrollTop = 0;
  }
}

document.addEventListener("click", e => {
  const btn = e.target.closest(".cand-tab-btn");
  if (!btn) return;
  const plat = btn.dataset.plat;
  if (plat) switchCandidateTab(plat);
});

function renderLookupResults(data) {
  // ── Person Card ──
  const person = data.person || {};
  const nameEl = document.getElementById("person-name");
  const bioEl = document.getElementById("person-bio");
  const personLocEl = document.getElementById("person-location");
  const avatarEl = document.getElementById("person-avatar");
  const avatarPlaceholder = document.getElementById("avatar-placeholder");
  const typeBadge = document.getElementById("email-type-badge");
  const delivBadge = document.getElementById("deliverability-badge");
  const personExtra = document.getElementById("person-extra");

  nameEl.textContent = person.name || "Unknown Person";
  bioEl.textContent = person.bio || "";
  
  const locWrap = document.getElementById("person-location-wrap");
  if (person.location) {
    personLocEl.textContent = person.location;
    if (locWrap) locWrap.classList.remove("hidden");
  } else if (locWrap) {
    locWrap.classList.add("hidden");
  }

  if (person.avatar) {
    avatarEl.referrerPolicy = "no-referrer";
    avatarEl.src = person.avatar;
    avatarEl.onload = () => {
      avatarEl.classList.remove("hidden");
      avatarPlaceholder.classList.add("hidden");
    };
    avatarEl.onerror = () => {
      avatarEl.classList.add("hidden");
      avatarPlaceholder.classList.remove("hidden");
    };
  } else {
    avatarEl.classList.add("hidden");
    avatarPlaceholder.classList.remove("hidden");
  }

  typeBadge.textContent = data.email_type === "corporate" ? "Corporate Account" : "Personal Account";
  typeBadge.className = "type-badge " + (data.email_type || "personal");

  const profiles = data.profiles || {};
  const identityBadge = document.getElementById("identity-badge");
  const hasVerifiedIdentity = Boolean(
    profiles.linkedin_verified ||
    (profiles.linkedin_confidence === 100 && ["wikidata", "github", "gravatar", "harvested"].includes(profiles.linkedin_source)) ||
    (profiles.github && typeof profiles.github === "object" && profiles.github.username) ||
    (profiles.gravatar && typeof profiles.gravatar === "object" && (profiles.gravatar.name || profiles.gravatar.avatar))
  );

  if (identityBadge) {
    if (hasVerifiedIdentity) {
      identityBadge.innerHTML = `✓ Corroborated Identity`;
      identityBadge.className = "type-badge badge-verified";
      identityBadge.title = "Identity verified through authoritative profile records";
      identityBadge.classList.remove("hidden");
    } else if (person.name) {
      identityBadge.textContent = "Inferred Name · Unconfirmed";
      identityBadge.className = "type-badge badge-inferred";
      identityBadge.title = "Name derived from email username; review matching candidate profiles below";
      identityBadge.classList.remove("hidden");
    } else {
      identityBadge.classList.add("hidden");
    }
  }

  if (delivBadge) {
    if (data.deliverability === "undeliverable") {
      delivBadge.textContent = "Inactive Mailbox";
      delivBadge.classList.remove("hidden");
    } else {
      delivBadge.classList.add("hidden");
    }
  }

  personExtra.classList.remove("hidden");

  // ── Workplace & Organization Panel (Bento Row 1 Right) ──
  const comp = data.company;
  const workplaceSideEl = document.getElementById("person-workplace-side");
  const compNameEl = document.getElementById("company-name");
  const compMetaEl = document.getElementById("company-meta");
  const compLogoEl = document.getElementById("company-logo");
  const compLogoFallback = document.getElementById("company-logo-fallback");

  const hasRealWorkplace = Boolean(
    comp && (comp.name || (comp.domain && data.email_type === "corporate"))
  );

  if (hasRealWorkplace && workplaceSideEl) {
    workplaceSideEl.classList.remove("hidden");
    compNameEl.textContent = comp.name || comp.domain;
    const metaParts = [];
    if (comp.role) metaParts.push(comp.role);
    if (comp.industry) metaParts.push(comp.industry);
    if (comp.country) metaParts.push(comp.country);
    if (comp.domain && comp.domain.toLowerCase() !== (comp.name || "").toLowerCase()) metaParts.push(comp.domain);
    compMetaEl.textContent = metaParts.join(" · ") || comp.domain || "Enterprise Workplace";

    if (comp.logo) {
      compLogoEl.src = comp.logo;
      compLogoEl.classList.remove("hidden");
      compLogoFallback.classList.add("hidden");
      compLogoEl.onerror = () => {
        if (comp.domain && !compLogoEl.src.includes("google.com/s2/favicons")) {
          compLogoEl.src = `https://www.google.com/s2/favicons?domain=${comp.domain}&sz=128`;
        } else {
          compLogoEl.classList.add("hidden");
          compLogoFallback.classList.remove("hidden");
        }
      };
    } else if (comp.domain) {
      compLogoEl.src = `https://www.google.com/s2/favicons?domain=${comp.domain}&sz=128`;
      compLogoEl.classList.remove("hidden");
      compLogoFallback.classList.add("hidden");
      compLogoEl.onerror = () => {
        compLogoEl.classList.add("hidden");
        compLogoFallback.classList.remove("hidden");
      };
    } else {
      compLogoEl.classList.add("hidden");
      compLogoFallback.classList.remove("hidden");
    }
  } else if (workplaceSideEl) {
    workplaceSideEl.classList.add("hidden");
  }

  // ── Social Profiles Chips (with Headshot Avatar Rendering) ──
  const profilesList = document.getElementById("profiles-list");
  const chips = [];

  const RESERVED_FRONTEND_HANDLES = new Set(["https", "http", "www", "null", "undefined", "in", "pub", "dir", "explore", "about"]);

  function parseProfileVal(val, defaultLabel) {
    if (!val) return null;
    if (typeof val === "string") {
      const cleanUrl = val.trim();
      const rawHandle = (cleanUrl.split("/").filter(Boolean).pop() || "").replace(/^@/, "");
      if (!rawHandle || RESERVED_FRONTEND_HANDLES.has(rawHandle.toLowerCase()) || rawHandle.length < 2) {
        return null;
      }
      return { url: cleanUrl, name: defaultLabel, handle: `@${rawHandle}`, snippet: "", avatar_url: null, isObject: false, verified: false, source: "" };
    }
    if (typeof val === "object") {
      const cleanUrl = (val.url || "").trim();
      const rawHandle = (val.handle || val.username || cleanUrl.split("/").filter(Boolean).pop() || "").replace(/^@/, "");
      if (!rawHandle || RESERVED_FRONTEND_HANDLES.has(rawHandle.toLowerCase()) || rawHandle.length < 2) {
        return null;
      }
      const isConfirmed = val.verified === true || ["github", "gravatar", "wikidata", "harvested"].includes(val.source);
      return {
        url: cleanUrl,
        name: val.name || defaultLabel,
        handle: `@${rawHandle}`,
        snippet: val.snippet || val.title || "",
        avatar_url: val.avatar_url || val.avatar || null,
        confidence: val.confidence || (isConfirmed ? 100 : 80),
        source: val.source || "",
        verified: isConfirmed,
        isObject: true,
      };
    }
    return null;
  }

  function resolveVerifiedAvatar(platform, p) {
    if (p && (p.avatar_url || p.avatar)) return p.avatar_url || p.avatar;
    return null;
  }

  if (profiles.linkedin) {
    const p = parseProfileVal(profiles.linkedin, "LinkedIn Profile");
    if (p && p.url) {
      const isDirect = p.verified || ["wikidata", "github", "gravatar", "harvested"].includes(p.source || profiles.linkedin_source);
      const rawSlug = p.url.split("/in/").pop().split("?")[0].replace(/\/$/, "");
      const displaySlug = rawSlug ? `in/${rawSlug}` : "Profile Link";
      if (isDirect) {
        chips.push(buildProfileChip({
          href: p.url,
          platform: "linkedin",
          name: `LinkedIn <span class="verified-pill">✓ Verified</span>`,
          sub: displaySlug,
          avatar_url: resolveVerifiedAvatar("linkedin", p),
        }));
      }
    }
  }

  if (profiles.github) {
    const gh = profiles.github;
    const ghUrl = typeof gh === "string" ? gh : (gh.url || "");
    const ghUser = typeof gh === "string" ? ghUrl.split("/").pop() : (gh.username || "");
    const ghAvatar = typeof gh === "object" ? (gh.avatar || gh.avatar_url) : null;
    // Subtext: handle · repos · followers
    const ghSub = typeof gh === "object"
      ? `@${ghUser} · ${gh.repos ?? "?"} repos · ${gh.followers ?? "?"} followers`
      : `@${ghUser}`;
    chips.push(buildProfileChip({
      href: ghUrl,
      platform: "github",
      name: `GitHub <span class="verified-pill">✓ Verified</span>`,
      sub: ghSub,
      avatar_url: ghAvatar || resolveVerifiedAvatar("github", { handle: ghUser, url: ghUrl }),
    }));
  }

  if (profiles.twitter) {
    const p = parseProfileVal(profiles.twitter, "X / Twitter");
    if (p && p.url) {
      const isDirect = p.verified || ["github", "gravatar"].includes(p.source);
      if (isDirect) {
        // Show name + handle, or just handle — no 'View Profile' trailing text
        let subText = p.handle || "";
        if (p.name && p.handle && p.name !== "X / Twitter") {
          subText = `${p.name} · ${p.handle}`;
        }
        chips.push(buildProfileChip({
          href: p.url,
          platform: "twitter",
          name: `X / Twitter <span class="verified-pill">✓ Verified</span>`,
          sub: subText,
          avatar_url: resolveVerifiedAvatar("twitter", p),
        }));
      }
    }
  }

  if (profiles.instagram) {
    const p = parseProfileVal(profiles.instagram, "Instagram");
    if (p && p.url) {
      const isDirect = p.verified || ["github", "gravatar"].includes(p.source);
      if (isDirect) {
        // Show display name + handle, or just handle — no trailing 'View Profile'
        let subText = p.handle || "";
        if (p.name && p.handle && p.name !== "Instagram") {
          subText = `${p.name} · ${p.handle}`;
        }
        chips.push(buildProfileChip({
          href: p.url,
          platform: "instagram",
          name: `Instagram <span class="verified-pill">✓ Verified</span>`,
          sub: subText,
          avatar_url: resolveVerifiedAvatar("instagram", p),
        }));
      }
    }
  }

  if (profiles.facebook) {
    const p = parseProfileVal(profiles.facebook, "Facebook");
    if (p && p.url) {
      const isDirect = p.verified || ["github", "gravatar"].includes(p.source);
      if (isDirect) {
        let subText = p.handle || "";
        if (p.name && p.handle && p.name !== "Facebook") {
          subText = `${p.name} · ${p.handle}`;
        }
        chips.push(buildProfileChip({
          href: p.url,
          platform: "facebook",
          name: `Facebook <span class="verified-pill">✓ Verified</span>`,
          sub: subText,
          avatar_url: resolveVerifiedAvatar("facebook", p),
        }));
      }
    }
  }

  if (profiles.youtube) {
    const p = parseProfileVal(profiles.youtube, "YouTube");
    if (p && p.url) {
      const isDirect = p.verified || ["gravatar"].includes(p.source);
      if (isDirect) {
        chips.push(buildProfileChip({
          href: p.url,
          platform: "youtube",
          name: `YouTube <span class="verified-pill">✓ Verified</span>`,
          sub: "Verified Channel",
          avatar_url: resolveVerifiedAvatar("youtube", p),
        }));
      }
    }
  }

  if (profiles.spotify) {
    const p = parseProfileVal(profiles.spotify, "Spotify");
    if (p && p.url) {
      // Show display name + handle, or just handle
      let subText = p.handle || "";
      if (p.name && p.name !== "Spotify") {
        subText = p.handle ? `${p.name} · ${p.handle}` : p.name;
      }
      chips.push(buildProfileChip({
        href: p.url,
        platform: "spotify",
        name: `Spotify <span class="verified-pill">✓ Verified</span>`,
        sub: subText,
        avatar_url: resolveVerifiedAvatar("spotify", p),
      }));
    }
  }

  // ── Render Verified Profiles Card ──
  const verifiedBadgeEl = document.getElementById("verified-count-badge");
  if (verifiedBadgeEl) verifiedBadgeEl.textContent = chips.length;

  if (chips.length > 0) {
    profilesList.innerHTML = chips.join("");
    profilesList.style.display = "flex";
  } else {
    profilesList.innerHTML = "<p class='no-data'>No direct verified profiles confirmed for this email.</p>";
    profilesList.style.display = "block";
  }

  // ── Render Discovered Candidate Profiles Card (Sticky Navbar + Scrollable List) ──
  const byPlat = Object.assign({}, data.social_candidates_by_platform || {});

  // When GitHub is directly verified in top profiles, suppress candidate GitHub
  if (profiles.github) {
    byPlat.github = [];
  }

  currentLookupCandidates = byPlat;

  const orderedPlats = ["linkedin", "github", "instagram", "facebook", "twitter", "pinterest", "tiktok", "spotify"];
  let totalCandidatesFound = 0;
  orderedPlats.forEach(p => {
    totalCandidatesFound += (byPlat[p] || []).length;
  });

  const candTotalBadge = document.getElementById("cand-total-badge");
  if (candTotalBadge) candTotalBadge.textContent = totalCandidatesFound;

  // Build the pinned Platform Symbols Navbar (Only show platforms with count > 0, show ONLY icons + count badges, no text names, no 'all')
  const navBarEl = document.getElementById("cand-nav-bar");
  const visiblePlats = CANDIDATE_PLATFORMS.filter(plat => (byPlat[plat.id] || []).length > 0);

  if (navBarEl) {
    if (visiblePlats.length > 0) {
      navBarEl.innerHTML = visiblePlats.map(plat => {
        const count = (byPlat[plat.id] || []).length;
        return `
          <button type="button" class="cand-tab-btn" data-plat="${plat.id}" title="${escapeHtml(plat.label)} (${count})">
            <span class="cand-tab-icon">${plat.icon}</span>
            <span class="cand-tab-badge">${count}</span>
          </button>
        `;
      }).join("");
      navBarEl.style.display = "flex";
    } else {
      navBarEl.innerHTML = "";
      navBarEl.style.display = "none";
    }
  }

  // Activate LinkedIn by default if it has candidates, then GitHub, then Instagram, otherwise the first available platform
  if ((byPlat.linkedin || []).length > 0) {
    switchCandidateTab("linkedin");
  } else if ((byPlat.github || []).length > 0) {
    switchCandidateTab("github");
  } else if ((byPlat.instagram || []).length > 0) {
    switchCandidateTab("instagram");
  } else if (visiblePlats.length > 0) {
    switchCandidateTab(visiblePlats[0].id);
  } else {
    switchCandidateTab("linkedin");
  }



  // ── Query Time ──
  document.getElementById("query-time").textContent = `Query completed in ${data.query_time_ms}ms`;
}

function buildProfileChip({ href, platform, name, sub, avatar_url }) {
  const glyphSvg = SVG_ICONS[platform] || SVG_ICONS.github;
  const glyphClass = `${platform}-glyph`;

  const iconHtml = avatar_url ? `
    <div class="profile-chip-avatar-wrap">
      <img src="${escapeHtml(avatar_url)}" class="profile-chip-avatar" referrerpolicy="no-referrer" alt="${escapeHtml(name)}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
      <div class="platform-glyph-badge ${glyphClass}" style="display: none;">${glyphSvg}</div>
    </div>
  ` : `
    <div class="platform-glyph-badge ${glyphClass}">${glyphSvg}</div>
  `;

  return `
    <a href="${href}" target="_blank" rel="noopener noreferrer" class="profile-chip">
      ${iconHtml}
      <div class="profile-chip-info">
        <div class="profile-chip-name">${name}</div>
        <div class="profile-chip-sub">${sub}</div>
      </div>
      <svg class="ext-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
        <polyline points="15 3 21 3 21 9"/>
        <line x1="10" y1="14" x2="21" y2="3"/>
      </svg>
    </a>
  `;
}

function renderCandidateCard(c) {
  const glyphSvg = SVG_ICONS[c.platform] || SVG_ICONS.github;
  const glyphClass = `${c.platform}-glyph`;

  // Note: percentage badges are omitted. Only 100% verified profiles receive a badge.
  const verifiedBadge = c.verified === true ? `<span class="verified-pill">✓ Verified</span>` : "";

  const snippetHtml = c.snippet ? `<div class="candidate-snippet">${escapeHtml(c.snippet)}</div>` : "";

  const avatarImgHtml = c.avatar_url ? `
    <div class="profile-chip-avatar-wrap" style="width: 44px; height: 44px;">
      <img src="${escapeHtml(c.avatar_url)}" class="candidate-avatar" referrerpolicy="no-referrer" alt="${escapeHtml(c.handle)}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
      <div class="platform-glyph-badge ${glyphClass}" style="display: none; width: 44px; height: 44px; border-radius: var(--radius-sm);">${glyphSvg}</div>
    </div>
  ` : `
    <div class="platform-glyph-badge ${glyphClass}" style="width: 44px; height: 44px; border-radius: var(--radius-sm);">${glyphSvg}</div>
  `;

  return `
    <div class="candidate-card">
      <div class="candidate-main">
        <div class="candidate-header">
          <div class="candidate-avatar-wrapper">
            ${avatarImgHtml}
          </div>
          <div class="candidate-info">
            <div class="candidate-name-row">
              <span class="candidate-name">${escapeHtml(c.name || c.handle)}</span>
              <span class="candidate-handle">${escapeHtml(c.handle)}</span>
              ${verifiedBadge}
            </div>
            <div class="candidate-platform-sub">${escapeHtml(c.platform_label || c.platform)}</div>
          </div>
        </div>
        ${snippetHtml}
      </div>
      <a href="${c.url}" target="_blank" rel="noopener noreferrer" class="candidate-action-btn">
        <span>View Profile</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
      </a>
    </div>
  `;
}

// ── ─────────────────────────────────────────────────────────────────────────
//    EMAIL VERIFIER
// ── ─────────────────────────────────────────────────────────────────────────
const verifyBtn = document.getElementById("verify-btn");
verifyBtn.dataset.originalText = "Verify";

document.getElementById("verify-input").addEventListener("keydown", e => {
  if (e.key === "Enter") verifyBtn.click();
});

verifyBtn.addEventListener("click", async () => {
  const email = document.getElementById("verify-input").value.trim();
  if (!isValidEmailAddress(email)) {
    showError("verify-error", "Please enter a valid email address.");
    return;
  }

  hideError("verify-error");
  showVerifySkeleton();
  setLoading(verifyBtn, true);
  verifyBtn.querySelector(".btn-text").textContent = "Verifying...";

  try {
    const res = await fetch(`${API_BASE}/api/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Verification failed");
    }

    const data = await res.json();
    hideVerifySkeleton();
    renderVerifyResults(data);
    document.getElementById("verify-results").classList.remove("hidden");
  } catch (err) {
    hideVerifySkeleton();
    showError("verify-error", `❌ ${err.message}`);
  } finally {
    setLoading(verifyBtn, false);
    verifyBtn.querySelector(".btn-text").textContent = "Verify";
  }
});

function renderVerifyResults(data) {
  const verdict = document.getElementById("verify-verdict");
  const verdictIcon = document.getElementById("verdict-icon");
  const verdictTitle = document.getElementById("verdict-title");
  const verdictSub = document.getElementById("verdict-sub");
  const verdictBadge = document.getElementById("verdict-badge");

  const vContactable = document.getElementById("v-contactable");
  const vContactableSub = document.getElementById("v-contactable-sub");
  const vInboxStatus = document.getElementById("v-inbox-status");
  const vInboxSub = document.getElementById("v-inbox-sub");
  const vProvider = document.getElementById("v-provider");
  const vProviderSub = document.getElementById("v-provider-sub");
  const noteEl = document.getElementById("verify-note");

  const provider = data.mx_provider || "Standard Provider";
  vProvider.textContent = provider;

  const isProtectedHost = (
    data.valid === null &&
    (
      ["Microsoft 365", "Google Workspace", "Yahoo Mail", "Apple iCloud"].includes(data.mx_provider) ||
      (data.error && /dropped connection|rejected|timeout/i.test(data.error))
    )
  );

  if (data.valid === true) {
    verdict.className = "verdict-banner valid";
    verdictIcon.textContent = "✓";
    verdictTitle.textContent = "Deliverable & Active Mailbox";
    verdictSub.textContent = "This email address is verified and active on the mail server. Messages will deliver successfully.";
    verdictBadge.textContent = "Deliverable";
    verdictBadge.className = "verdict-pill deliverable";

    vContactable.textContent = "Safe to Contact";
    vContactable.style.color = "var(--status-success-text)";
    vContactableSub.textContent = "High delivery confidence";

    vInboxStatus.textContent = "Active Mailbox";
    vInboxStatus.style.color = "var(--status-success-text)";
    vInboxSub.textContent = "Mailbox exists & accepts mail";

    vProviderSub.textContent = "Configured Host";
    noteEl.classList.add("hidden");

  } else if (data.valid === false) {
    verdict.className = "verdict-banner invalid";
    verdictIcon.textContent = "✕";
    verdictTitle.textContent = "Undeliverable Mailbox";
    verdictSub.textContent = "This mailbox does not exist on the remote mail server. Outbound emails will bounce.";
    verdictBadge.textContent = "Undeliverable";
    verdictBadge.className = "verdict-pill invalid";

    vContactable.textContent = "Do Not Send";
    vContactable.style.color = "var(--status-danger-text)";
    vContactableSub.textContent = "Will result in hard bounce";

    vInboxStatus.textContent = "Non-Existent";
    vInboxStatus.style.color = "var(--status-danger-text)";
    vInboxSub.textContent = "Rejected by mail host";

    vProviderSub.textContent = "Configured Host";
    noteEl.classList.add("hidden");

  } else if (data.catchall === true) {
    verdict.className = "verdict-banner unknown";
    verdictIcon.textContent = "!";
    verdictTitle.textContent = "Catch-All Mail Server";
    verdictSub.textContent = "The domain server accepts mail addressed to any username, so individual mailbox delivery cannot be guaranteed.";
    verdictBadge.textContent = "Catch-All";
    verdictBadge.className = "verdict-pill risky";

    vContactable.textContent = "Send with Caution";
    vContactable.style.color = "var(--status-warn-text)";
    vContactableSub.textContent = "Catch-all configuration";

    vInboxStatus.textContent = "Catch-All Domain";
    vInboxStatus.style.color = "var(--status-warn-text)";
    vInboxSub.textContent = "Accepts any address";

    vProviderSub.textContent = "Configured Host";
    noteEl.textContent = "Catch-all domains accept all incoming email to shield individual employee mailboxes from dictionary attacks. If this contact was obtained directly, delivery is likely normal.";
    noteEl.classList.remove("hidden");

  } else if (isProtectedHost) {
    verdict.className = "verdict-banner protected";
    verdictIcon.textContent = "✓";
    verdictTitle.textContent = "Protected Mail Server (Active MX)";
    verdictSub.textContent = `${provider} actively receives mail, but drops direct socket probes to safeguard user privacy.`;
    verdictBadge.textContent = "Protected";
    verdictBadge.className = "verdict-pill protected";

    vContactable.textContent = "Likely Safe";
    vContactable.style.color = "var(--brand-primary)";
    vContactableSub.textContent = "Standard enterprise security";

    vInboxStatus.textContent = "Protected Mailbox";
    vInboxStatus.style.color = "var(--brand-primary)";
    vInboxSub.textContent = "Probes filtered by host";

    vProviderSub.textContent = "Verified MX Host";
    noteEl.textContent = `${provider} deliberately drops automated SMTP verification probes to prevent user enumeration. Because the domain's MX servers are active, emails sent to a genuine recipient will deliver normally.`;
    noteEl.classList.remove("hidden");

  } else {
    verdict.className = "verdict-banner unknown";
    verdictIcon.textContent = "?";
    verdictTitle.textContent = "Unverifiable";
    verdictSub.textContent = data.error || "Remote mail server did not respond to verification probes.";
    verdictBadge.textContent = "Uncertain";
    verdictBadge.className = "verdict-pill unknown";

    vContactable.textContent = "Uncertain";
    vContactable.style.color = "var(--text-muted)";
    vContactableSub.textContent = "Could not verify";

    vInboxStatus.textContent = "Unreachable";
    vInboxStatus.style.color = "var(--text-muted)";
    vInboxSub.textContent = "Connection timed out";

    vProviderSub.textContent = "Host Service";
    noteEl.textContent = `ℹ️ ${data.error || 'The remote mail server could not be reached.'}`;
    noteEl.classList.remove("hidden");
  }

  // ── Technical Diagnostics ──
  document.getElementById("v-mx").textContent = data.mx_record || "—";

  const catchallEl = document.getElementById("v-catchall");
  if (data.catchall === true) {
    catchallEl.textContent = "Yes (Accepts all addresses)";
    catchallEl.style.color = "var(--status-warn-text)";
  } else if (data.catchall === false) {
    catchallEl.textContent = "No (Strict recipient validation)";
    catchallEl.style.color = "var(--status-success-text)";
  } else {
    catchallEl.textContent = isProtectedHost ? "Shielded / Unknown" : "Unknown";
    catchallEl.style.color = "var(--text-muted)";
  }

  const confidence = data.confidence;
  const confEl = document.getElementById("v-confidence");
  if (confidence !== null && confidence !== undefined) {
    confEl.textContent = `${confidence}%`;
    confEl.style.color = confidence >= 80
      ? "var(--status-success-text)"
      : confidence >= 50 ? "var(--status-warn-text)" : "var(--status-danger-text)";
  } else {
    confEl.textContent = "—";
  }

  const METHOD_LABELS = {
    smtp: "Direct SMTP Handshake (Port 25)",
    smtp_catchall: "SMTP (Catch-All Detected)",
    mx_only: "MX DNS Record Only",
    abstractapi: "AbstractAPI (Port 25 Fallback)",
  };
  document.getElementById("v-method").textContent =
    METHOD_LABELS[data.method_used] || data.method_used || "—";

  document.getElementById("v-time").textContent =
    data.response_time_ms !== null ? `${data.response_time_ms}ms` : "—";
}
