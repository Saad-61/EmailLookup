/* ──────────────────────────────────────────────────────────────────────────
   app.js — Email Lookup frontend logic
   ────────────────────────────────────────────────────────────────────────── */

const API_BASE = window.location.origin;

// ── Platform emoji/icon map ───────────────────────────────────────────────────
const PLATFORM_ICONS = {
  github:   { emoji: "🐙", label: "GitHub" },
  spotify:  { emoji: "🎵", label: "Spotify" },
  adobe:    { emoji: "🅐",  label: "Adobe" },
  dropbox:  { emoji: "📦", label: "Dropbox" },
  discord:  { emoji: "💬", label: "Discord" },
  duolingo: { emoji: "🦜", label: "Duolingo" },
  pinterest:{ emoji: "📌", label: "Pinterest" },
  patreon:  { emoji: "🎨", label: "Patreon" },
  gravatar: { emoji: "👤", label: "Gravatar" },
  tumblr:   { emoji: "✏️", label: "Tumblr" },
  archive:  { emoji: "📚", label: "Archive.org" },
  airbnb:   { emoji: "🏠", label: "Airbnb" },
  reddit:   { emoji: "🤖", label: "Reddit" },
};

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("panel-" + btn.dataset.tab).classList.add("active");
  });
});

// ── Port 25 check on load ─────────────────────────────────────────────────────
async function checkPort25() {
  const badge = document.getElementById("port-badge");
  const badgeText = badge.querySelector(".badge-text");
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    const res = await fetch(`${API_BASE}/api/port-check`, { signal: controller.signal });
    clearTimeout(timeoutId);

    const data = await res.json();
    badge.classList.remove("loading");
    if (data.port25_available) {
      badge.classList.add("open");
      badgeText.textContent = "Port 25 open";
      badge.title = "SMTP verification works directly from your connection.";
    } else {
      badge.classList.add("blocked");
      badgeText.textContent = "Port 25 blocked";
      badge.title = "ISP blocks port 25. Using API fallback for verification.";
    }
  } catch {
    badge.classList.remove("loading");
    badge.classList.add("blocked");
    badgeText.textContent = "Port 25 blocked";
    badge.title = "Outbound port 25 check timed out or blocked by ISP.";
  }
}
checkPort25();

// ── Utility ───────────────────────────────────────────────────────────────────
function setLoading(btnEl, isLoading) {
  const textEl = btnEl.querySelector(".btn-text");
  const spinnerEl = btnEl.querySelector(".btn-spinner");
  btnEl.disabled = isLoading;
  textEl.textContent = isLoading ? "Searching..." : btnEl.dataset.originalText || textEl.textContent;
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

// ── ─────────────────────────────────────────────────────────────────────────
//    REVERSE LOOKUP
// ── ─────────────────────────────────────────────────────────────────────────
const lookupBtn = document.getElementById("lookup-btn");
const lookupRefreshBtn = document.getElementById("lookup-refresh-btn");
lookupBtn.dataset.originalText = "Search";

document.getElementById("lookup-input").addEventListener("keydown", e => {
  if (e.key === "Enter") lookupBtn.click();
});

async function doLookup(forceRefresh = false) {
  const email = document.getElementById("lookup-input").value.trim();
  const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  if (!email || !EMAIL_REGEX.test(email)) {
    showError("lookup-error", "Please enter a valid email address (e.g. name@company.com).");
    return;
  }

  hideError("lookup-error");
  const acBanner = document.getElementById("lookup-autocorrect");
  if (acBanner) acBanner.classList.add("hidden");
  document.getElementById("lookup-results").classList.add("hidden");
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
    renderLookupResults(data);
    document.getElementById("lookup-results").classList.remove("hidden");
  } catch (err) {
    showError("lookup-error", `❌ ${err.message}`);
  } finally {
    setLoading(lookupBtn, false);
    lookupBtn.querySelector(".btn-text").textContent = "Search";
  }
}

