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
    } else if (profiles.linkedin_confidence && profiles.linkedin_confidence >= 80) {
      identityBadge.textContent = `★ ${profiles.linkedin_confidence}% Match`;
      identityBadge.className = "type-badge badge-match";
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
    const isDirect = conf === 100;
    const badgeText = isDirect ? "✓ 100% Verified" : `★ ${conf}% Match`;
    chips.push(buildProfileChip({
      href: profiles.linkedin,
      iconClass: "linkedin-icon",
      iconContent: "in",
      name: `LinkedIn <span class="badge-confidence ${isDirect ? 'verified' : 'high'}">${badgeText}</span>`,
      sub: isDirect ? "Verified in GitHub Profile →" : "Corroborated Match →",
    }));
  }

  if (profiles.github) {
    const gh = profiles.github;
    chips.push(buildProfileChip({
      href: gh.url,
      iconClass: "github-icon",
      iconContent: "⌨",
      name: `@${gh.username}`,
      sub: `${gh.repos ?? "?"} repos · ${gh.followers ?? "?"} followers`,
    }));
  }

  profilesList.innerHTML = chips.length
    ? chips.join("")
    : "<p class='no-data'>No social profiles found for this email.</p>";

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

  // ── Breaches ──
  const breachesList = document.getElementById("breaches-list");
  const breaches = data.breaches || [];

  if (breaches.length === 0) {
    breachesList.innerHTML = "<p class='no-data no-breach'>✅ No known data breaches found.</p>";
  } else {
    const top3 = breaches.slice(0, 3);
    const rest = breaches.slice(3);

    const renderBreachItem = b => `
      <div class="breach-item">
        <div class="breach-name">⚠️ ${b.name || "Unknown Breach"}</div>
        <div class="breach-date">${b.date || "Unknown date"}</div>
        <div class="breach-tags">
          ${(b.data_types || []).map(t => `<span class="breach-tag">${t}</span>`).join("")}
        </div>
      </div>
    `;

    let html = top3.map(renderBreachItem).join("");

    if (rest.length > 0) {
      html += `
        <div id="breaches-extra" class="breaches-extra collapsed">
          ${rest.map(renderBreachItem).join("")}
        </div>
        <button type="button" class="btn-toggle-breaches" id="btn-toggle-breaches">
          Show ${rest.length} more ${rest.length === 1 ? 'breach' : 'breaches'} ▼
        </button>
      `;
    }

    breachesList.innerHTML = html;

    if (rest.length > 0) {
      const toggleBtn = document.getElementById("btn-toggle-breaches");
      const extraDiv = document.getElementById("breaches-extra");
      toggleBtn.addEventListener("click", () => {
        const isCollapsed = extraDiv.classList.contains("collapsed");
        if (isCollapsed) {
          extraDiv.classList.remove("collapsed");
          toggleBtn.textContent = "Show less ▲";
        } else {
          extraDiv.classList.add("collapsed");
          toggleBtn.textContent = `Show ${rest.length} more ${rest.length === 1 ? 'breach' : 'breaches'} ▼`;
        }
      });
    }
  }

  // ── Email quality (AbstractAPI) ──
  const eq = data.email_quality || {};
  const qualityCard = document.getElementById("quality-card");
  if (eq.quality_score !== undefined && eq.quality_score !== null) {
    qualityCard.classList.remove("hidden");
    const scoreEl = document.getElementById("eq-score");
    const score = Math.round((eq.quality_score || 0) * 100);
    scoreEl.textContent = `${score}%`;
    scoreEl.style.color = score >= 80 ? "var(--c-success)" : score >= 50 ? "var(--c-warn)" : "var(--c-danger)";
    document.getElementById("eq-deliverability").textContent = eq.deliverability || "—";
    document.getElementById("eq-disposable").textContent = eq.is_disposable ? "Yes ⚠️" : "No";
    document.getElementById("eq-provider").textContent = eq.smtp_provider || "—";
    document.getElementById("eq-catchall").textContent = eq.is_catchall ? "Yes" : "No";
    document.getElementById("eq-role").textContent = eq.is_role_account ? "Yes (e.g. info@, admin@)" : "No";

    // Risk
    const addrRiskEl = document.getElementById("eq-addr-risk");
    const domainRiskEl = document.getElementById("eq-domain-risk");
    const riskColor = r => r === "High" ? "var(--c-danger)" : r === "Medium" ? "var(--c-warn)" : "var(--c-success)";
    addrRiskEl.textContent = eq.address_risk || "—";
    addrRiskEl.style.color = eq.address_risk ? riskColor(eq.address_risk) : "";
    domainRiskEl.textContent = eq.domain_risk || "—";
    domainRiskEl.style.color = eq.domain_risk ? riskColor(eq.domain_risk) : "";

    // Breach summary (kept hidden per user preference)
    const breachSection = document.getElementById("eq-breach-section");
    if (breachSection) {
      breachSection.classList.add("hidden");
    }

    const acEl = document.getElementById("eq-autocorrect");
    if (eq.autocorrect) {
      acEl.textContent = `⚠️ Did you mean: ${eq.autocorrect}?`;
      acEl.classList.remove("hidden");
    }
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

  verdict.className = "verdict-banner";

  if (data.valid === true) {
    verdict.classList.add("valid");
    verdictIcon.textContent = "✅";
    verdictTitle.textContent = "Valid Email Address";
    verdictSub.textContent = "This email address exists and can receive mail.";
  } else if (data.valid === false) {
    verdict.classList.add("invalid");
    verdictIcon.textContent = "❌";
    verdictTitle.textContent = "Invalid Email Address";
    verdictSub.textContent = "This email address does not exist on the mail server.";
  } else {
    verdict.classList.add("unknown");
    verdictIcon.textContent = "⚠️";
    verdictTitle.textContent = "Unknown / Unverifiable";
    verdictSub.textContent = data.error || "Could not determine validity.";
  }

  document.getElementById("v-provider").textContent = data.mx_provider || "—";
  document.getElementById("v-mx").textContent = data.mx_record || "—";

  const catchallEl = document.getElementById("v-catchall");
  if (data.catchall === true) {
    catchallEl.textContent = "Yes (accepts all mail)";
    catchallEl.style.color = "var(--c-warn)";
  } else if (data.catchall === false) {
    catchallEl.textContent = "No";
    catchallEl.style.color = "var(--c-success)";
  } else {
    catchallEl.textContent = "Unknown";
    catchallEl.style.color = "";
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
    smtp: "Direct SMTP Handshake",
    smtp_catchall: "SMTP (Catch-All Domain)",
    mx_only: "MX Record Only",
    abstractapi: "AbstractAPI (Port 25 blocked)",
  };
  document.getElementById("v-method").textContent =
    METHOD_LABELS[data.method_used] || data.method_used || "—";

  document.getElementById("v-time").textContent =
    data.response_time_ms !== null ? `${data.response_time_ms}ms` : "—";

  const noteEl = document.getElementById("verify-note");
  if (data.error && data.valid === null) {
    noteEl.textContent = `ℹ️ ${data.error}`;
    noteEl.classList.remove("hidden");
  } else {
    noteEl.classList.add("hidden");
  }
}