lookupBtn.addEventListener("click", () => doLookup(false));
if (lookupRefreshBtn) {
  lookupRefreshBtn.addEventListener("click", () => doLookup(true));
}

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

// ── Platform-Specific Candidate Accordion Toggles ──
document.addEventListener("click", e => {
  const btn = e.target.closest(".candidates-toggle-btn");
  if (!btn) return;
  const targetId = btn.dataset.target;
  const list = document.getElementById(targetId);
  const pill = btn.querySelector(".candidates-toggle-pill");
  const icon = btn.querySelector(".candidates-toggle-icon");
  if (!list) return;

  const isCollapsed = list.classList.contains("collapsed");
  if (isCollapsed) {
    list.classList.remove("collapsed");
    if (icon) icon.textContent = "▼";
    if (pill) pill.textContent = "Click to collapse";
  } else {
    list.classList.add("collapsed");
    if (icon) icon.textContent = "▶";
    if (pill) pill.textContent = "Click to expand";
  }
});

function renderLookupResults(data) {
  // ── Person card ──
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
  personLocEl.textContent = person.location ? "📍 " + person.location : "";

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
      avatarPlaceholder.textContent = (person.name || "?")[0].toUpperCase();
    };
  } else {
    avatarEl.classList.add("hidden");
    avatarPlaceholder.classList.remove("hidden");
    avatarPlaceholder.textContent = (person.name || "?")[0].toUpperCase();
  }

  typeBadge.textContent = data.email_type === "corporate" ? "Corporate Email" : "Personal Email";
  typeBadge.className = "type-badge " + (data.email_type || "personal");

  const profiles = data.profiles || {};
  const identityBadge = document.getElementById("identity-badge");
  if (identityBadge) {
    if (profiles.linkedin_verified || profiles.linkedin_confidence === 100) {
      identityBadge.textContent = "✓ 100% Verified Identity";
      identityBadge.className = "type-badge badge-verified";
      identityBadge.classList.remove("hidden");
    } else {
      identityBadge.classList.add("hidden");
    }
  }

  if (delivBadge) {
    if (data.deliverability === "undeliverable") {
      delivBadge.textContent = "⚠️ Inactive Mailbox / Undeliverable";
      delivBadge.classList.remove("hidden");
    } else {
      delivBadge.classList.add("hidden");
    }
  }

  personExtra.classList.remove("hidden");

  // ── Social profiles ──
  const profilesList = document.getElementById("profiles-list");
  const chips = [];

  if (profiles.linkedin) {
    const conf = profiles.linkedin_confidence || (profiles.linkedin_verified ? 100 : 85);
    const src = profiles.linkedin_source || "";
    let subText = "Corroborated Match →";
    if (src === "wikidata") subText = "Authoritative Wikidata Entity →";
    else if (src === "github") subText = "Verified in GitHub Profile →";
    else if (src === "gravatar") subText = "Verified in Gravatar Profile →";
    else if (src === "harvested") subText = "Verified Public Record →";
    else if (conf === 100) subText = "100% Corroborated Match →";

    const isDirect = (src === "wikidata" || src === "github" || src === "gravatar" || src === "harvested" || conf === 100);
    const badgeHtml = isDirect ? `<span class="badge-confidence verified">✓ 100% Verified</span>` : "";
    chips.push(buildProfileChip({
      href: profiles.linkedin,
      iconClass: "linkedin-icon",
      iconContent: "in",
      name: `LinkedIn ${badgeHtml}`,
      sub: subText,
    }));
  }

  if (profiles.github) {
    const gh = profiles.github;
    chips.push(buildProfileChip({
      href: gh.url,
      iconClass: "github-icon",
      iconContent: "⌨",
      name: `@${gh.username} <span class="badge-confidence verified">✓ 100% Verified</span>`,
      sub: `${gh.repos ?? "?"} repos · ${gh.followers ?? "?"} followers`,
    }));
  }

  if (profiles.twitter) {
    const twUrl = profiles.twitter;
    const twHandle = twUrl.split("/").pop().replace(/^@/, "");
    chips.push(buildProfileChip({
      href: twUrl,
      iconClass: "twitter-icon",
      iconContent: "𝕏",
      name: `X / Twitter <span class="badge-confidence verified">✓ 100% Verified</span>`,
      sub: `@${twHandle} · Verified Account`,
    }));
  }

  if (profiles.instagram) {
    const igUrl = profiles.instagram;
    const igHandle = igUrl.split("/").pop().replace(/^@/, "");
    chips.push(buildProfileChip({
      href: igUrl,
      iconClass: "instagram-icon",
      iconContent: "📸",
      name: `Instagram <span class="badge-confidence verified">✓ 100% Verified</span>`,
      sub: `@${igHandle} · Verified Account`,
    }));
  }

  if (profiles.facebook) {
    const fbUrl = profiles.facebook;
    const fbHandle = fbUrl.split("/").pop();
    chips.push(buildProfileChip({
      href: fbUrl,
      iconClass: "facebook-icon",
      iconContent: "fb",
      name: `Facebook <span class="badge-confidence verified">✓ 100% Verified</span>`,
      sub: `${fbHandle} · Verified Account`,
    }));
  }

  if (profiles.youtube) {
    chips.push(buildProfileChip({
      href: profiles.youtube,
      iconClass: "youtube-icon",
      iconContent: "▶",
      name: `YouTube <span class="badge-confidence verified">✓ 100% Verified</span>`,
      sub: `Verified Channel`,
    }));
  }

  // ── Candidate Social Accounts by Platform (Separate Accordions) ──
  const candidatesWrapper = document.getElementById("candidates-wrapper");
  const byPlat = data.social_candidates_by_platform || {};
  let totalCandidatesFound = 0;

  ["linkedin", "instagram", "twitter", "facebook"].forEach(plat => {
    const accEl = document.getElementById(`cand-acc-${plat}`);
    const listEl = document.getElementById(`cand-list-${plat}`);
    const countEl = document.getElementById(`cand-count-${plat}`);
    const candidates = byPlat[plat] || [];

    if (accEl && listEl) {
      if (candidates.length > 0) {
        totalCandidatesFound += candidates.length;
        if (countEl) countEl.textContent = candidates.length;
        listEl.classList.add("collapsed"); // Collapsed by default
        listEl.innerHTML = candidates.map(renderCandidateCard).join("");
        accEl.classList.remove("hidden");
      } else {
        accEl.classList.add("hidden");
      }
    }
  });

  if (chips.length > 0) {
    profilesList.innerHTML = chips.join("");
    profilesList.style.display = "flex";
  } else if (totalCandidatesFound > 0) {
    profilesList.innerHTML = "";
    profilesList.style.display = "none";
  } else {
    profilesList.innerHTML = "<p class='no-data'>No social profiles found for this email.</p>";
    profilesList.style.display = "block";
  }

  if (candidatesWrapper) {
    if (totalCandidatesFound > 0) {
      candidatesWrapper.classList.remove("hidden");
    } else {
      candidatesWrapper.classList.add("hidden");
    }
  }


  // ── Platform Accounts (13+ probed platforms) ──
  const platformsCard = document.getElementById("platforms-card");
  const platformsList = document.getElementById("platforms-list");
  const platformsSummary = document.getElementById("platforms-summary");
  const platforms = data.platforms || [];

  if (platformsCard && platformsList) {
    if (platforms.length > 0) {
      const foundCount = platforms.filter(p => p.found).length;
      if (platformsSummary) {
        platformsSummary.textContent = `${foundCount} active account${foundCount === 1 ? '' : 's'} detected`;
      }
      platformsList.innerHTML = platforms.map(p => {
        const iconInfo = PLATFORM_ICONS[p.icon] || { emoji: "🌐", label: p.name };
        return `
          <div class="platform-chip ${p.found ? 'found' : 'not-found'}">
            <span class="platform-icon-emoji">${iconInfo.emoji}</span>
            <span>${p.name}</span>
            <span class="platform-status">${p.found ? '✅' : '—'}</span>
          </div>
        `;
      }).join("");
      platformsCard.classList.remove("hidden");
    } else {
      platformsCard.classList.add("hidden");
    }
  }

  // ── Contact ──
  const phoneEl = document.getElementById("phone-val");
  if (data.phone) {
    phoneEl.textContent = data.phone;
    phoneEl.classList.remove("not-found");
  } else {
    phoneEl.textContent = "Not publicly listed";
    phoneEl.classList.add("not-found");
  }

  const contactLocEl = document.getElementById("location-val");
  if (person.location) {
    contactLocEl.textContent = person.location;
    contactLocEl.classList.remove("not-found");
  } else {
    contactLocEl.textContent = "Not specified";
    contactLocEl.classList.add("not-found");
  }

  // ── Company & Education Intelligence ──
  const companyCard = document.getElementById("company-card");
  const comp = data.company;
  if (companyCard && comp && (comp.name || comp.domain)) {
    const cardTitleEl = companyCard.querySelector(".card-title");
    if (cardTitleEl) {
      if (comp.type === "education") {
        cardTitleEl.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>
          Education &amp; University
        `;
      } else if (comp.type === "academic_workplace") {
        cardTitleEl.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>
          Academic Workplace
        `;
      } else {
        cardTitleEl.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18M3 7v14M21 7v14M6 11h4M6 15h4M14 11h4M14 15h4M9 21v-4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v4M3 7l9-4 9 4"/></svg>
          Company &amp; Workplace
        `;
      }
    }

    document.getElementById("company-name").textContent = comp.name || comp.domain;
    const metaParts = [];
    if (comp.role) metaParts.push(comp.role);
    if (comp.industry) metaParts.push(comp.industry);
    if (comp.country) metaParts.push(comp.country);
    if (comp.alma_mater) metaParts.push(`Alum: ${comp.alma_mater}`);
    if (comp.domain && comp.domain.toLowerCase() !== (comp.name || "").toLowerCase()) metaParts.push(comp.domain);
    document.getElementById("company-meta").textContent = metaParts.join(" · ") || comp.domain || "Enterprise";

    const logoEl = document.getElementById("company-logo");
    if (comp.logo) {
      logoEl.src = comp.logo;
      logoEl.classList.remove("hidden");
      logoEl.onerror = () => {
        if (comp.domain && !logoEl.src.includes("google.com/s2/favicons")) {
          logoEl.src = `https://www.google.com/s2/favicons?domain=${comp.domain}&sz=128`;
        } else {
          logoEl.classList.add("hidden");
        }
      };
    } else if (comp.domain) {
      logoEl.src = `https://www.google.com/s2/favicons?domain=${comp.domain}&sz=128`;
      logoEl.classList.remove("hidden");
      logoEl.onerror = () => logoEl.classList.add("hidden");
    } else {
      logoEl.classList.add("hidden");
    }

    companyCard.classList.remove("hidden");
  } else if (companyCard) {
    companyCard.classList.add("hidden");
  }





  // ── Global Typo Banner ──
  const acBanner = document.getElementById("lookup-autocorrect");
  const acEmail = document.getElementById("autocorrect-email");
  const acBtn = document.getElementById("autocorrect-apply-btn");
  const autocorrectTarget = data.autocorrect || (data.email_quality || {}).autocorrect;
  if (autocorrectTarget && autocorrectTarget.toLowerCase() !== (data.email || "").toLowerCase()) {
    if (acBanner && acEmail) {
      acEmail.textContent = autocorrectTarget;
      acBanner.classList.remove("hidden");
      acBtn.onclick = () => {
        document.getElementById("lookup-input").value = autocorrectTarget;
        doLookup(false);
      };
    }
  } else if (acBanner) {
    acBanner.classList.add("hidden");
  }

  // ── Query time ──
  document.getElementById("query-time").textContent = `Query completed in ${data.query_time_ms}ms`;
}

function buildProfileChip({ href, iconClass, iconContent, name, sub }) {
  return `
    <a href="${href}" target="_blank" rel="noopener noreferrer" class="profile-chip">
      <div class="profile-chip-icon ${iconClass}">${iconContent}</div>
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
  const pIconClass = c.platform === "linkedin"
    ? "linkedin-icon"
    : c.platform === "twitter"
    ? "twitter-icon"
    : c.platform === "instagram"
    ? "instagram-icon"
    : "facebook-icon";
  const pIconSymbol = c.platform === "linkedin"
    ? "💼"
    : c.platform === "twitter"
    ? "𝕏"
    : c.platform === "instagram"
    ? "📸"
    : "ⓕ";

  const headlineHtml = c.title ? `<div class="candidate-headline" style="font-size:12px; color:var(--c-text-secondary); margin-top:2px; line-height:1.3;">${escapeHtml(c.title)}</div>` : "";
  const snippetHtml = c.snippet ? `<div class="candidate-snippet">${escapeHtml(c.snippet)}</div>` : "";

  const avatarImgHtml = c.avatar_url ? `
    <img src="${escapeHtml(c.avatar_url)}" class="candidate-avatar" alt="${escapeHtml(c.handle)}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
    <div class="profile-chip-icon ${pIconClass}" style="display: none;">${pIconSymbol}</div>
  ` : `
    <div class="profile-chip-icon ${pIconClass}">${pIconSymbol}</div>
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
            </div>
            <div class="candidate-platform-sub">${escapeHtml(c.platform_label || c.platform)}</div>
            ${headlineHtml}
          </div>
        </div>
        ${snippetHtml}
      </div>
      <a href="${c.url}" target="_blank" rel="noopener noreferrer" class="candidate-action-btn">
        <span>View</span>
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
  const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  if (!email || !EMAIL_REGEX.test(email)) {
    showError("verify-error", "Please enter a valid email address (e.g. name@company.com).");
    return;
  }

  hideError("verify-error");
  document.getElementById("verify-results").classList.add("hidden");
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
    renderVerifyResults(data);
    document.getElementById("verify-results").classList.remove("hidden");
  } catch (err) {
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
    verdictIcon.textContent = "✅";
    verdictTitle.textContent = "Safe to Contact";
    verdictSub.textContent = "This email address is verified and active. Messages will reach this inbox.";
    verdictBadge.textContent = "Deliverable";
    verdictBadge.className = "verdict-pill deliverable";

    vContactable.textContent = "Yes, Safe to Send";
    vContactable.style.color = "var(--c-success)";
    vContactableSub.textContent = "High confidence delivery";

    vInboxStatus.textContent = "Active Mailbox";
    vInboxStatus.style.color = "var(--c-success)";
    vInboxSub.textContent = "Mailbox exists & accepts mail";

    vProviderSub.textContent = "Configured Host";
    noteEl.classList.add("hidden");

  } else if (data.valid === false) {
    verdict.className = "verdict-banner invalid";
    verdictIcon.textContent = "❌";
    verdictTitle.textContent = "Do Not Send";
    verdictSub.textContent = "This mailbox does not exist on the mail server. Sending will bounce.";
    verdictBadge.textContent = "Undeliverable";
    verdictBadge.className = "verdict-pill invalid";

    vContactable.textContent = "No, Will Bounce";
    vContactable.style.color = "var(--c-danger)";
    vContactableSub.textContent = "Do not send mail";

    vInboxStatus.textContent = "Non-Existent";
    vInboxStatus.style.color = "var(--c-danger)";
    vInboxSub.textContent = "Rejected by mail server";

    vProviderSub.textContent = "Configured Host";
    noteEl.classList.add("hidden");

  } else if (data.catchall === true) {
    verdict.className = "verdict-banner unknown";
    verdictIcon.textContent = "⚠️";
    verdictTitle.textContent = "Catch-All Server (Risky)";
    verdictSub.textContent = "The server accepts mail sent to any name, so individual mailbox delivery cannot be guaranteed.";
    verdictBadge.textContent = "Risky";
    verdictBadge.className = "verdict-pill risky";

    vContactable.textContent = "Send with Caution";
    vContactable.style.color = "var(--c-warn)";
    vContactableSub.textContent = "Catch-all configuration";

    vInboxStatus.textContent = "Catch-All Domain";
    vInboxStatus.style.color = "var(--c-warn)";
    vInboxSub.textContent = "Accepts any address";

    vProviderSub.textContent = "Configured Host";
    noteEl.textContent = "ℹ️ Catch-all mail servers accept all inbound emails to prevent spam harvesting of employee lists. If this email was provided directly by the recipient, it is likely legitimate.";
    noteEl.classList.remove("hidden");

  } else if (isProtectedHost) {
    verdict.className = "verdict-banner protected";
    verdictIcon.textContent = "🛡️";
    verdictTitle.textContent = "Server Protected (Domain Active)";
    verdictSub.textContent = `${provider} actively receives mail, but shields individual mailbox probes from third-party scanners.`;
    verdictBadge.textContent = "Protected";
    verdictBadge.className = "verdict-pill protected";

    vContactable.textContent = "Likely Safe";
    vContactable.style.color = "var(--c-accent)";
    vContactableSub.textContent = "Standard security policy";

    vInboxStatus.textContent = "Protected Mailbox";
    vInboxStatus.style.color = "var(--c-accent)";
    vInboxSub.textContent = "Probes dropped by host";

    vProviderSub.textContent = "Verified MX Host";
    noteEl.textContent = `ℹ️ ${provider} deliberately drops automated SMTP verification handshakes to protect user privacy. Because the domain's MX servers are active and healthy, emails sent to a genuine recipient will deliver normally.`;
    noteEl.classList.remove("hidden");

  } else {
    verdict.className = "verdict-banner unknown";
    verdictIcon.textContent = "⚠️";
    verdictTitle.textContent = "Unverifiable";
    verdictSub.textContent = data.error || "Remote mail server did not respond to verification probes.";
    verdictBadge.textContent = "Uncertain";
    verdictBadge.className = "verdict-pill unknown";

    vContactable.textContent = "Uncertain";
    vContactable.style.color = "var(--c-muted)";
    vContactableSub.textContent = "Could not verify";

    vInboxStatus.textContent = "Unreachable";
    vInboxStatus.style.color = "var(--c-muted)";
    vInboxSub.textContent = "Connection timed out";

    vProviderSub.textContent = "Host Service";
    noteEl.textContent = `ℹ️ ${data.error || 'The remote mail server could not be reached.'}`;
    noteEl.classList.remove("hidden");
  }

  // ── Technical Diagnostics (collapsed by default) ──
  document.getElementById("v-mx").textContent = data.mx_record || "—";

  const catchallEl = document.getElementById("v-catchall");
  if (data.catchall === true) {
    catchallEl.textContent = "Yes (Accepts all mail)";
    catchallEl.style.color = "var(--c-warn)";
  } else if (data.catchall === false) {
    catchallEl.textContent = "No";
    catchallEl.style.color = "var(--c-success)";
  } else {
    catchallEl.textContent = isProtectedHost ? "Shielded / Unknown" : "Unknown";
    catchallEl.style.color = "var(--c-muted)";
  }

  const confidence = data.confidence;
  const confEl = document.getElementById("v-confidence");
  if (confidence !== null && confidence !== undefined) {
    confEl.textContent = `${confidence}%`;
    confEl.style.color = confidence >= 80
      ? "var(--c-success)"
      : confidence >= 50 ? "var(--c-warn)" : "var(--c-danger)";
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
